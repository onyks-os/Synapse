from unittest.mock import MagicMock, patch

import pytest

from src.network.peer_discovery import ZeroconfPeerProvider, _ZeroconfListener


@pytest.fixture
def provider():
    return ZeroconfPeerProvider(
        node_id="test-node",
        h3_cell="871f99cddffffff",
        zmq_port=5555,
        dashboard_port=8080,
    )


@pytest.mark.asyncio
async def test_zeroconf_start_stop(provider):
    with (
        patch("src.network.peer_discovery.Zeroconf") as mock_zc,
        patch("src.network.peer_discovery.ServiceBrowser") as mock_sb,
    ):
        await provider.start()

        mock_zc.assert_called_once()
        instance = mock_zc.return_value
        instance.register_service.assert_called_once()
        mock_sb.assert_called_once()

        # Test stop
        await provider.stop()
        instance.unregister_service.assert_called_once()
        instance.close.assert_called_once()


def test_zeroconf_listener_add_remove(provider):
    listener = _ZeroconfListener(provider)

    mock_zc = MagicMock()
    mock_info = MagicMock()
    mock_info.properties = {
        b"node_id": b"peer-node",
        b"h3_cell": b"871f99cddffffff",
        b"zmq_host": b"10.0.0.5",
        b"zmq_port": b"5555",
        b"dashboard_port": b"8080",
    }
    mock_info.addresses = []
    mock_info.port = 5555

    mock_zc.get_service_info.return_value = mock_info

    # Simulate adding service
    listener.add_service(
        mock_zc, "_synapse._tcp.local.", "Node-peer-node._synapse._tcp.local."
    )

    peers = provider.get_peer_info()
    assert len(peers) == 1
    assert peers[0]["node_id"] == "peer-node"
    assert peers[0]["h3_cell"] == "871f99cddffffff"
    assert peers[0]["dashboard_url"] == "http://10.0.0.5:8080"

    # Simulate removing service
    listener.remove_service(
        mock_zc, "_synapse._tcp.local.", "Node-peer-node._synapse._tcp.local."
    )

    peers_after = provider.get_peer_info()
    assert len(peers_after) == 0


def test_zeroconf_listener_ignore_self(provider):
    listener = _ZeroconfListener(provider)
    mock_zc = MagicMock()
    # If the discovered service has the same name as our service, it should be ignored
    listener.add_service(mock_zc, "_synapse._tcp.local.", provider.service_name)
    assert len(provider.get_peer_info()) == 0


def test_zeroconf_listener_missing_data(provider):
    listener = _ZeroconfListener(provider)
    mock_zc = MagicMock()
    mock_info = MagicMock()
    # Missing node_id in properties
    mock_info.properties = {
        b"h3_cell": b"871f99cddffffff",
    }
    mock_info.addresses = []
    mock_info.port = 5555
    mock_zc.get_service_info.return_value = mock_info

    listener.add_service(
        mock_zc, "_synapse._tcp.local.", "Node-broken._synapse._tcp.local."
    )
    assert len(provider.get_peer_info()) == 0
