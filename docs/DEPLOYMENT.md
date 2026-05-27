# Deployment Guide

This document provides instructions for running the Synapse system, both in a local development environment and via Docker for a production-like environment.

## Prerequisites

- Python 3.11+
- Docker
- Docker Compose

## Registry persistence (optional)

Set **`Synapse_REGISTRY_DB`** on the monitor to a filesystem path (e.g. `/data/registry.sqlite`). The monitor will create parent directories and store **node rows** (id, status, last reading, H3 cell, etc.) in SQLite. **Prometheus counters** (`messages_total`, …) are **not** persisted and reset on restart. Mount a **volume** on that path in production so data survives container recreation.

## Option 1: Running via Docker (Recommended)

This is the preferred method for running the system, as it automatically handles the network and dependencies between services.

### 1. Starting the System

The `docker-compose.yml` file in the `docker/` directory orchestrates the startup of the monitor and a set of sensors.

To build the images and start all services in the background, run the following command from the project root:

```bash
docker-compose -f docker/docker-compose.yml up -d --build
```

This command will:

1. Build the Docker image for the `monitor` service (`Dockerfile.monitor`).
2. Build the Docker image for the `sensor` service (`Dockerfile.sensor`).
3. Start one `monitor` container.
4. Start `sensor` containers (with **Docker Compose v2** without Swarm, use `--scale sensor=N` — see §3 — the `deploy.replicas` field is mainly for Swarm stacks).
5. Create a virtual network `Synapse_net` to allow the containers to communicate.

### 2. Checking the Status

To view the logs of the running services:

```bash
# Show the monitor's logs
docker-compose -f docker/docker-compose.yml logs -f monitor

# Show the logs of all sensors
docker-compose -f docker/docker-compose.yml logs -f sensor
```

To see the running containers:

```bash
docker ps
```

You should see one `monitor` container and five `sensor` containers running.

### 3. Scaling the Number of Sensors

You can easily increase or decrease the number of running sensors using the `--scale` option.

For example, to start 20 sensors:

```bash
docker-compose -f docker/docker-compose.yml up -d --scale sensor=20
```

### 4. Stopping the System

To stop and remove all containers and the network, run:

```bash
docker-compose -f docker/docker-compose.yml down
```

## Option 2: Running Locally (Development)

This option is useful for developing and debugging individual components.

### 1. Setting up the Environment

1. **Create a virtual environment**:

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

2. **Install dependencies**:
    The project uses `hatchling` for build management. To install the project dependencies and development dependencies (like `pytest`), use:

    ```bash
    pip install -e .[dev]
    ```

### 2. Running the Components

You will need to run the monitor and at least one sensor in two separate terminals.

#### Terminal 1: Start the Monitor

```bash
python src/main_monitor.py
```

The monitor will start and begin listening on the ZMQ port (default `5555`) and serving the dashboard on the HTTP port (default `8080`).

#### Terminal 2: Start a Sensor

```bash
python src/main_sensor.py
```

The sensor will start sending pings to the monitor. You can start multiple instances of `main_sensor.py` in different terminals to simulate a larger network.

### 3. Configuration via Environment Variables

The settings for the components can be customized through environment variables. You can create a `.env` file in the project root (by copying from `.env.example`) to set them.

**Example `.env` file**:

```.env
# Monitor settings
DEATH_TIMEOUT=3.0
EVICTION_TTL=10.0
MONITOR_PORT=5555
DASHBOARD_PORT=8080

# Discovery settings (ZTP)
# Options: "zeroconf" (default, mDNS), "beacon" (UDP Multicast), "static" (CSV)
SYNAPSE_DISCOVERY=zeroconf

# Peering settings
# Max active connections per node (0 = unlimited / full-mesh)
SYNAPSE_MAX_CONNECTIONS=8

# Sensor settings
PING_INTERVAL=1.0
H3_RESOLUTION=7
```

### CURVEZMQ (data channel security) — key generation + Docker wiring

Synapse can secure the ZMQ channel with **CURVEZMQ** and a client public key **allowlist** loaded from a file.

1. Generate keys and per-sensor env files:

```bash
python tools/generate_curve_setup.py --count 5 --out-dir .curve-setup
```

This generates:

- `.curve-setup/server.env` (monitor/server keys + allowlist container path `/config/...`)
- `.curve-setup/allowed_client_publickeys.txt` (authorized sensor public keys)
- `.curve-setup/sensor-envs/<NODE_ID>.env` (sensor identity + client keys)

1. Wire `monitor` in `docker/docker-compose.yml`:
   - set `ZMQ_CURVE_SERVER_PUBLICKEY` and `ZMQ_CURVE_SERVER_SECRETKEY`
   - mount `.curve-setup/allowed_client_publickeys.txt` into the monitor container at:
     `/config/allowed_client_publickeys.txt`

2. Wire each `sensor` replica:
   - set `NODE_ID`
   - set `ZMQ_CURVE_CLIENT_PUBLICKEY` and `ZMQ_CURVE_CLIENT_SECRETKEY`

For Kubernetes, the typical mapping is:

- allowlist as a read-only ConfigMap volume
- per-sensor env from Secret/ConfigMap

### Ready-to-copy `docker-compose` snippet (with per-sensor identity)

Docker Compose (con `deploy.replicas` / `--scale`) in pratica duplica *lo stesso* env su più repliche, quindi per avere identità distinte e CURVE client keys diverse per ogni sensore conviene definire servizi separati:

1) Nel file `docker/docker-compose.yml` (o in un compose override) configura `monitor` con:

```yaml
services:
  monitor:
    env_file:
      - ../.curve-setup/server.env
    volumes:
      - ../.curve-setup/allowed_client_publickeys.txt:/config/allowed_client_publickeys.txt:ro
```

1) Definisci un servizio per ogni sensore, usando i file generati:

```yaml
services:
  sensor-0000:
    image: ghcr.io/<OWNER>/Synapse-sensor:latest
    env_file:
      - ../.curve-setup/sensor-envs/sensor_0000.env
    environment:
      - MONITOR_HOST=monitor
      - MONITOR_PORT=5555
      - PING_INTERVAL=1.0
      - H3_RESOLUTION=7
    networks:
      - Synapse_net

  sensor-0001:
    image: ghcr.io/<OWNER>/Synapse-sensor:latest
    env_file:
      - ../.curve-setup/sensor-envs/sensor_0001.env
    environment:
      - MONITOR_HOST=monitor
      - MONITOR_PORT=5555
      - PING_INTERVAL=1.0
      - H3_RESOLUTION=7
    networks:
      - Synapse_net
```

Nota: usa `sensor_0000`, `sensor_0001`, ... in base al `--node-id-template` usato nello script. L'esempio sopra assume il default `sensor_{i:04d}`.

## Option 3: Kubernetes via Helm (Edge Production)

For production deployment on physical edge clusters (e.g., K3s, MicroK8s), Synapse provides an official Helm chart implementing a DaemonSet architecture with a secure Caddy sidecar.

### 1. Architectural Overview

The Helm chart encapsulates:
- **Synapse Node**: The core daemon process.
- **Caddy Proxy Sidecar**: A reverse proxy container within the same Pod terminating TLS and exposing the dashboard securely over HTTPS.
- **ConfigMap**: Dynamic injection of the `Caddyfile`.
- **HostPath Persistence**: Local hardware storage mapping to persist the SQLite registry across Pod restarts.

### 2. Configuration and Values

Default parameters are stored in `charts/synapse/values.yaml`. Key configurations include:

- `image.repository` / `image.tag`: The Docker image to deploy (default: `ghcr.io/onyks-os/synapse-node:latest`).
- `persistence.hostPath`: The absolute path on the physical edge device where SQLite data is saved (default: `/var/lib/synapse/data`).
- `caddyfile`: The raw Caddy configuration string.

### 3. Installation

From the repository root, install the chart directly into your cluster:

```bash
helm install synapse-edge ./charts/synapse
```

To override values during installation:

```bash
helm install synapse-edge ./charts/synapse \
  --set persistence.hostPath=/opt/synapse/data \
  --set node.logFormat=text
```

### 4. Continuous Deployment (CD) and Chaos Engineering (CI)

The project includes an automated GitHub Actions pipeline to ensure production readiness:

- **Continuous Integration (`ci.yml`)**: On every push and pull request, the pipeline builds an isolated environment to run full static analysis (`mypy`, `ruff`), executes unit testing (`pytest`), and dynamically lints the Helm charts. Furthermore, it spins up a full Docker Compose topology and runs the `tools/ci_chaos_smoke.py` suite. This forcefully injects ZMQ anomalies into the network to guarantee the runtime resilience of the mesh before merging code.
- **Continuous Deployment (`cd.yml`)**: On every release, it automatically builds multi-architecture Docker images (`linux/amd64`, `linux/arm64`) using QEMU and pushes them to the GitHub Container Registry (GHCR). It also publishes Python packages to PyPI via OIDC Trusted Publishing.
