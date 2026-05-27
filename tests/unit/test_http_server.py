from unittest.mock import MagicMock, patch

from src.core.corroboration import build_corroboration_strategy
from src.core.node_registry import NodeRegistry
from src.network.http_server import DashboardServer


def test_dashboard_server_init():
    registry = NodeRegistry(
        corroboration_strategy=build_corroboration_strategy("mad"), self_node_id="test"
    )
    server = DashboardServer(registry, port=9090, host="0.0.0.0")
    assert server._port == 9090
    assert server._host == "0.0.0.0"


@patch("src.network.http_server.waitress.serve")
@patch("src.network.http_server.threading.Thread")
def test_dashboard_server_start(mock_thread, mock_serve):
    registry = NodeRegistry(
        corroboration_strategy=build_corroboration_strategy("mad"), self_node_id="test"
    )
    server = DashboardServer(registry)

    mock_thread_instance = MagicMock()
    mock_thread.return_value = mock_thread_instance

    server.start()

    mock_thread.assert_called_once()
    kwargs = mock_thread.call_args[1]
    assert kwargs["target"] == mock_serve
    assert kwargs["daemon"] is True

    mock_thread_instance.start.assert_called_once()
