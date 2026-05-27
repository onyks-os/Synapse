# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-05-28

### Added

- **Active Connection Management:** Bounded peering via `SYNAPSE_MAX_CONNECTIONS` env var. Each node connects only to the first *X* discovered peers and keeps the rest in a reserve queue. When an active peer drops, the node automatically reconnects to a reserve candidate, keeping the target degree constant (`src/network/zmq_mesh.py`).
- **Self-Peering Filter:** Nodes now actively filter their own ZMQ bind address from the discovered peer list, preventing self-connections that would waste socket slots.
- **Native Benchmark Suite:** `tools/benchmark.py` — orchestrates up to 50 in-process simulated nodes (via `subprocess.Popen`) with static peer discovery, measures mesh convergence time and aggregate throughput. Run with `make benchmark` or `make benchmark NODES=N`. Validated results: 50 nodes converge in < 3s at 2476 msg/s (full-mesh); bounded mesh (X=8) achieves same convergence 17% faster with 84% fewer TCP sockets.
- **Pumba Network Chaos Integration:** Added `pumba` service to `docker/docker-compose.yml` under the `tools` profile. Injects configurable latency and packet loss onto sensor containers via `iproute2`. New Makefile targets: `make chaos-network` (start) and `make chaos-network-stop` (restore).
- **Glassmorphic Operator Dashboard:** Complete visual overhaul of `src/dashboard/index.html`. Full-screen Leaflet map with floating glassmorphic panels, neutral charcoal dark theme, H3 hex overlays colored by node status. Features: real-time client-side search and status filters (ALL / ALIVE / FAULTY / DEAD), click-to-pan map rows, SVG radial health gauge, Chaos Engineering command console with clipboard copy, retro event terminal with differential-polling log events. Telemetry values displayed as `°C`.
- **Kubernetes Helm Chart:** `charts/synapse/` — official Helm chart for Edge deployment on K3s/MicroK8s. Configurable via `values.yaml` (Caddy proxy, SQLite persistence via `hostPath`).
- **Continuous Deployment (CD):** `.github/workflows/cd.yml` — on every versioned tag, builds multi-architecture Docker images (amd64, arm64) and pushes to GHCR; publishes Python library to PyPI via OIDC Trusted Publishing (no stored secrets).
- **New Unit Tests:** `test_http_server.py`, `test_main_node.py`, `test_zeroconf_discovery.py`, `test_zmq_curve.py`, `test_zmq_mesh_limits.py` — total test suite now at **80 tests**.

### Changed

- **`make verify`:** Now runs ruff auto-fix + format, pytest, mypy, and the chaos smoke integration test in a single command. Ends with `"Verification complete. The codebase is ready for release."` only if all steps pass.
- **Makefile:** Rewrote from scratch with full target documentation, rootless Podman socket auto-detection, and `--remove-orphans` cleanup.
- **`docker-compose.yml`:** Added `chaos` and `pumba` services under the `tools` profile; suppressed compose orphan warnings via `PODMAN_COMPOSE_WARNING_LOGS=false`.
- **Documentation:** Updated `docs/USER_GUIDE.md`, `docs/DEPLOYMENT.md`, and `docs/ARCHITECTURE.md` to cover Active Connection Management, the benchmark suite, Pumba chaos injection, and the new dashboard.

### Fixed

- **Pumba flags:** Corrected the `netem` subcommand arguments — removed the invalid `-lo` flag and set proper `--duration`, `--delay`, and `--loss` parameters compatible with the `ghcr.io/alexei-led/pumba` image.
- **Chaos Monkey Docker dependency:** Moved the `docker` Python SDK to an optional dependency group (`chaos`) in `pyproject.toml` so the base image doesn't install it unconditionally.

## [0.1.0] - 2026-05-23

### Added

- **SQLite registry persistence:** optional `Synapse_REGISTRY_DB` path; node rows survive monitor restart; Prometheus-style counters remain **in-memory only** (`src/core/registry_store.py`).
- **Chaos CI smoke:** `tools/ci_chaos_smoke.py` and `.github/workflows/chaos-ci.yml` (weekly + `workflow_dispatch`) against Docker Compose.

### Changed

- **`NodeRegistry`:** wrapped mutations and reads with `threading.RLock`; `get_node` / `get_all` / `get_by_cell` return **copies** for safer cross-thread use with Flask.
- **P2P Mesh Architecture**: Transitioned from a central hub-and-spoke model to a symmetric P2P Mesh.
- **Unified Node**: Consolidated monitor and sensor daemons into a single `main_node.py` executable.
- **Peer Discovery**: Added `BeaconPeerProvider` (UDP Multicast) and `StaticPeerProvider`.
- **CurveZMQ**: Updated security model to support mutual authentication with a shared peer trust list.
- **Dashboard**: Localized dashboard per node with cross-mesh navigation sidebar.
- **Docker**: Consolidated into a single `Dockerfile.node`.

## 2026-03-25

### Changed

- **Documentation:** Aligned README, TDD v2.0, ARCHITECTURE, and THREAT_MODEL with **V1 complete** and **V2 core-complete** (stretch items documented as optional); replaced Italian ADRs with **English** ADR set and `docs/adr/README.md`; corroboration documented as **pluggable** leave-one-out (MAD / zscore / both).

### Added

- **Pluggable spatial corroboration:** `CORROBORATION_METHOD=mad` (default, modified Z / MAD), `zscore`, or `both` (AND). New module `src/core/corroboration.py` with `register_corroboration_method` for extensions. See `docs/TDD.md` §4.5–4.6 and `docs/FORMALISM.md` §3.
- **Operator endpoints**: `/live`, `/ready`, and **Prometheus** `/metrics`.
- **Versioned HTTP API**: `/api/v1/nodes` and `/api/v1/cells` (legacy `/api/*` aliases preserved).
- **Strong dashboard auth** (API key): `Synapse_DASHBOARD_API_KEY` protects `/api/v1/*` and `/metrics`.
- **Data channel hardening**: optional **ZeroMQ CURVE** with **client public key allowlist** loaded from a file.
- **Sensor identity guidance**: sensor node IDs can be provided via `NODE_ID` or `SENSOR_ID` (hostname fallback for Docker).
- **Schema versioning**: sensor payload now includes `schema_version` (listener supports missing as v1).

### Changed

- Dashboard UI now targets `/api/v1/*` and prompts for the API key client-side when needed.
- Docker images install runtime dependencies only (no `.[dev]` extras).

## 2026-03-24

This is the initial release of the Synapse system.

### Added

- **Daemon Architecture**: Created `Sensor` (`main_sensor.py`) and `Monitor` (`main_monitor.py`) daemons as the main components.
- **Network Communication**: Implemented a Pub/Sub communication pattern using ZeroMQ (`pyzmq`) for decoupled and scalable messaging.
- **Geospatial Indexing**: Integrated the H3 library (`h3`) to group sensors into hexagonal cells based on their geographic location (latitude/longitude).
- **Node Registry**: Created an in-memory registry (`NodeRegistry`) to track the status of all sensors in the network.
- **Lifecycle Management**: Implemented a state machine for nodes with `ALIVE`, `FAULTY`, and `DEAD` states.
- **Statistical Corroboration**: Developed a Z-score-based anomaly detection algorithm ("leave-one-out") to identify and flag sensors with unreliable data (`FAULTY`).
- **Garbage Collection**: Introduced a mechanism to mark inactive nodes as `DEAD` after a timeout and to permanently remove them after an eviction TTL.
- **Web Dashboard**: Created a simple web dashboard with Flask and an HTML interface (`dashboard/index.html`) to visualize the network status.
- **HTTP API**: Exposed a read-only JSON API (`/api/nodes`, `/api/cells`) to provide real-time data on the status of nodes and cells (legacy aliases; current versioned endpoints are under `/api/v1/*`).
- **Docker Deployment**: Provided `Dockerfile`s for `sensor` and `monitor` and a `docker-compose.yml` file for easy deployment and sensor scalability.
- **Testing**: Set up a test suite with `pytest`, including unit tests for core logic and integration tests for the network flow and API.
- **Chaos Engineering**: Developed a `chaos_monkey.py` tool to inject failures (container kills, corrupted data, anomalous values) and test the system's resilience.
