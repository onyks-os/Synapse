# User Guide

This document is a guide for the end-user or operator of the Synapse system. It explains how to view the network status and how to use the available tools to test the system.

## 1. System Purpose

Synapse is a system that monitors a network of devices (sensors). Its main purpose is to aggregate data from these sensors and, using their geographical location, determine whether the data sent by a sensor is reliable or anomalous compared to its neighbors. This provides an overview of the network's health and reliability.

## 2. Viewing the Dashboard

The easiest way to interact with the system is through the web dashboard provided by the `monitor` service.

### 2.1. Accessing the Dashboard

Once the system is running (see `DEPLOYMENT.md`), you can access the dashboard by opening your web browser and navigating to the monitor's address. If you are using the default Docker Compose configuration, the address is:

- **URL**: `http://localhost:8080`

If `Synapse_DASHBOARD_API_KEY` is configured, the UI will prompt for the key before it can fetch `/api/v1/*` and `/metrics`.

### 2.2. Interpreting the Interface

The dashboard displays an interactive map showing the H3 cells where sensors are present.

- **Hexagonal Cells**: Each hexagon on the map represents an H3 cell. The color of the cell indicates the aggregated status of the nodes within it.
  - **Green**: Most nodes in the cell are `ALIVE` and functioning correctly.
  - **Yellow/Orange**: There are `FAULTY` or `DEAD` nodes in the cell.
  - **Red**: Most nodes in the cell are unreliable.
- **Interaction**: By clicking on a cell, you can view detailed information about the nodes within it, such as their ID, status (`ALIVE`, `FAULTY`, `DEAD`), and the last value they sent.

The dashboard automatically updates at regular intervals to reflect the latest network status.

### 2.3. Corroboration tuning (operators)

How strictly neighbours are compared is controlled on the **monitor** (restart required after changes):

| Variable | Typical use |
| -------- | ----------- |
| `CORROBORATION_METHOD` | `mad` (**default**, robust to a few bad peers), `zscore` (classic mean/σ), or `both` (only if **both** rules fire — very conservative). |
| `ANOMALY_ZSCORE_THRESHOLD` | Higher → fewer `FAULTY` flags; lower → more sensitive. Same knob for all methods. |
| `CORROBORATION_MIN_PEERS` | Minimum `ALIVE` nodes in an H3 cell before corroboration runs. |
| `Synapse_REGISTRY_DB` | Optional SQLite path so **node rows** survive a monitor restart (counters still reset). See `docs/DEPLOYMENT.md`. |

Details: `docs/TDD.md` §4.5–4.6 and `docs/FORMALISM.md` §3.

### 2.4. Peering and Network Limits (operators)

To scale the P2P mesh network to a large number of nodes, you can configure active connection limits and discovery types:

| Variable | Typical use |
| -------- | ----------- |
| `SYNAPSE_MAX_CONNECTIONS` | Limit the maximum number of active TCP ZMQ SUB connections per node (default `0` = unlimited / full-mesh). A value of `8` to `12` is recommended for larger networks to prevent high CPU load and socket exhaustion. |
| `SYNAPSE_DISCOVERY` | Peer discovery protocol: `zeroconf` (default, mDNS), `beacon` (UDP Multicast), or `static` (CSV peer list). |

## 3. Testing Resilience with the Chaos Monkey

`chaos_monkey.py` is a command-line tool included with the project to test the robustness and resilience of the Synapse system. It simulates various types of failures that can occur in a real-world network.

### 3.1. How to Run It

The tool is located in the `tools/` directory and should be run from the project root while the Docker Compose environment is active.

Before running `chaos_monkey.py`, install the optional dependencies:

```bash
pip install ".[chaos]"
```

The basic syntax is:

```bash
python tools/chaos_monkey.py [OPTIONS]
```

### 3.2. Failure Modes

The Chaos Monkey has several modes (`--mode`):

- **`kill`**: Simulates a hardware crash or a sudden outage. It randomly selects one or more sensor containers and forcibly terminates them (`SIGKILL`). The Synapse system should mark these nodes as `DEAD` after the timeout.
- **`flood`**: Tests the Monitor's robustness by sending a high volume of malformed data (invalid JSON, missing fields, etc.) to its ZMQ endpoint. The Monitor should be able to discard these messages without crashing.
- **`anomaly`**: Tests the spatial corroboration logic. It sends well-formed messages but with deliberately extreme sensor values (e.g., `999.0` or `-50.0`). These nodes should be quickly identified and marked as `FAULTY` on the dashboard.
- **`both`**: Runs a combination of all failure modes (`kill`, `flood`, and `anomaly`) to simulate a complex chaotic scenario.

### 3.3. Intensity Levels

You can control the frequency and probability of failures with the `--intensity` option:

- **`low`**: Infrequent failures.
- **`medium`**: A moderate and steady level of failures (default).
- **`high`**: An intense and continuous attack on the system.

### 3.4. Usage Examples

**Example 1: Simulate occasional sensor crashes**
This command will attempt to terminate a sensor container at 10-second intervals, with a low probability.

```bash
python tools/chaos_monkey.py --mode kill --intensity low --interval 10
```

**Example 2: Aggressively test the corroboration logic**
This command will send a high number of anomalous values every 5 seconds. Watch the dashboard to see nodes turn `FAULTY`.

```bash
python tools/chaos_monkey.py --mode anomaly --intensity high --interval 5
```

**Example 3: Full stress test**
This command will run all types of attacks at medium intensity for a total duration of 2 minutes (120 seconds).

```bash
python tools/chaos_monkey.py --mode both --intensity medium --duration 120
```

## 4. Network Emulation Chaos Engineering (Pumba)

To test the resilience of the ZeroMQ P2P mesh network under physical network degradation, Synapse integrates **Pumba**, an industry-standard Docker chaos tool. 

Pumba intercepts the network stack of the nodes and injects network delay (latency with jitter) and packet loss via the Linux kernel's `tc` (Traffic Control) subsystem.

### 4.1. Network Chaos Mode Details
By default, the Pumba service is configured to:
* Target all sensor and main nodes matching the pattern `docker-node-`.
* Inject **200ms of latency** (with a `+-50ms` random jitter).
* Inject **15% packet loss** on all incoming and outgoing connections.
* Run network degradation blocks for **1 minute**, alternating with **2 minutes** of normal network operations (allowing you to witness dynamic self-healing and recovery).

### 4.2. Running Network Chaos

To start injecting network latency and packet loss into the running Docker Compose network:

```bash
make chaos-network
```

To stop the network chaos injection and immediately restore network stability:

```bash
make chaos-network-stop
```

During network degradation, you can monitor the node logs and the dashboard to observe how the active connection management, rate limiter, and corroboration engine handle packet drops and latency spikes gracefully!
