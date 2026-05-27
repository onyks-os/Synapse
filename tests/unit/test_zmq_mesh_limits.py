import asyncio

import pytest
import zmq.asyncio

from src.core.corroboration import build_corroboration_strategy
from src.core.node_registry import NodeRegistry
from src.network.zmq_mesh import MeshNode


class MockPeerProvider:
    def __init__(self, initial_peers=None):
        self._peers = list(initial_peers or [])
        self._callbacks = []

    async def get_peers(self) -> list[str]:
        return self._peers

    async def get_peer_pubkey(self, host_port: str) -> str | None:
        return None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def on_peer_change(self, callback) -> None:
        self._callbacks.append(callback)

    def trigger_join(self, host_port: str, node_id: str):
        if host_port not in self._peers:
            self._peers.append(host_port)
        for cb in self._callbacks:
            cb("joined", host_port, node_id)

    def trigger_leave(self, host_port: str, node_id: str):
        if host_port in self._peers:
            self._peers.remove(host_port)
        for cb in self._callbacks:
            cb("left", host_port, node_id)


@pytest.mark.asyncio
async def test_mesh_connection_limits():
    registry = NodeRegistry(build_corroboration_strategy("mad"))
    provider = MockPeerProvider(
        ["127.0.0.1:16001", "127.0.0.1:16002", "127.0.0.1:16003"]
    )

    # Node under test with limit = 2
    mesh = MeshNode(
        node_id="test-node",
        h3_cell="871f9b863ffffff",
        bind_port=16000,
        peer_provider=provider,
        registry=registry,
        ping_interval=1.0,
        sensor_payload_fn=lambda: {"value": 20.0},
        zscore_threshold=2.0,
        min_peers=2,
        rate_limit=100.0,
        rate_burst=10,
        context=zmq.asyncio.Context(),
        max_connections=2,
    )

    try:
        await mesh.start()

        # 1. Verify that only 2 connections are active initially out of 3 discovered
        assert len(mesh._active_connections) == 2
        assert len(mesh._discovered_peers) == 3

        # Record which ones were connected
        connected_initially = list(mesh._active_connections)
        unconnected_initially = [
            p for p in mesh._discovered_peers if p not in connected_initially
        ]
        assert len(unconnected_initially) == 1
        reserve_peer = unconnected_initially[0]

        # 2. Simulate new peer joining
        provider.trigger_join("127.0.0.1:16004", "node-4")
        assert len(mesh._discovered_peers) == 4
        # Since we are already at max_connections = 2, we shouldn't connect to node-4
        assert len(mesh._active_connections) == 2
        assert "127.0.0.1:16004" not in mesh._active_connections

        # 3. Simulate one of the initially connected peers leaving
        leaving_peer = connected_initially[0]
        remaining_initially_connected = connected_initially[1]

        provider.trigger_leave(leaving_peer, "node-leaving")

        # Give asyncio tasks a tick to execute the background reconnect
        await asyncio.sleep(0.05)

        # The leaving peer should be removed
        assert leaving_peer not in mesh._active_connections
        assert leaving_peer not in mesh._discovered_peers

        # Grado di connessione should still be 2 due to failover connecting to one of the reserve peers
        assert len(mesh._active_connections) == 2
        assert remaining_initially_connected in mesh._active_connections

        # At least one of the reserve peers (either node-4 or the original reserve_peer) must now be connected
        active_reserves = [
            p
            for p in ["127.0.0.1:16004", reserve_peer]
            if p in mesh._active_connections
        ]
        assert len(active_reserves) == 1

    finally:
        mesh.stop()
        mesh.close()


@pytest.mark.asyncio
async def test_mesh_self_connection_filtering():
    registry = NodeRegistry(build_corroboration_strategy("mad"))
    # The provider includes the node's own address (127.0.0.1:16000)
    provider = MockPeerProvider(["127.0.0.1:16000", "127.0.0.1:16001"])

    mesh = MeshNode(
        node_id="test-node",
        h3_cell="871f9b863ffffff",
        bind_port=16000,
        peer_provider=provider,
        registry=registry,
        ping_interval=1.0,
        sensor_payload_fn=lambda: {"value": 20.0},
        zscore_threshold=2.0,
        min_peers=2,
        rate_limit=100.0,
        rate_burst=10,
        context=zmq.asyncio.Context(),
        max_connections=0,  # no limits
    )

    try:
        await mesh.start()

        # Verify that own address was NOT added as an active connection
        assert "127.0.0.1:16000" not in mesh._active_connections
        assert "127.0.0.1:16000" not in mesh._discovered_peers

        # Verify that other peer WAS connected successfully
        assert "127.0.0.1:16001" in mesh._active_connections
        assert "127.0.0.1:16001" in mesh._discovered_peers

        # Verify that dynamic self-connection joins are also filtered out
        provider.trigger_join("127.0.0.1:16000", "test-node")
        assert "127.0.0.1:16000" not in mesh._active_connections
        assert "127.0.0.1:16000" not in mesh._discovered_peers

    finally:
        mesh.stop()
        mesh.close()
