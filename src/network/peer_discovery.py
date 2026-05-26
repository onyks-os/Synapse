import asyncio
import json
import logging
import os
import socket
import struct
import time
from collections.abc import Callable
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class PeerProvider(Protocol):
    async def get_peers(self) -> list[str]: ...
    async def get_peer_pubkey(self, host_port: str) -> str | None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def on_peer_change(self, callback: Callable[[str, str, str], None]) -> None:
        """callback(event, host_port, node_id) — event: 'joined' | 'left'"""
        ...

    def get_peer_info(self) -> list[dict]: ...


class StaticPeerProvider:
    def __init__(self, peers_csv: str):
        # Format can be host:port or host:port:pubkey
        self._peers_raw = [p.strip() for p in peers_csv.split(",") if p.strip()]
        logger.info(f"StaticPeerProvider initialized with peers: {self._peers_raw}")

    async def get_peers(self) -> list[str]:
        # Return host_port
        return [
            p.rsplit(":", 1)[0] if p.count(":") == 2 else p for p in self._peers_raw
        ]

    async def get_peer_pubkey(self, host_port: str) -> str | None:
        for p in self._peers_raw:
            parts = p.split(":")
            if len(parts) == 3 and f"{parts[0]}:{parts[1]}" == host_port:
                return parts[2]
            elif len(parts) == 2 and p == host_port:
                return None
        return None

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def on_peer_change(self, callback: Callable[[str, str, str], None]) -> None:
        pass

    def get_peer_info(self) -> list[dict]:
        res = []
        for p in self._peers_raw:
            parts = p.split(":")
            if len(parts) >= 2:
                res.append(
                    {
                        "node_id": f"static-{parts[0]}",
                        "h3_cell": "unknown",
                        "dashboard_url": None,
                    }
                )
        return res


class BeaconPeerProvider:
    def __init__(
        self,
        node_id: str,
        h3_cell: str,
        zmq_port: int,
        dashboard_port: int,
        external_dashboard_url: str = "",
        public_key: str = "",
        beacon_interval: float = 2.0,
        beacon_timeout: float = 6.0,
        multicast_group: str = "239.255.77.77",
        multicast_port: int = 5670,
        zmq_host: str = "0.0.0.0",
    ):
        self.node_id = node_id
        self.h3_cell = h3_cell
        self.zmq_port = zmq_port
        self.dashboard_port = dashboard_port
        self.external_dashboard_url = external_dashboard_url
        self.public_key = public_key
        self.beacon_interval = beacon_interval
        self.beacon_timeout = beacon_timeout
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port

        self.zmq_host = self._get_local_ip() if zmq_host == "0.0.0.0" else zmq_host

        self._peers: dict[str, dict[str, Any]] = {}
        self._callbacks: list[Callable[[str, str, str], None]] = []
        self._running = False
        self._tx_task: asyncio.Task | None = None
        self._rx_task: asyncio.Task | None = None
        self._expiry_task: asyncio.Task | None = None

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    async def get_peers(self) -> list[str]:
        return list(self._peers.keys())

    def on_peer_change(self, callback: Callable[[str, str, str], None]) -> None:
        self._callbacks.append(callback)

    def _notify_callbacks(self, event: str, host_port: str, node_id: str) -> None:
        for cb in self._callbacks:
            try:
                cb(event, host_port, node_id)
            except Exception as e:
                logger.error(f"Error in peer callback: {e}")

    async def start(self) -> None:
        self._running = True
        loop = asyncio.get_running_loop()
        self._tx_task = loop.create_task(self._beacon_tx_loop())
        self._rx_task = loop.create_task(self._beacon_rx_loop())
        self._expiry_task = loop.create_task(self._expiry_loop())
        logger.info(
            f"BeaconPeerProvider started (group={self.multicast_group}:{self.multicast_port})"
        )

    async def stop(self) -> None:
        self._running = False
        if self._tx_task:
            self._tx_task.cancel()
        if self._rx_task:
            self._rx_task.cancel()
        if self._expiry_task:
            self._expiry_task.cancel()
        logger.info("BeaconPeerProvider stopped")

    async def _beacon_tx_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

        payload = {
            "node_id": self.node_id,
            "h3_cell": self.h3_cell,
            "zmq_host": self.zmq_host,
            "zmq_port": self.zmq_port,
            "dashboard_port": self.dashboard_port,
            "external_dashboard_url": self.external_dashboard_url,
            "public_key": self.public_key,
        }
        data = json.dumps(payload).encode("utf-8")

        while self._running:
            try:
                sock.sendto(data, (self.multicast_group, self.multicast_port))
            except Exception as e:
                logger.error(f"Failed to send beacon: {e}")
            await asyncio.sleep(self.beacon_interval)
        sock.close()

    async def _beacon_rx_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

        sock.bind(("", self.multicast_port))

        mreq = struct.pack(
            "4sl", socket.inet_aton(self.multicast_group), socket.INADDR_ANY
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setblocking(False)

        loop = asyncio.get_running_loop()

        while self._running:
            try:
                data, addr = await loop.sock_recvfrom(sock, 1024)
                try:
                    payload = json.loads(data.decode("utf-8"))
                    peer_node_id = payload.get("node_id")

                    if not peer_node_id or peer_node_id == self.node_id:
                        continue

                    zmq_host = payload.get("zmq_host")
                    if not zmq_host or zmq_host == "0.0.0.0" or zmq_host == "127.0.0.1":
                        zmq_host = addr[0]

                    zmq_port = payload.get("zmq_port")
                    host_port = f"{zmq_host}:{zmq_port}"

                    is_new = host_port not in self._peers

                    self._peers[host_port] = {
                        "node_id": peer_node_id,
                        "h3_cell": payload.get("h3_cell"),
                        "dashboard_port": payload.get("dashboard_port"),
                        "external_dashboard_url": payload.get(
                            "external_dashboard_url", ""
                        ),
                        "public_key": payload.get("public_key"),
                        "last_seen": time.time(),
                        "zmq_host": zmq_host,
                        "zmq_port": zmq_port,
                    }

                    if is_new:
                        logger.info(
                            f"Discovered new peer: {peer_node_id} at {host_port}"
                        )
                        self._notify_callbacks("joined", host_port, peer_node_id)

                except json.JSONDecodeError:
                    pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error receiving beacon: {e}")
                await asyncio.sleep(1)
        sock.close()

    async def _expiry_loop(self) -> None:
        while self._running:
            now = time.time()
            to_remove = []
            for host_port, info in self._peers.items():
                if now - info["last_seen"] > self.beacon_timeout:
                    to_remove.append((host_port, info["node_id"]))

            for host_port, peer_node_id in to_remove:
                del self._peers[host_port]
                logger.info(f"Peer expired: {peer_node_id} at {host_port}")
                self._notify_callbacks("left", host_port, peer_node_id)

            await asyncio.sleep(self.beacon_interval)

    async def get_peer_pubkey(self, host_port: str) -> str | None:
        info = self._peers.get(host_port)
        return info["public_key"] if info else None

    def get_peer_info(self) -> list[dict]:
        res = []
        for _host_port, info in self._peers.items():
            dash_url = info.get("external_dashboard_url")
            if not dash_url and info.get("dashboard_port"):
                dash_url = f"http://{info['zmq_host']}:{info['dashboard_port']}"
            res.append(
                {
                    "node_id": info["node_id"],
                    "h3_cell": info["h3_cell"],
                    "dashboard_url": dash_url,
                }
            )
        return res


def build_peer_provider(discovery: str, **kwargs) -> PeerProvider:
    if discovery == "static":
        return StaticPeerProvider(peers_csv=os.getenv("SYNAPSE_PEERS", ""))

    return BeaconPeerProvider(
        node_id=kwargs.get("node_id", "unknown"),
        h3_cell=kwargs.get("h3_cell", ""),
        zmq_port=kwargs.get("zmq_port", 5555),
        dashboard_port=kwargs.get("dashboard_port", 8080),
        external_dashboard_url=kwargs.get("external_dashboard_url", ""),
        public_key=os.getenv("SYNAPSE_CURVE_PUBLICKEY", ""),
        beacon_interval=float(os.getenv("SYNAPSE_BEACON_INTERVAL", "2.0")),
        beacon_timeout=float(os.getenv("SYNAPSE_BEACON_TIMEOUT", "6.0")),
        multicast_group=os.getenv("SYNAPSE_BEACON_GROUP", "239.255.77.77"),
        multicast_port=int(os.getenv("SYNAPSE_BEACON_PORT", "5670")),
        zmq_host=kwargs.get("zmq_host", "0.0.0.0"),
    )
