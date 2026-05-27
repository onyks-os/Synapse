import os
from unittest.mock import MagicMock, patch

import pytest

from src.network.zmq_curve import (
    CurveAllowlist,
    _AllowedKeysProvider,
    _load_allowed_keys_from_file,
    apply_curve_client_socket_options,
    apply_curve_server_socket_options,
    configure_curve_authenticator,
    curve_is_enabled_from_env,
    get_required_env_key,
    load_curve_allowlist_from_env,
)


def test_load_allowed_keys_from_file(tmp_path):
    f = tmp_path / "allowed.txt"
    f.write_text("# Comment\nnode1 abcd\nefgh\n   \n")
    keys = _load_allowed_keys_from_file(str(f))
    assert keys == {b"abcd", b"efgh"}


def test_load_curve_allowlist_from_env_missing():
    # When SYNAPSE_CURVE_PEER_KEYS_FILE is not set
    assert load_curve_allowlist_from_env() is None


@patch.dict(
    os.environ,
    {
        "SYNAPSE_CURVE_PEER_KEYS_FILE": "dummy.txt",
        "SYNAPSE_CURVE_ZAP_DOMAIN": "test_domain",
    },
)
@patch("src.network.zmq_curve._load_allowed_keys_from_file")
def test_load_curve_allowlist_from_env_present(mock_load):
    mock_load.return_value = {b"key1"}
    allowlist = load_curve_allowlist_from_env()
    assert allowlist is not None
    assert allowlist.zap_domain == "test_domain"
    assert allowlist.allowed_client_public_keys == {b"key1"}


@patch.dict(
    os.environ, {"SYNAPSE_CURVE_PUBLICKEY": "pub", "SYNAPSE_CURVE_SECRETKEY": "sec"}
)
def test_curve_is_enabled_from_env():
    assert curve_is_enabled_from_env() is True


@patch.dict(
    os.environ, {"SYNAPSE_CURVE_PUBLICKEY": "pub", "SYNAPSE_CURVE_SECRETKEY": ""}
)
def test_curve_is_enabled_from_env_false():
    assert curve_is_enabled_from_env() is False


def test_get_required_env_key():
    with patch.dict(os.environ, {"MY_KEY": "val"}):
        assert get_required_env_key("MY_KEY") == "val"
        with pytest.raises(RuntimeError):
            get_required_env_key("MISSING_KEY")


def test_allowed_keys_provider():
    provider = _AllowedKeysProvider({b"key1", b"key2"})
    assert provider.callback("domain", b"key1") is True
    assert provider.callback("domain", b"key3") is False


def test_apply_curve_server_socket_options():
    mock_socket = MagicMock()
    apply_curve_server_socket_options(mock_socket, "pub", "sec", "domain")
    assert mock_socket.setsockopt.call_count == 5


def test_apply_curve_client_socket_options():
    mock_socket = MagicMock()
    apply_curve_client_socket_options(mock_socket, "srv_pub", "cli_pub", "cli_sec")
    assert mock_socket.setsockopt.call_count == 3


@patch("zmq.auth.thread.ThreadAuthenticator")
def test_configure_curve_authenticator(mock_auth_class):
    mock_ctx = MagicMock()
    mock_auth_instance = mock_auth_class.return_value

    allowlist = CurveAllowlist("domain", {b"key1"})
    auth = configure_curve_authenticator(mock_ctx, allowlist)

    mock_auth_class.assert_called_once_with(context=mock_ctx)
    mock_auth_instance.configure_curve_callback.assert_called_once()
    mock_auth_instance.start.assert_called_once()
    assert auth == mock_auth_instance
