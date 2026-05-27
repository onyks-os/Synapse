"""
src/core/registry_store.py

Optional SQLite backing store for NodeRegistry rows (node snapshots only).
Prometheus-style counters in NodeRegistry are **not** persisted — they reset on
process start (see docs/TDD.md).

Env: ``Synapse_REGISTRY_DB`` — filesystem path to the SQLite file (parent dirs created).
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.node_registry import NodeEntry

_SCHEMA_VERSION = "1"


class SqliteRegistryStore:
    """
    Thread-safe, synchronous persistence. Call from NodeRegistry while holding
    the registry lock so reads/writes stay consistent with the in-memory table.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        parent = Path(path).parent
        if str(parent) not in (".", ""):
            parent.mkdir(parents=True, exist_ok=True)
        self._db_lock = threading.Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_schema(self) -> None:
        with self._db_lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS registry_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS registry_nodes (
                        node_id TEXT PRIMARY KEY,
                        type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        last_seen REAL NOT NULL,
                        h3_cell TEXT NOT NULL,
                        lat REAL NOT NULL,
                        lon REAL NOT NULL,
                        last_value REAL NOT NULL
                    );
                    """
                )
                conn.execute(
                    "INSERT OR IGNORE INTO registry_meta (key, value) VALUES (?, ?)",
                    ("schema_version", _SCHEMA_VERSION),
                )
                conn.commit()
            finally:
                conn.close()

    def load_all(self) -> dict[str, NodeEntry]:
        """Return all stored rows keyed by node_id. Invalid status rows are skipped."""
        from src.core.node_registry import NodeEntry  # late import avoids cycle

        with self._db_lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """
                    SELECT node_id, type, status, last_seen, h3_cell, lat, lon, last_value
                    FROM registry_nodes
                    """
                )
                rows: dict[str, NodeEntry] = {}
                for row in cur.fetchall():
                    node_id, typ, status, last_seen, h3_cell, lat, lon, last_value = row
                    if status not in ("ALIVE", "FAULTY", "DEAD"):
                        continue
                    rows[str(node_id)] = NodeEntry(
                        node_id=str(node_id),
                        type=str(typ),
                        status=str(status),
                        last_seen=float(last_seen),
                        h3_cell=str(h3_cell or ""),
                        lat=float(lat),
                        lon=float(lon),
                        last_value=float(last_value),
                    )
                return rows
            finally:
                conn.close()

    def put(self, entry: NodeEntry) -> None:
        with self._db_lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO registry_nodes (
                        node_id, type, status, last_seen, h3_cell, lat, lon, last_value
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(node_id) DO UPDATE SET
                        type=excluded.type,
                        status=excluded.status,
                        last_seen=excluded.last_seen,
                        h3_cell=excluded.h3_cell,
                        lat=excluded.lat,
                        lon=excluded.lon,
                        last_value=excluded.last_value
                    """,
                    (
                        entry["node_id"],
                        entry["type"],
                        entry["status"],
                        entry["last_seen"],
                        entry["h3_cell"],
                        entry["lat"],
                        entry["lon"],
                        entry["last_value"],
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def delete(self, node_id: str) -> None:
        with self._db_lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM registry_nodes WHERE node_id = ?", (node_id,))
                conn.commit()
            finally:
                conn.close()
