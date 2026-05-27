<div align="center">
  <h1>Synapse</h1>
  <p><b>Brokerless IoT ingestion engine with spatial anomaly detection</b></p>

  <a href="https://github.com/onyks-os/Synapse/actions/workflows/cd.yml">
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT">
  </a>
</div>

Synapse is an experimental project exploring alternative Edge IoT topologies. It substitutes centralized message brokers like MQTT or Kafka with a true decentralized Symmetric P2P Mesh topology over ZeroMQ. Integrity checks and anomaly detection are processed locally on each node using H3 spatial grids.

![Synapse Dashboard Demo](https://raw.githubusercontent.com/onyks-os/Synapse/main/assets/gif/demo.gif)
*(Above: Synapse dashboard. Hexagons turn yellow or red when sensors report anomalies compared to their local peers).*

## Features

* **Symmetric P2P Mesh:** Fully decentralized communication via ZeroMQ, eliminating single points of failure.
* **Zero-Touch Provisioning (ZTP):** True plug-and-play local discovery powered by mDNS/Zeroconf (Bonjour), enabling seamless topology formation without hardcoded peers.
* **Active Connection Management:** Bounded peering limits (`SYNAPSE_MAX_CONNECTIONS`) with dynamic failover and self-peering filtering, allowing the mesh to scale to 50+ nodes with minimal CPU/socket overhead.
* **Spatial Anomaly Detection:** Real-time localized validation of sensor data using the Uber H3 indexing system and Median Absolute Deviation (MAD).
* **Automated TLS & Secure Proxying:** Every node is protected by a dedicated Caddy reverse proxy sidecar that terminates TLS locally and seamlessly routes traffic.
* **Continuous Deployment (CD):** GitHub Actions automatically build multi-architecture Docker images (amd64, arm64) to GHCR and securely publish the library to PyPI using OIDC Trusted Publishing.

## Quickstart

The easiest way to interact with the project is via the provided `Makefile`.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/onyks-os/Synapse.git
   cd Synapse
   ```

2. **Start the network:**
   ```bash
   make start
   ```
   This will build and deploy a simulated local mesh of 4 nodes, each alongside its secure Caddy proxy.

3. **Access the Dashboard:**
   Open a browser and navigate to `https://localhost:8441`. Bypass the local development certificate warning to view the dashboard securely.

4. **Stop the network:**
   ```bash
   make stop
   ```

## Orchestration & Deployment (Kubernetes)

For production environments on Edge hardware, deploying via Kubernetes (e.g., K3s, MicroK8s) is the recommended path. Synapse provides an official Helm chart.

1. **Review the Configuration:**
   Inspect the default parameters in `charts/synapse/values.yaml`. You can customize the Caddy proxy configuration and the SQLite persistence path (`hostPath`).

2. **Install the Chart:**
   ```bash
   helm install synapse-node ./charts/synapse
   ```

   The chart leverages a **DaemonSet** topology. This guarantees that exactly one Synapse instance (and its Caddy sidecar) is scheduled onto every physical edge node in your cluster, perfectly complementing the decentralized P2P architecture.

## Development and QA

The project requires Python 3.11+. The `Makefile` exposes all primary development commands.

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

### Verification and Testing

Run the full suite of unit tests, linting (Ruff), and type checking (Mypy) before a release:

```bash
make verify
```

### Build and Publish

To build Python distribution packages (sdist and wheel) locally:

```bash
make build
```

To manually test publishing:

```bash
make publish-testpypi
make publish-pypi
```

## Performance & Benchmarking

Synapse includes a native, container-overhead-free benchmark tool to test the network's convergence time and message throughput under intense stress tests.

To run the incremental stress test (scaling from 5 to 50 simulated nodes locally):
```bash
make benchmark
```

To run a fixed scale benchmark (e.g., 10 nodes):
```bash
make benchmark NODES=10
```

### Key Performance Metrics (N=50 nodes)

* **Full Mesh ($O(N^2)$ topology)**: Convergence in **2.9s** with a total throughput of **~2470 msg/sec**.
* **Limited Mesh ($X=8$ connection limit)**: Convergence in **2.39s** with **~400 msg/sec** (resulting in a **84% reduction** in socket/CPU overhead, keeping the mesh fully connected and resilient!).

## Chaos Engineering

Synapse includes a built-in Chaos Monkey to test the spatial corroboration and node eviction mechanisms under stress. 

To launch it manually against your local network:
```bash
make chaos
```

**Note:** This resilience is continuously verified. The GitHub Actions CI pipeline (`ci.yml`) automatically provisions a cluster, executes the chaos smoke test (`make test-chaos`), and ensures the mesh survives the attack on every commit.

![Chaos Monkey logs](https://raw.githubusercontent.com/onyks-os/Synapse/main/assets/img/chaos.png)
*(Above: Injecting malicious payloads via the `chaos_monkey.py` CLI triggers the local MAD corroboration, immediately flagging the rogue nodes as `FAULTY`).*

## License
Distributed under the MIT License.