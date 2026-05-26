import asyncio

import pytest

from src.network.peer_discovery import BeaconPeerProvider, StaticPeerProvider


@pytest.mark.asyncio
async def test_static_peer_provider():
    provider = StaticPeerProvider("127.0.0.1:5555:key1, 192.168.1.2:5556:key2")
    peers = await provider.get_peers()
    assert len(peers) == 2
    assert "127.0.0.1:5555" in peers
    assert "192.168.1.2:5556" in peers

    pubkey = await provider.get_peer_pubkey("127.0.0.1:5555")
    assert pubkey == "key1"


@pytest.mark.asyncio
async def test_beacon_peer_provider():
    provider = BeaconPeerProvider(
        node_id="test-node",
        h3_cell="871fb4670ffffff",
        zmq_port=5555,
        dashboard_port=8080,
        public_key="my-key",
        beacon_interval=0.1,
        beacon_timeout=0.5,
        multicast_group="127.0.0.1",  # use localhost for test
        multicast_port=5679,
        zmq_host="127.0.0.1",
    )

    events = []

    def on_change(event, host_port, peer_id):
        events.append((event, host_port, peer_id))

    provider.on_peer_change(on_change)

    await provider.start()

    try:
        await asyncio.sleep(0.3)
        # Should discover itself (if multicast loopback works) or just run without error
    finally:
        await provider.stop()
