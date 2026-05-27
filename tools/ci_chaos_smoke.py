#!/usr/bin/env python3
"""
tools/ci_chaos_smoke.py

CI-oriented smoke test: verify the monitor survives a burst of garbage on the
ZMQ ingest port while continuing to serve /ready.

Intended to run against ``docker compose`` with ports 8080/5555 published
(e.g. GitHub Actions). No Docker SDK required.

Usage:
  python tools/ci_chaos_smoke.py [--http URL] [--zmq tcp://host:5555] [--wait 60]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import urllib.error
import urllib.request

import zmq.asyncio

_BAD_MESSAGES = [
    b"not-json-at-all",
    b"\x00\xff garbage",
    b"{",
]


def _wait_ready(url: str, timeout_s: float, interval: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_err: str | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return
                last_err = f"HTTP {resp.status}"
        except urllib.error.URLError as e:
            last_err = str(e.reason) if hasattr(e, "reason") else str(e)
        time.sleep(interval)
    raise SystemExit(f"/ready never became OK ({last_err}) after {timeout_s}s")


async def _flood_zmq(endpoint: str, rounds: int) -> None:
    ctx = zmq.asyncio.Context()
    sock = ctx.socket(zmq.PUB)
    try:
        sock.connect(endpoint)
        await asyncio.sleep(0.15)
        for _ in range(rounds):
            for raw in _BAD_MESSAGES:
                try:
                    await sock.send(raw)
                except Exception:
                    pass
            await asyncio.sleep(0.01)
    finally:
        sock.close(linger=0)
        ctx.destroy(linger=0)


def main() -> None:
    p = argparse.ArgumentParser(description="Chaos smoke: ZMQ garbage + /ready")
    p.add_argument(
        "--http",
        default="http://127.0.0.1:8080/ready",
        help="Readiness URL",
    )
    p.add_argument(
        "--zmq",
        default="tcp://127.0.0.1:5555",
        help="Monitor SUB endpoint (PUB connects here)",
    )
    p.add_argument(
        "--wait", type=float, default=90.0, help="Seconds to wait for /ready"
    )
    p.add_argument("--rounds", type=int, default=40, help="Garbage burst rounds")
    args = p.parse_args()

    _wait_ready(args.http, args.wait)
    asyncio.run(_flood_zmq(args.zmq, args.rounds))
    _wait_ready(args.http, 30.0)
    print(
        "ci_chaos_smoke: OK (monitor stayed ready after ZMQ garbage burst)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
