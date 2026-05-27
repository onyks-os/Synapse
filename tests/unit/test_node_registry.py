"""
tests/unit/test_node_registry.py

Unit tests for NodeRegistry.
All tests use mocked time — no network, no asyncio required.
"""

import time

import pytest

from src.core.node_registry import NodeRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> NodeRegistry:
    return NodeRegistry()


def _make_ping(node_id: str = "sensor_01", ts: float | None = None) -> dict:
    return {
        "node_id": node_id,
        "type": "mock",
        "timestamp": ts if ts is not None else time.time(),
        "status": "PING",
        "payload": {"value": 0.0},
    }


# ---------------------------------------------------------------------------
# upsert()
# ---------------------------------------------------------------------------


class TestUpsert:
    def test_register_new_node(self, registry: NodeRegistry) -> None:
        """A first PING creates an ALIVE entry."""
        registry.upsert(_make_ping("sensor_01"))
        entry = registry.get_node("sensor_01")
        assert entry is not None
        assert entry["node_id"] == "sensor_01"
        assert entry["status"] == "ALIVE"

    def test_update_existing_node_refreshes_last_seen(
        self, registry: NodeRegistry
    ) -> None:
        """A second PING updates last_seen without duplicating the entry."""
        registry.upsert(_make_ping("sensor_01", ts=100.0))
        registry.upsert(_make_ping("sensor_01", ts=200.0))
        assert len(registry) == 1
        assert registry.get_node("sensor_01")["last_seen"] == 200.0

    def test_resurrection_alive(self, registry: NodeRegistry) -> None:
        """A DEAD node that receives a new PING becomes ALIVE again."""
        registry.upsert(_make_ping("sensor_01", ts=100.0))
        # Simulate death detection
        registry.check_timeouts(now=110.0, death_timeout=3.0)
        assert registry.get_node("sensor_01")["status"] == "DEAD"
        # Sensor reconnects
        registry.upsert(_make_ping("sensor_01", ts=115.0))
        assert registry.get_node("sensor_01")["status"] == "ALIVE"

    def test_multiple_sensors_independent(self, registry: NodeRegistry) -> None:
        """Multiple sensors are tracked independently."""
        registry.upsert(_make_ping("s1", ts=100.0))
        registry.upsert(_make_ping("s2", ts=100.0))
        registry.upsert(_make_ping("s3", ts=100.0))
        assert len(registry) == 3


# ---------------------------------------------------------------------------
# check_timeouts()
# ---------------------------------------------------------------------------


class TestCheckTimeouts:
    def test_mark_dead_on_timeout(self, registry: NodeRegistry) -> None:
        """A node exceeding death_timeout is marked DEAD."""
        registry.upsert(_make_ping("sensor_01", ts=100.0))
        dead = registry.check_timeouts(now=104.0, death_timeout=3.0)
        assert "sensor_01" in dead
        assert registry.get_node("sensor_01")["status"] == "DEAD"

    def test_no_premature_death(self, registry: NodeRegistry) -> None:
        """A node within the timeout window stays ALIVE."""
        registry.upsert(_make_ping("sensor_01", ts=100.0))
        dead = registry.check_timeouts(now=102.0, death_timeout=3.0)
        assert dead == []
        assert registry.get_node("sensor_01")["status"] == "ALIVE"

    def test_already_dead_not_re_listed(self, registry: NodeRegistry) -> None:
        """Calling check_timeouts on an already-DEAD node does not re-list it."""
        registry.upsert(_make_ping("sensor_01", ts=100.0))
        registry.check_timeouts(now=110.0, death_timeout=3.0)
        dead_again = registry.check_timeouts(now=120.0, death_timeout=3.0)
        assert "sensor_01" not in dead_again

    def test_returns_only_newly_dead(self, registry: NodeRegistry) -> None:
        """Only the node crossing the threshold this call is returned."""
        registry.upsert(_make_ping("s1", ts=100.0))
        registry.upsert(_make_ping("s2", ts=100.0))
        # First call: both should die
        dead = registry.check_timeouts(now=110.0, death_timeout=3.0)
        assert set(dead) == {"s1", "s2"}


# ---------------------------------------------------------------------------
# evict_dead_nodes()
# ---------------------------------------------------------------------------


class TestEvictDeadNodes:
    def test_ttl_eviction(self, registry: NodeRegistry) -> None:
        """A DEAD node is physically deleted after death_timeout + eviction_ttl."""
        registry.upsert(_make_ping("sensor_01", ts=100.0))
        registry.check_timeouts(now=110.0, death_timeout=3.0)
        evicted = registry.evict_dead_nodes(
            now=114.0, death_timeout=3.0, eviction_ttl=10.0
        )
        assert "sensor_01" in evicted
        assert registry.get_node("sensor_01") is None
        assert len(registry) == 0

    def test_no_early_eviction(self, registry: NodeRegistry) -> None:
        """A DEAD node is NOT deleted before death_timeout + eviction_ttl."""
        registry.upsert(_make_ping("sensor_01", ts=100.0))
        registry.check_timeouts(now=110.0, death_timeout=3.0)
        # Only 5s have passed since last_seen=100, total_grace = 13s
        evicted = registry.evict_dead_nodes(
            now=106.0, death_timeout=3.0, eviction_ttl=10.0
        )
        assert evicted == []
        assert registry.get_node("sensor_01") is not None

    def test_alive_node_never_evicted(self, registry: NodeRegistry) -> None:
        """An ALIVE node is never evicted regardless of elapsed time."""
        registry.upsert(_make_ping("sensor_01", ts=100.0))
        evicted = registry.evict_dead_nodes(
            now=999.0, death_timeout=3.0, eviction_ttl=10.0
        )
        assert evicted == []
        assert registry.get_node("sensor_01") is not None
