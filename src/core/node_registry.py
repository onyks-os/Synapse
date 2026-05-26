"""
src/core/node_registry.py

Pure state management for discovered network nodes.
No ZeroMQ or I/O dependencies — receives dicts, returns state.
V2: NodeEntry extended with h3_cell, lat, lon, last_value.
V2 Phase 2: FAULTY state + pluggable spatial corroboration (see corroboration.py).
V2: optional SQLite persistence for node rows (Synapse_REGISTRY_DB); counters stay in RAM.
"""

from __future__ import annotations

import threading
import time
from typing import TypedDict, cast

from src.core import event_logger
from src.core.corroboration import CorroborationStrategy, build_corroboration_strategy
from src.core.registry_store import SqliteRegistryStore


def _fault_event_detail(metrics: dict[str, float | str]) -> dict[str, object]:
    """Normalize corroboration metrics for structured logging."""
    out: dict[str, object] = {}
    for key, val in metrics.items():
        if isinstance(val, float):
            out[key] = round(val, 4)
        else:
            out[key] = val
    return out


class NodeEntry(TypedDict):
    node_id: str
    type: str
    status: str  # "ALIVE" | "FAULTY" | "DEAD"
    last_seen: float  # Unix epoch
    h3_cell: str  # H3 cell index string
    lat: float
    lon: float
    last_value: float  # Most recent sensor reading (used for corroboration)


class NodeRegistry:
    """
    In-memory registry of all known sensor nodes, optionally mirrored to SQLite.

    A ``threading.RLock`` protects the table for the asyncio ingest thread,
    garbage collector, and the Flask dashboard thread.
    """

    def __init__(
        self,
        corroboration_strategy: CorroborationStrategy | None = None,
        sqlite_path: str | None = None,
        self_node_id: str | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._nodes: dict[str, NodeEntry] = {}
        self._self_node_id = self_node_id
        self._corroboration: CorroborationStrategy = (
            corroboration_strategy or build_corroboration_strategy()
        )
        self._sqlite: SqliteRegistryStore | None = (
            SqliteRegistryStore(sqlite_path) if sqlite_path else None
        )
        if self._sqlite is not None:
            loaded = self._sqlite.load_all()
            self._nodes.update(loaded)

        self._counters: dict[str, int] = {
            "messages_total": 0,
            "invalid_payload_total": 0,
            "rate_limited_total": 0,
            "corroboration_faulty_total": 0,
            "node_registered_total": 0,
            "node_dead_total": 0,
            "node_evicted_total": 0,
        }

    @property
    def self_node_id(self) -> str | None:
        return self._self_node_id

    def inc_counter(self, name: str, amount: int = 1) -> None:
        """Increment a named counter metric."""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = 0
            self._counters[name] += amount

    def metrics_snapshot(self) -> dict[str, int]:
        """Return a Prometheus-friendly snapshot (counters + gauges)."""
        with self._lock:
            alive = sum(1 for e in self._nodes.values() if e["status"] == "ALIVE")
            faulty = sum(1 for e in self._nodes.values() if e["status"] == "FAULTY")
            dead = sum(1 for e in self._nodes.values() if e["status"] == "DEAD")
            return {
                **self._counters,
                "nodes_alive": alive,
                "nodes_faulty": faulty,
                "nodes_dead": dead,
                "nodes_total": len(self._nodes),
            }

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def upsert(self, payload: dict) -> None:
        """
        Register a new node or update an existing one.
        Always resets status to ALIVE and refreshes last_seen.
        """
        raw_id = payload.get("node_id")
        if not raw_id or str(raw_id).strip().lower() in ("null", "none", ""):
            return
        node_id = str(raw_id)
        inner = payload.get("payload", {})
        h3_cell = payload.get("h3_cell", "")

        with self._lock:
            prev = self._nodes.get(node_id)
            if prev is None:
                event_logger.emit("NODE_REGISTERED", node_id, cell=h3_cell)
                self._bump_counter_unlocked("node_registered_total", 1)
            elif prev["status"] in ("DEAD", "FAULTY"):
                event_logger.emit(
                    "NODE_RESURRECTED",
                    node_id,
                    cell=h3_cell,
                    previous_status=prev["status"],
                )

            self._nodes[node_id] = NodeEntry(
                node_id=node_id,
                type=payload.get("type", "unknown"),
                status="ALIVE",
                last_seen=payload.get("timestamp", time.time()),
                h3_cell=h3_cell,
                lat=float(inner.get("lat", 0.0)),
                lon=float(inner.get("lon", 0.0)),
                last_value=float(inner.get("value", 0.0)),
            )
            self._bump_counter_unlocked("messages_total", 1)
            entry = self._nodes[node_id]
            if self._sqlite is not None:
                self._sqlite.put(entry)

    def _bump_counter_unlocked(self, name: str, amount: int = 1) -> None:
        if name not in self._counters:
            self._counters[name] = 0
        self._counters[name] += amount

    def check_timeouts(self, now: float, death_timeout: float) -> list[str]:
        """Mark silent ALIVE/FAULTY nodes as DEAD."""
        with self._lock:
            newly_dead: list[str] = []
            for node_id, entry in self._nodes.items():
                if (
                    entry["status"] in ("ALIVE", "FAULTY")
                    and (now - entry["last_seen"]) > death_timeout
                ):
                    self._nodes[node_id]["status"] = "DEAD"
                    newly_dead.append(node_id)
                    self._bump_counter_unlocked("node_dead_total", 1)
                    event_logger.emit(
                        "NODE_DEAD",
                        node_id,
                        cell=entry["h3_cell"],
                        silent_seconds=round(now - entry["last_seen"], 1),
                    )
                    if self._sqlite is not None:
                        self._sqlite.put(self._nodes[node_id])
            return newly_dead

    def evict_dead_nodes(
        self, now: float, death_timeout: float, eviction_ttl: float
    ) -> list[str]:
        """Remove DEAD nodes past eviction TTL."""
        with self._lock:
            total_grace = death_timeout + eviction_ttl
            to_evict = [
                node_id
                for node_id, entry in self._nodes.items()
                if entry["status"] == "DEAD"
                and (now - entry["last_seen"]) > total_grace
            ]
            for node_id in to_evict:
                event_logger.emit(
                    "NODE_EVICTED",
                    node_id,
                    cell=self._nodes[node_id]["h3_cell"],
                )
                del self._nodes[node_id]
                self._bump_counter_unlocked("node_evicted_total", 1)
                if self._sqlite is not None:
                    self._sqlite.delete(node_id)
            return to_evict

    def check_corroboration(
        self,
        cell: str,
        zscore_threshold: float,
        min_peers: int,
    ) -> list[str]:
        """Spatial corroboration for one H3 cell (see TDD §4.5)."""
        with self._lock:
            alive_in_cell = [
                e
                for e in self._nodes.values()
                if e["h3_cell"] == cell and e["status"] == "ALIVE"
            ]

            if len(alive_in_cell) < min_peers:
                return []

            newly_faulty: list[str] = []
            for i, entry in enumerate(alive_in_cell):
                peer_values = [
                    alive_in_cell[j]["last_value"]
                    for j in range(len(alive_in_cell))
                    if j != i
                ]
                if len(peer_values) < 2:
                    continue

                is_outlier, metrics = self._corroboration.evaluate(
                    entry["last_value"], peer_values, zscore_threshold
                )
                if is_outlier:
                    nid = entry["node_id"]
                    self._nodes[nid]["status"] = "FAULTY"
                    newly_faulty.append(nid)
                    self._bump_counter_unlocked("corroboration_faulty_total", 1)
                    detail = _fault_event_detail(metrics)
                    event_logger.emit(
                        "NODE_FAULTY",
                        nid,
                        cell=cell,
                        threshold=zscore_threshold,
                        value=entry["last_value"],
                        **detail,
                    )
                    if self._sqlite is not None:
                        self._sqlite.put(self._nodes[nid])

            return newly_faulty

    # ------------------------------------------------------------------
    # Read API — single-node
    # ------------------------------------------------------------------

    def get_all(self) -> dict[str, NodeEntry]:
        """Return a snapshot copy of the node table (safe across threads)."""
        with self._lock:
            return {k: cast(NodeEntry, dict(v)) for k, v in self._nodes.items()}

    def get_node(self, node_id: str) -> NodeEntry | None:
        """Return a single node entry or None if not found."""
        with self._lock:
            e = self._nodes.get(node_id)
            return cast(NodeEntry, dict(e)) if e is not None else None

    # ------------------------------------------------------------------
    # Read API — spatial
    # ------------------------------------------------------------------

    def get_by_cell(self, cell: str) -> list[NodeEntry]:
        """Return all nodes belonging to a specific H3 cell."""
        with self._lock:
            return [
                cast(NodeEntry, dict(e))
                for e in self._nodes.values()
                if e["h3_cell"] == cell
            ]

    def get_cells_summary(self) -> dict[str, dict]:
        """Per-cell summary for the dashboard API."""
        with self._lock:
            summary: dict[str, dict] = {}
            for entry in self._nodes.values():
                c = entry["h3_cell"]
                if not c:
                    continue
                if c not in summary:
                    summary[c] = {
                        "alive": 0,
                        "faulty": 0,
                        "dead": 0,
                        "nodes": [],
                        "lat": entry["lat"],
                        "lon": entry["lon"],
                    }
                summary[c]["nodes"].append(entry["node_id"])
                if entry["status"] == "ALIVE":
                    summary[c]["alive"] += 1
                elif entry["status"] == "FAULTY":
                    summary[c]["faulty"] += 1
                else:
                    summary[c]["dead"] += 1
            return summary

    def __len__(self) -> int:
        with self._lock:
            return len(self._nodes)

    def __repr__(self) -> str:
        with self._lock:
            counts = {"ALIVE": 0, "FAULTY": 0, "DEAD": 0}
            for e in self._nodes.values():
                counts[e["status"]] = counts.get(e["status"], 0) + 1
            return (
                f"<NodeRegistry alive={counts['ALIVE']} faulty={counts['FAULTY']} "
                f"dead={counts['DEAD']}>"
            )
