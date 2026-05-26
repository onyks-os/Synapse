"""
src/main_node.py

Unified entrypoint for the Synapse P2P Mesh node.
Starts the MeshNode, GarbageCollector, and DashboardServer.
"""

import asyncio
import logging
import os
import random
import signal
import socket

import h3
import zmq.asyncio

from src.core.corroboration import build_corroboration_strategy
from src.core.garbage_collector import GarbageCollector
from src.core.node_registry import NodeRegistry
from src.network.http_server import DashboardServer
from src.network.peer_discovery import build_peer_provider
from src.network.zmq_mesh import MeshNode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("Synapse.node")


def _random_coord(
    env_key_min: str, env_key_max: str, fallback_min: float, fallback_max: float
) -> float:
    lo = float(os.getenv(env_key_min, str(fallback_min)))
    hi = float(os.getenv(env_key_max, str(fallback_max)))
    return random.uniform(lo, hi)


def resolve_node_id() -> str:
    node_id = os.getenv("NODE_ID", "").strip()
    if not node_id:
        node_id = os.getenv("HOSTNAME", socket.gethostname()).strip()
    if not node_id:
        node_id = f"node-{random.randint(1000, 9999)}"
    return node_id


def resolve_coordinates() -> tuple[float, float]:
    lat_env = os.getenv("SENSOR_LAT")
    lon_env = os.getenv("SENSOR_LON")
    if lat_env is not None and lon_env is not None:
        return float(lat_env), float(lon_env)
    # Default fallback bounding box (Italy roughly)
    lat = _random_coord("LAT_MIN", "LAT_MAX", 44.0, 47.0)
    lon = _random_coord("LON_MIN", "LON_MAX", 6.0, 14.0)
    return lat, lon


async def main() -> None:
    # 1. Identity
    node_id = resolve_node_id()
    lat, lon = resolve_coordinates()
    resolution = int(os.getenv("H3_RESOLUTION", "7"))
    h3_cell = h3.latlng_to_cell(lat, lon, resolution)

    logger.info(
        f"Identity resolved: node_id={node_id}, cell={h3_cell}, lat={lat:.4f}, lon={lon:.4f}"
    )

    # 2. Configuration
    zmq_port = int(os.getenv("SYNAPSE_ZMQ_PORT", "5555"))
    dashboard_port = int(os.getenv("DASHBOARD_PORT", "8080"))
    dashboard_host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    external_url = os.getenv("EXTERNAL_DASHBOARD_URL", "")
    discovery = os.getenv("SYNAPSE_DISCOVERY", "beacon").strip().lower()

    death_timeout = float(os.getenv("DEATH_TIMEOUT", "3.0"))
    eviction_ttl = float(os.getenv("EVICTION_TTL", "10.0"))
    zscore_threshold = float(os.getenv("ANOMALY_ZSCORE_THRESHOLD", "2.0"))
    min_peers = int(os.getenv("CORROBORATION_MIN_PEERS", "3"))
    corro_method = os.getenv("CORROBORATION_METHOD", "mad").strip().lower()
    rate_limit = float(os.getenv("RATE_LIMIT_MSG_PER_SEC", "100"))
    rate_burst = int(os.getenv("RATE_LIMIT_BURST", "20"))
    ping_interval = float(os.getenv("PING_INTERVAL", "1.0"))
    registry_db = os.getenv("SYNAPSE_REGISTRY_DB", "").strip()
    sqlite_path = registry_db if registry_db else None

    # 3. Components
    registry = NodeRegistry(
        corroboration_strategy=build_corroboration_strategy(corro_method),
        sqlite_path=sqlite_path,
        self_node_id=node_id,
    )
    gc = GarbageCollector(registry, death_timeout, eviction_ttl)

    peer_provider = build_peer_provider(
        discovery=discovery,
        node_id=node_id,
        h3_cell=h3_cell,
        zmq_port=zmq_port,
        dashboard_port=dashboard_port,
        external_dashboard_url=external_url,
    )

    def sensor_payload_fn():
        # Simulated sensor logic
        base_val = float(os.getenv("SENSOR_VALUE", random.uniform(18.0, 35.0)))
        noise = random.uniform(-0.5, 0.5)
        return {
            "value": round(base_val + noise, 2),
            "lat": lat,
            "lon": lon,
        }

    ctx = zmq.asyncio.Context()
    mesh = MeshNode(
        node_id=node_id,
        h3_cell=h3_cell,
        bind_port=zmq_port,
        peer_provider=peer_provider,
        registry=registry,
        ping_interval=ping_interval,
        sensor_payload_fn=sensor_payload_fn,
        zscore_threshold=zscore_threshold,
        min_peers=min_peers,
        rate_limit=rate_limit,
        rate_burst=rate_burst,
        context=ctx,
    )

    dashboard = DashboardServer(
        registry,
        port=dashboard_port,
        host=dashboard_host,
        peer_info_fn=peer_provider.get_peer_info,
        identity={"node_id": node_id, "h3_cell": h3_cell, "lat": lat, "lon": lon},
    )

    # 4. Orchestration
    dashboard.start()

    loop = asyncio.get_running_loop()

    def _shutdown(sig: signal.Signals) -> None:
        logger.info("Received %s — shutting down gracefully…", sig.name)
        mesh.stop()
        gc.stop()
        asyncio.create_task(peer_provider.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig)

    logger.info("Starting PeerProvider...")
    await peer_provider.start()

    logger.info("Starting MeshNode and GC...")
    await asyncio.gather(
        mesh.start(),
        gc.start(),
    )


if __name__ == "__main__":
    asyncio.run(main())
