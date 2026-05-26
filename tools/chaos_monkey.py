"""
tools/chaos_monkey.py

Dynamic Chaos Engineering CLI for Synapse V2.
Injects controlled failures into a running Docker Compose environment.

Usage:
  python tools/chaos_monkey.py [OPTIONS]

Modes:
  kill    — randomly kills node containers (simulates hardware crash)
  flood   — blasts malformed JSON payloads at a node via a rogue PUB socket
  anomaly — sends valid payloads with extreme sensor values to trigger FAULTY
  both    — interleaves kill and flood events

Intensity controls event probability and flood rate:
  low:    20% kill chance, 1 flood msg/s, 1 anomaly/s
  medium: 50% kill chance, 5 flood msgs/s, 3 anomaly/s
  high:   80% kill chance, 20 flood msgs/s, 10 anomaly/s
"""

import argparse
import asyncio
import json
import logging
import os
import random
import sys
import time

# Ensure src is importable when running directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import docker
import zmq
import zmq.asyncio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CHAOS %(levelname)s] %(message)s",
)
logger = logging.getLogger("chaos")


# ── Intensity presets ────────────────────────────────────────────────────────

INTENSITY = {
    "low": {"kill_prob": 0.20, "flood_rate": 1, "anomaly_rate": 1},
    "medium": {"kill_prob": 0.50, "flood_rate": 5, "anomaly_rate": 3},
    "high": {"kill_prob": 0.80, "flood_rate": 20, "anomaly_rate": 10},
}


# ── Kill mode ────────────────────────────────────────────────────────────────


def _get_sensor_containers(client: docker.DockerClient, target: str) -> list:
    """Return all running containers whose name contains `target`."""
    return [
        c
        for c in client.containers.list()
        if target in c.name and c.status == "running"
    ]


def chaos_kill(client: docker.DockerClient, kill_prob: float, target: str) -> None:
    """Randomly kill one sensor container with probability `kill_prob`."""
    if random.random() > kill_prob:
        return
    containers = _get_sensor_containers(client, target)
    if not containers:
        logger.warning("[kill] No running %r containers found.", target)
        return
    victim = random.choice(containers)
    logger.info("[kill] 💀 Killing container: %s", victim.name)
    victim.kill(signal="SIGKILL")


# ── Flood mode ───────────────────────────────────────────────────────────────

_FLOOD_TEMPLATES = [
    b"not-json-at-all!!!",
    json.dumps({"node_id": None, "status": "PING"}).encode(),
    json.dumps(
        {
            "node_id": "evil_node",
            "type": "flood",
            "timestamp": -1,
            "status": "PING",
            "h3_cell": "INVALID",
            "payload": {"value": float("inf"), "lat": 999, "lon": 999},
        }
    ).encode(),
    json.dumps({}).encode(),
    b"\xff\xfe malformed unicode \x00\x01",
]


async def chaos_flood(socket: zmq.asyncio.Socket, flood_rate: int) -> None:
    """Send `flood_rate` malformed messages per second."""
    for _ in range(flood_rate):
        msg = random.choice(_FLOOD_TEMPLATES)
        try:
            await socket.send(msg)
        except zmq.ZMQError:
            pass
    logger.info("[flood] 🌊 Sent %d malformed payloads", flood_rate)


# ── Anomaly mode ───────────────────────────────────────────────────────────────

# Fixed H3 cell and coordinates for anomaly injection.
# All anomaly nodes share the same cell so they meet the corroboration
# min_peers quorum — then the extreme value triggers FAULTY detection.
_ANOMALY_CELL = "871fb4670ffffff"  # Northern Italy, resolution 7
_ANOMALY_LAT = 45.464
_ANOMALY_LON = 9.190


async def chaos_anomaly(socket: zmq.asyncio.Socket, anomaly_rate: int) -> None:
    """
    Send `anomaly_rate` valid-looking payloads with extreme sensor values.
    These will be registered by NodeMonitor and flagged FAULTY by corroboration.
    """
    for i in range(anomaly_rate):
        extreme_value = random.choice([999.0, -50.0, 1e6, -273.15])
        payload = {
            "node_id": f"chaos_anomaly_{i}",
            "type": "chaos",
            "timestamp": time.time(),
            "status": "PING",
            "h3_cell": _ANOMALY_CELL,
            "payload": {
                "value": extreme_value,
                "lat": _ANOMALY_LAT,
                "lon": _ANOMALY_LON,
            },
        }
        try:
            await socket.send_json(payload)
        except zmq.ZMQError:
            pass
    logger.info(
        "[⚠️ anomaly] Injected %d extreme-value payloads into cell %s",
        anomaly_rate,
        _ANOMALY_CELL,
    )


# ── Main event loop ──────────────────────────────────────────────────────────


async def run(args: argparse.Namespace) -> None:
    preset = INTENSITY[args.intensity]
    kill_prob = preset["kill_prob"]
    flood_rate = preset["flood_rate"]
    anomaly_rate = preset["anomaly_rate"]

    # Docker client (only needed for kill/both modes)
    docker_client = None
    if args.mode in ("kill", "both"):
        try:
            docker_client = docker.from_env()
            docker_client.ping()
        except Exception as exc:
            logger.error("Cannot connect to Docker daemon: %s", exc)
            sys.exit(1)

    # ZMQ rogue PUB socket (needed for flood/anomaly/both modes)
    ctx = zmq.asyncio.Context()
    flood_socket = None
    peer_provider = None
    if args.mode in ("flood", "anomaly", "both"):
        flood_socket = ctx.socket(zmq.PUB)
        bind_port = args.port
        flood_socket.bind(f"tcp://0.0.0.0:{bind_port}")
        logger.info("[zmq] Rogue socket bound to 0.0.0.0:%d", bind_port)

        # Start beacon so mesh nodes connect their SUB sockets to us
        from src.network.peer_discovery import BeaconPeerProvider

        peer_provider = BeaconPeerProvider(
            node_id="chaos_monkey",
            h3_cell=_ANOMALY_CELL,
            zmq_port=bind_port,
            dashboard_port=0,
            zmq_host="0.0.0.0",
        )
        await peer_provider.start()
        await asyncio.sleep(1.0)  # wait for peers to connect

    start = time.time()
    event = 0

    logger.info(
        "🐒 Chaos Monkey started | mode=%s intensity=%s interval=%.1fs duration=%s",
        args.mode,
        args.intensity,
        args.interval,
        f"{args.duration}s" if args.duration > 0 else "∞",
    )

    try:
        while True:
            elapsed = time.time() - start
            if args.duration > 0 and elapsed >= args.duration:
                logger.info("Duration %.1fs elapsed — stopping.", args.duration)
                break

            event += 1
            logger.info("── Event #%d (%.1fs elapsed) ──", event, elapsed)

            if args.mode in ("kill", "both") and docker_client:
                chaos_kill(docker_client, kill_prob, args.target)

            if args.mode in ("flood", "both") and flood_socket:
                await chaos_flood(flood_socket, flood_rate)

            if args.mode in ("anomaly", "both") and flood_socket:
                await chaos_anomaly(flood_socket, anomaly_rate)

            await asyncio.sleep(args.interval)

    except asyncio.CancelledError:
        pass
    finally:
        if peer_provider:
            await peer_provider.stop()
        if flood_socket:
            flood_socket.close()
        ctx.destroy(linger=0)
        logger.info("Chaos Monkey stopped after %d events.", event)


# ── CLI ──────────────────────────────────────────────────────────────────────


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Synapse Chaos Monkey — dynamic fault injector",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--mode",
        choices=["kill", "flood", "anomaly", "both"],
        default="both",
        help="Chaos mode",
    )
    p.add_argument(
        "--intensity",
        choices=["low", "medium", "high"],
        default="medium",
        help="Fault intensity level",
    )
    p.add_argument(
        "--interval", type=float, default=5.0, help="Seconds between chaos events"
    )
    p.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Total run duration in seconds (0 = infinite)",
    )
    p.add_argument(
        "--target",
        default="node",
        help="Docker container name fragment to target for kills",
    )
    p.add_argument(
        "--host", default="localhost", help="(Unused in Mesh Mode) Node host"
    )
    p.add_argument(
        "--port", type=int, default=5599, help="ZMQ port to bind for anomaly injection"
    )
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(run(_parse()))
