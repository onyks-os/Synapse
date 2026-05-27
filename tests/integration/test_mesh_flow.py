import asyncio

import h3
import pytest
import zmq.asyncio

from src.core.node_registry import NodeRegistry
from src.network.peer_discovery import StaticPeerProvider
from src.network.zmq_mesh import MeshNode


@pytest.fixture
def zmq_context():
    ctx = zmq.asyncio.Context()
    yield ctx
    ctx.destroy(linger=0)


@pytest.mark.asyncio
async def test_mesh_node_corroboration_flow(zmq_context):
    """
    Simulate two mesh nodes locally connected.
    They should exchange PINGs and corroborate data.
    """
    reg1 = NodeRegistry(self_node_id="node-1")
    reg2 = NodeRegistry(self_node_id="node-2")

    cell = h3.latlng_to_cell(45.0, 10.0, 7)

    peer_provider1 = StaticPeerProvider("127.0.0.1:5556")
    peer_provider2 = StaticPeerProvider("127.0.0.1:5555")

    def sensor_payload_fn1():
        return {"value": 22.0, "lat": 45.0, "lon": 10.0}

    def sensor_payload_fn2():
        return {"value": 999.0, "lat": 45.0, "lon": 10.0}  # anomalous

    node1 = MeshNode(
        node_id="node-1",
        h3_cell=cell,
        bind_port=5555,
        peer_provider=peer_provider1,
        registry=reg1,
        ping_interval=0.1,
        sensor_payload_fn=sensor_payload_fn1,
        zscore_threshold=2.0,
        min_peers=2,  # Need 2 peers for corroboration in this test
        rate_limit=100.0,
        rate_burst=20,
        context=zmq_context,
    )

    node2 = MeshNode(
        node_id="node-2",
        h3_cell=cell,
        bind_port=5556,
        peer_provider=peer_provider2,
        registry=reg2,
        ping_interval=0.1,
        sensor_payload_fn=sensor_payload_fn2,
        zscore_threshold=2.0,
        min_peers=2,
        rate_limit=100.0,
        rate_burst=20,
        context=zmq_context,
    )

    # Start both
    await asyncio.gather(node1.start(), node2.start())

    try:
        # Give them time to exchange
        await asyncio.sleep(1.0)

        # reg1 should have node-2
        assert "node-2" in reg1.get_all()
        # reg2 should have node-1
        assert "node-1" in reg2.get_all()

    finally:
        node1.stop()
        node2.stop()
        node1.close()
        node2.close()
