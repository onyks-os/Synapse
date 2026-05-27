"""
ZeroMQ CURVE helpers.

Goal:
  - Enable CURVE server/client configuration from environment variables.
  - Allowlist authorized client public keys from a file.

Key format:
  PyZMQ CURVE public keys are expected as Z85-encoded ASCII strings.
  This module treats file lines / env values as Z85 strings and converts
  them to bytes (ASCII) for comparisons with pyzmq's authenticator callback.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import zmq

if TYPE_CHECKING:
    from zmq.auth.thread import ThreadAuthenticator

_DEFAULT_ZAP_DOMAIN: Final[str] = "*"


def _load_allowed_keys_from_file(path: str) -> set[bytes]:
    allowed: set[bytes] = set()
    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # We support both "public_key" and "node_id public_key" format.
            # Just extract the public key part.
            parts = line.split()
            key_str = parts[-1]
            allowed.add(key_str.encode("ascii"))
    return allowed


@dataclass(frozen=True)
class CurveAllowlist:
    zap_domain: str
    allowed_client_public_keys: set[bytes]


def load_curve_allowlist_from_env() -> CurveAllowlist | None:
    """
    If CURVE is enabled but allowlist is missing, return None.
    The caller may decide whether to fail fast.
    """
    allow_file = os.getenv("SYNAPSE_CURVE_PEER_KEYS_FILE", "").strip()
    if not allow_file:
        return None
    zap_domain = os.getenv("SYNAPSE_CURVE_ZAP_DOMAIN", _DEFAULT_ZAP_DOMAIN).strip()
    if not zap_domain:
        zap_domain = _DEFAULT_ZAP_DOMAIN
    allowed = _load_allowed_keys_from_file(allow_file)
    return CurveAllowlist(zap_domain=zap_domain, allowed_client_public_keys=allowed)


def curve_is_enabled_from_env() -> bool:
    pub = os.getenv("SYNAPSE_CURVE_PUBLICKEY", "").strip()
    sec = os.getenv("SYNAPSE_CURVE_SECRETKEY", "").strip()
    return bool(pub and sec)


def get_required_env_key(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


class _AllowedKeysProvider:
    """
    Credentials provider for ZMQ ZAP CURVE authentication.

    PyZMQ passes the z85-encoded bytes to callback(domain, z85_client_key).
    """

    def __init__(self, allowed_keys: set[bytes]) -> None:
        self._allowed = allowed_keys

    def callback(self, domain: str, client_key: bytes) -> bool:
        return client_key in self._allowed


def configure_curve_authenticator(
    ctx: zmq.asyncio.Context,
    allowlist: CurveAllowlist,
) -> ThreadAuthenticator:
    """
    Create and start a ThreadAuthenticator using a callback allowlist.
    """
    # Imported lazily: auth is only needed when CURVE is enabled.
    from zmq.auth.thread import ThreadAuthenticator

    auth = ThreadAuthenticator(context=ctx)
    provider = _AllowedKeysProvider(allowlist.allowed_client_public_keys)
    auth.configure_curve_callback(
        domain=allowlist.zap_domain,
        credentials_provider=provider,
    )
    auth.start()
    return auth


def apply_curve_server_socket_options(
    socket: zmq.Socket,
    server_publickey: str,
    server_secretkey: str,
    zap_domain: str,
) -> None:
    socket.setsockopt(zmq.CURVE_SERVER, 1)
    socket.setsockopt(zmq.CURVE_PUBLICKEY, server_publickey.encode("ascii"))
    socket.setsockopt(zmq.CURVE_SECRETKEY, server_secretkey.encode("ascii"))
    if zap_domain:
        socket.setsockopt(zmq.ZAP_DOMAIN, zap_domain.encode("ascii"))
        socket.setsockopt(zmq.ZAP_ENFORCE_DOMAIN, 1)


def apply_curve_client_socket_options(
    socket: zmq.Socket,
    server_publickey: str,
    client_publickey: str,
    client_secretkey: str,
) -> None:
    socket.setsockopt(zmq.CURVE_PUBLICKEY, client_publickey.encode("ascii"))
    socket.setsockopt(zmq.CURVE_SECRETKEY, client_secretkey.encode("ascii"))
    socket.setsockopt(zmq.CURVE_SERVERKEY, server_publickey.encode("ascii"))
