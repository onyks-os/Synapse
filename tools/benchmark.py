import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlopen

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("benchmark")


def get_node_count(port: int) -> int:
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/v1/nodes", timeout=1.0) as resp:
            data = json.loads(resp.read().decode())
            return len(data)
    except Exception:
        return 0


async def wait_for_convergence(
    nodes_count: int, http_ports: list[int], timeout: float = 45.0
) -> float:
    start_time = time.time()
    max_conn_env = os.getenv("SYNAPSE_MAX_CONNECTIONS")
    max_conn = int(max_conn_env) if max_conn_env else 0
    expected = nodes_count - 1
    if max_conn > 0:
        expected = min(expected, max_conn)

    while time.time() - start_time < timeout:
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=min(32, len(http_ports))) as pool:
            counts = await asyncio.gather(
                *[loop.run_in_executor(pool, get_node_count, p) for p in http_ports]
            )

        # We need all nodes to see 'expected' other nodes.
        if all(c >= expected for c in counts):
            return time.time() - start_time

        await asyncio.sleep(0.5)

    logger.error(f"Timeout reached. Last counts: {counts}")
    return -1.0  # Timeout


def get_metrics(port: int) -> int:
    try:
        with urlopen(f"http://127.0.0.1:{port}/metrics", timeout=1.0) as resp:
            text = resp.read().decode()
            for line in text.splitlines():
                if line.startswith("Synapse_messages_total "):
                    return int(line.split()[1])
    except Exception:
        pass
    return 0


class Benchmark:
    def __init__(self, n: int, silent: bool = False):
        self.n = n
        self.silent = silent
        self.procs = []
        self.http_ports = []

    def log(self, msg: str):
        if not self.silent:
            logger.info(msg)

    def start(self):
        peers_list = ",".join([f"127.0.0.1:{16000 + i}" for i in range(self.n)])
        self.log(f"Starting {self.n} nodes locally (Static Discovery)...")
        for i in range(self.n):
            zmq_port = 16000 + i
            http_port = 19000 + i
            self.http_ports.append(http_port)
            env = os.environ.copy()
            env["NODE_ID"] = f"bench-node-{i}"
            env["SYNAPSE_ZMQ_PORT"] = str(zmq_port)
            env["DASHBOARD_PORT"] = str(http_port)
            env["SYNAPSE_DISCOVERY"] = "static"
            env["SYNAPSE_PEERS"] = peers_list
            env["PING_INTERVAL"] = "1.0"
            env["RATE_LIMIT_MSG_PER_SEC"] = "10000"
            env["SYNAPSE_LOG_FORMAT"] = "json"
            env["SENSOR_LAT"] = "45.0"
            env["SENSOR_LON"] = "9.0"

            log_file = open(f"/tmp/bench_node_{i}.log", "w")
            p = subprocess.Popen(
                [sys.executable, "-m", "src.main_node"],
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            self.procs.append(p)

    def stop(self):
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            p.wait()

    async def run(self):
        self.start()
        try:
            self.log(
                f"Waiting for full mesh convergence ({self.n}x{self.n} connections)..."
            )
            conv_time = await wait_for_convergence(
                self.n, self.http_ports, timeout=45.0
            )
            if conv_time < 0:
                self.log("Network failed to converge after 45s.")
                return False, -1.0, 0.0
            self.log(f"Mesh converged in {conv_time:.2f}s.")

            # Measure throughput and message latency simulation
            self.log("Stabilizing and sampling throughput over 5 seconds...")
            await asyncio.sleep(2.0)

            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor() as pool:
                m1 = await asyncio.gather(
                    *[
                        loop.run_in_executor(pool, get_metrics, p)
                        for p in self.http_ports
                    ]
                )

            await asyncio.sleep(5.0)

            with ThreadPoolExecutor() as pool:
                m2 = await asyncio.gather(
                    *[
                        loop.run_in_executor(pool, get_metrics, p)
                        for p in self.http_ports
                    ]
                )

            total_msgs = sum(m2) - sum(m1)
            msgs_per_sec = total_msgs / 5.0
            self.log(f"Throughput: {msgs_per_sec:.2f} msg/s across cluster")
            return True, conv_time, msgs_per_sec

        finally:
            self.stop()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--nodes", type=int, default=0, help="Number of nodes for a fixed run"
    )
    args = parser.parse_args()

    if args.nodes > 0:
        b = Benchmark(args.nodes, silent=False)
        ok, c, th = await b.run()
        sys.exit(0 if ok else 1)
    else:
        logger.setLevel(logging.WARNING)  # Silence info logs
        print(
            f"{'Nodes':<10} | {'Convergence (s)':<20} | {'Throughput (msg/s)':<20} | {'Status'}"
        )
        print("-" * 80)
        # 10, 20, 30, 40, 50, 75, 100
        for nodes in [5, 10, 20, 30, 40, 50]:
            b = Benchmark(nodes, silent=True)
            ok, c, th = await b.run()
            status = "PASS" if ok else "FAIL (Timeout)"
            c_str = f"{c:.2f}" if ok else "---"
            th_str = f"{th:.2f}" if ok else "---"
            print(f"{nodes:<10} | {c_str:<20} | {th_str:<20} | {status}")
            if not ok:
                print("Benchmark failed to converge, stopping incremental stress test.")
                break


if __name__ == "__main__":
    asyncio.run(main())
