"""
tests/unit/test_garbage_collector.py

Unit tests for GarbageCollector asyncio loops.
Uses unittest.mock to freeze time — no real delays.
"""

from unittest.mock import patch

import pytest

from src.core.garbage_collector import GarbageCollector
from src.core.node_registry import NodeRegistry


def _make_ping(node_id: str = "sensor_01", ts: float = 100.0) -> dict:
    return {
        "node_id": node_id,
        "type": "mock",
        "timestamp": ts,
        "status": "PING",
        "payload": {"value": 0.0},
    }


class TestGarbageCollectorLoops:
    """
    These tests patch asyncio.sleep and time.time to simulate the passage of
    time without actually waiting, keeping the suite fast and deterministic.
    """

    @pytest.fixture
    def registry(self) -> NodeRegistry:
        return NodeRegistry()

    @pytest.fixture
    def gc(self, registry: NodeRegistry) -> GarbageCollector:
        return GarbageCollector(registry, death_timeout=3.0, eviction_ttl=10.0)

    async def test_check_loop_marks_node_dead(
        self, registry: NodeRegistry, gc: GarbageCollector
    ) -> None:
        """The check_loop marks a timed-out node as DEAD in exactly one tick."""
        registry.upsert(_make_ping("s1", ts=100.0))
        gc._running = True  # normally set by start(); bypass here for unit testing

        async def fake_sleep(_: float) -> None:
            gc.stop()  # stop after the first sleep → one iteration only

        with (
            patch("src.core.garbage_collector.asyncio.sleep", side_effect=fake_sleep),
            patch("src.core.garbage_collector.time.time", return_value=110.0),
        ):
            await gc._check_loop()

        assert registry.get_node("s1")["status"] == "DEAD"

    async def test_evict_loop_removes_dead_node(
        self, registry: NodeRegistry, gc: GarbageCollector
    ) -> None:
        """The evict_loop physically removes a DEAD node past its TTL."""
        registry.upsert(_make_ping("s1", ts=100.0))
        registry.check_timeouts(now=110.0, death_timeout=3.0)  # mark DEAD manually
        gc._running = True

        async def fake_sleep(_: float) -> None:
            gc.stop()

        with (
            patch("src.core.garbage_collector.asyncio.sleep", side_effect=fake_sleep),
            patch("src.core.garbage_collector.time.time", return_value=114.0),
        ):
            await gc._evict_loop()

        assert registry.get_node("s1") is None

    async def test_evict_loop_respects_ttl(
        self, registry: NodeRegistry, gc: GarbageCollector
    ) -> None:
        """The evict_loop does NOT remove a node still within its TTL."""
        registry.upsert(_make_ping("s1", ts=100.0))
        registry.check_timeouts(now=110.0, death_timeout=3.0)  # mark DEAD manually
        gc._running = True

        # now=104: only 4s since last_seen=100, total_grace=13s → must NOT evict
        async def fake_sleep(_: float) -> None:
            gc.stop()

        with (
            patch("src.core.garbage_collector.asyncio.sleep", side_effect=fake_sleep),
            patch("src.core.garbage_collector.time.time", return_value=104.0),
        ):
            await gc._evict_loop()

        assert registry.get_node("s1") is not None
