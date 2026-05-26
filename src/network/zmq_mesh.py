"""
src/network/zmq_mesh.py

MeshNode: Symmetric P2P node combining ZMQ PUB (bind) and ZMQ SUB (connect).
Uses H3 spatial topics for distributed corroboration without a central broker.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time as _time
from collections.abc import Callable
from typing import TYPE_CHECKING

import h3
import zmq
import zmq.asyncio

from src.core import event_logger

if TYPE_CHECKING:
    from zmq.auth.thread import ThreadAuthenticator
from src.core.node_registry import NodeRegistry
from src.network.peer_discovery import PeerProvider
from src.network.zmq_curve import (
    apply_curve_client_socket_options,
    apply_curve_server_socket_options,
    configure_curve_authenticator,
    curve_is_enabled_from_env,
    get_required_env_key,
    load_curve_allowlist_from_env,
)

logger = logging.getLogger(__name__)


class _TokenBucket:
    """
    Simple token-bucket rate limiter (no external dependencies).

    Tokens are added at `rate` tokens/second up to `burst` capacity.
    Each `consume()` call tries to take one token.
    """

    def __init__(self, rate: float, burst: int) -> None:
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last = _time.monotonic()

    def consume(self) -> bool:
        """Try to consume one token. Returns True if allowed."""
        now = _time.monotonic()
        elapsed = now - self._last
        self._last = now
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


class MeshNode:
    def __init__(
        self,
        node_id: str,
        h3_cell: str,
        bind_port: int,
        peer_provider: PeerProvider,
        registry: NodeRegistry,
        ping_interval: float,
        sensor_payload_fn: Callable[[], dict],
        zscore_threshold: float,
        min_peers: int,
        rate_limit: float,
        rate_burst: int,
        context: zmq.asyncio.Context | None = None,
    ) -> None:
        self.node_id = node_id
        self._h3_cell = h3_cell
        self._bind_port = bind_port
        self._peer_provider = peer_provider
        self._registry = registry
        self._interval = ping_interval
        self._sensor_payload_fn = sensor_payload_fn
        self._zscore_threshold = zscore_threshold
        self._min_peers = min_peers

        self._bucket = _TokenBucket(rate_limit, rate_burst)
        self._ctx = context or zmq.asyncio.Context()
        self._pub_socket: zmq.asyncio.Socket | None = None
        self._sub_socket: zmq.asyncio.Socket | None = None
        self._running = False

        self._curve_enabled = curve_is_enabled_from_env()
        self._curve_auth: ThreadAuthenticator | None = None
        self._curve_allowlist = None
        self._curve_publickey: str | None = None
        self._curve_secretkey: str | None = None

        if self._curve_enabled:
            allowlist = load_curve_allowlist_from_env()
            if allowlist is None:
                raise RuntimeError(
                    "CURVE enabled but SYNAPSE_CURVE_PEER_KEYS_FILE is missing/empty."
                )
            self._curve_allowlist = allowlist
            self._curve_publickey = get_required_env_key("SYNAPSE_CURVE_PUBLICKEY")
            self._curve_secretkey = get_required_env_key("SYNAPSE_CURVE_SECRETKEY")

    async def start(self) -> None:
        self._pub_socket = self._ctx.socket(zmq.PUB)
        self._sub_socket = self._ctx.socket(zmq.SUB)

        if self._curve_enabled and self._curve_allowlist is not None:
            self._curve_auth = configure_curve_authenticator(
                ctx=self._ctx,
                allowlist=self._curve_allowlist,
            )
            # Configure PUB as Server
            apply_curve_server_socket_options(
                socket=self._pub_socket,
                server_publickey=self._curve_publickey or "",
                server_secretkey=self._curve_secretkey or "",
                zap_domain=self._curve_allowlist.zap_domain,
            )

        self._pub_socket.bind(f"tcp://0.0.0.0:{self._bind_port}")

        # Subscribe to spatial k-ring 1
        my_cells = [self._h3_cell] + list(h3.grid_disk(self._h3_cell, 1))
        for cell in my_cells:
            self._sub_socket.subscribe(cell.encode("utf-8"))

        # Connect to existing peers
        peers = await self._peer_provider.get_peers()
        for p in peers:
            await self._connect_peer(p)

        # Register for dynamic peer changes
        self._peer_provider.on_peer_change(self._on_peer_change)

        logger.info(
            f"[Node:{self.node_id}] Mesh started on port {self._bind_port}, cell {self._h3_cell}"
        )

        self._running = True

        loop = asyncio.get_running_loop()
        self._tasks = [
            loop.create_task(self._heartbeat_loop()),
            loop.create_task(self._receive_loop()),
        ]

    async def _connect_peer(self, host_port: str) -> None:
        sub_socket = self._sub_socket
        if sub_socket is None:
            logger.warning(
                f"SUB socket is not initialized, cannot connect to peer {host_port}."
            )
            return

        if self._curve_enabled:
            peer_pubkey = await self._peer_provider.get_peer_pubkey(host_port)
            if not peer_pubkey:
                logger.warning(
                    f"Missing public key for peer {host_port}, cannot connect SUB socket securely."
                )
                return
            apply_curve_client_socket_options(
                socket=sub_socket,
                server_publickey=peer_pubkey,
                client_publickey=self._curve_publickey or "",
                client_secretkey=self._curve_secretkey or "",
            )
        sub_socket.connect(f"tcp://{host_port}")
        logger.info(f"[Node:{self.node_id}] Connected SUB to {host_port}")

    def _on_peer_change(self, event: str, host_port: str, peer_node_id: str) -> None:
        if event == "joined":
            asyncio.create_task(self._connect_peer(host_port))
        elif event == "left":
            try:
                if self._sub_socket:
                    self._sub_socket.disconnect(f"tcp://{host_port}")
                    logger.info(
                        f"[Node:{self.node_id}] Disconnected SUB from {host_port}"
                    )
            except Exception as e:
                logger.error(f"Error disconnecting peer: {e}")

    def stop(self) -> None:
        self._running = False
        if self._curve_auth is not None:
            try:
                self._curve_auth.stop()
            except Exception:
                pass
        for t in getattr(self, "_tasks", []):
            t.cancel()

    async def _heartbeat_loop(self) -> None:
        while self._running and self._pub_socket is not None:
            try:
                payload = {
                    "schema_version": 1,
                    "node_id": self.node_id,
                    "type": "mesh",
                    "timestamp": _time.time(),
                    "status": "PING",
                    "h3_cell": self._h3_cell,
                    "payload": self._sensor_payload_fn(),
                }
                json_str = json.dumps(payload)
                msg = f"{self._h3_cell}|{json_str}".encode()
                await self._pub_socket.send(msg)
                logger.debug(f"[Node:{self.node_id}] PING sent (cell={self._h3_cell})")
            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")
            await asyncio.sleep(self._interval)

    async def _receive_loop(self) -> None:
        while self._running and self._sub_socket is not None:
            try:
                msg = await self._sub_socket.recv()

                parts = msg.decode("utf-8").split("|", 1)
                if len(parts) != 2:
                    continue

                cell, json_str = parts

                if not self._bucket.consume():
                    self._registry.inc_counter("rate_limited_total", 1)
                    event_logger.emit(
                        "RATE_LIMITED", node_id="", reason="token_bucket_exhausted"
                    )
                    await asyncio.sleep(0.01)
                    continue

                try:
                    payload = json.loads(json_str)
                except json.JSONDecodeError:
                    continue

                schema_version = payload.get("schema_version", 1)
                if not isinstance(schema_version, int) or schema_version != 1:
                    continue

                node_id = payload.get("node_id")
                if not isinstance(node_id, str) or not node_id:
                    continue

                if node_id == self.node_id:
                    continue  # self-filter

                self._registry.upsert(payload)

                faulty = self._registry.check_corroboration(
                    cell, self._zscore_threshold, self._min_peers
                )
                for f_id in faulty:
                    logger.warning(
                        "[Node:%s] Peer %s marked FAULTY (corroboration in cell %s)",
                        self.node_id,
                        f_id,
                        cell,
                    )

            except zmq.ZMQError as exc:
                if exc.errno == zmq.EAGAIN:
                    await asyncio.sleep(0)
                else:
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in receive loop: {e}")

    def close(self) -> None:
        if self._pub_socket:
            self._pub_socket.close()
            self._pub_socket = None
        if self._sub_socket:
            self._sub_socket.close()
            self._sub_socket = None
