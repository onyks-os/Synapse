"""
src/core/garbage_collector.py

Asyncio background task that drives periodic eviction of stale nodes.
Delegates all state mutations to NodeRegistry (which emits structured events).
"""

import asyncio
import logging
import time

from src.core.node_registry import NodeRegistry

logger = logging.getLogger(__name__)


class GarbageCollector:
    """
    Runs two independent asyncio loops:
      1. check_loop  — marks ALIVE nodes as DEAD on timeout.
      2. evict_loop  — physically deletes DEAD nodes after TTL.

    Both loops tick every second for responsiveness without busy-waiting.
    """

    _CHECK_INTERVAL: float = 1.0  # seconds between each dead-check tick
    _EVICT_INTERVAL: float = 1.0  # seconds between each eviction tick

    def __init__(
        self,
        registry: NodeRegistry,
        death_timeout: float,
        eviction_ttl: float,
    ) -> None:
        self._registry = registry
        self._death_timeout = death_timeout
        self._eviction_ttl = eviction_ttl
        self._running = False

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch both background loops as concurrent asyncio tasks."""
        self._running = True
        await asyncio.gather(
            self._check_loop(),
            self._evict_loop(),
        )

    def stop(self) -> None:
        """Signal both loops to exit on their next tick."""
        self._running = False

    # ------------------------------------------------------------------
    # Internal loops
    # ------------------------------------------------------------------

    async def _check_loop(self) -> None:
        """Periodically calls NodeRegistry.check_timeouts()."""
        while self._running:
            await asyncio.sleep(self._CHECK_INTERVAL)
            now = time.time()
            dead = self._registry.check_timeouts(now, self._death_timeout)
            if dead:
                logger.debug("[GC] %d node(s) marked DEAD", len(dead))

    async def _evict_loop(self) -> None:
        """Periodically calls NodeRegistry.evict_dead_nodes()."""
        while self._running:
            await asyncio.sleep(self._EVICT_INTERVAL)
            now = time.time()
            evicted = self._registry.evict_dead_nodes(
                now, self._death_timeout, self._eviction_ttl
            )
            if evicted:
                logger.debug("[GC] %d node(s) evicted", len(evicted))
