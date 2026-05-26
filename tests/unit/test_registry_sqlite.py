"""Persistence of NodeRegistry rows via SQLite (optional Synapse_REGISTRY_DB)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.core.corroboration import ClassicZScoreStrategy
from src.core.node_registry import NodeRegistry


def _ping(node_id: str, cell: str = "c1", value: float = 20.0) -> dict:
    return {
        "node_id": node_id,
        "type": "mock",
        "timestamp": 100.0,
        "status": "PING",
        "h3_cell": cell,
        "payload": {"value": value, "lat": 45.0, "lon": 9.0},
    }


def test_sqlite_survives_process_restart() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "registry.sqlite")
        r1 = NodeRegistry(
            corroboration_strategy=ClassicZScoreStrategy(),
            sqlite_path=path,
        )
        r1.upsert(_ping("alpha"))
        assert r1.get_node("alpha") is not None
        del r1

        r2 = NodeRegistry(
            corroboration_strategy=ClassicZScoreStrategy(),
            sqlite_path=path,
        )
        n = r2.get_node("alpha")
        assert n is not None
        assert n["node_id"] == "alpha"
        assert n["status"] == "ALIVE"
        assert n["h3_cell"] == "c1"


def test_sqlite_eviction_deletes_row() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "r.sqlite")
        r = NodeRegistry(
            corroboration_strategy=ClassicZScoreStrategy(),
            sqlite_path=path,
        )
        r.upsert(_ping("gone"))
        r.check_timeouts(now=200.0, death_timeout=3.0)
        r.evict_dead_nodes(now=500.0, death_timeout=3.0, eviction_ttl=10.0)
        assert r.get_node("gone") is None
        del r

        r2 = NodeRegistry(sqlite_path=path)
        assert r2.get_node("gone") is None
