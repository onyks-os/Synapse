# Synapse System Architecture

This document describes the high-level architecture of the Synapse system, its main components, and data flows.

## 1. Overview

Synapse monitors many IoT sensors using a **Symmetric P2P Mesh architecture**. There are no central brokers or monitors. Every participant in the network is an identical **Node** that performs data sensing, data ingestion, spatial corroboration, and serves its own localized UI dashboard.

The system is designed to be *edge-first*, where the logic of geographic proximity is fundamental to validating data and limiting network traffic.

## 2. Components

### 2.1. Node (`main_node.py`)

- **Responsibilities**:
  - Generate a unique ID and determine geographic coordinates.
  - Convert coordinates into an **H3** index (resolution 7 by default).
  - Periodically publish a `PING` message containing its telemetry.
  - Discover other peers dynamically via UDP Multicast Beacons (or static lists).
  - Subscribe to ZMQ topics corresponding to its local H3 cell and adjacent cells (k-ring 1).
  - Maintain a local registry of known peers (`NodeRegistry`).
  - Execute **spatial corroboration** logic on incoming data to detect anomalies.
  - Provide an HTTP API and a localized web dashboard.
- **Technologies**:
  - **ZMQ (ZeroMQ)**: Uses a **PUB** socket (bind) to broadcast telemetry and a **SUB** socket (connect) to dynamically ingest data from discovered peers. It supports **Active Connection Management**, allowing each node to limit its ZMQ SUB sockets to $X$ active connections with dynamic failover (automatically replacing disconnected peers from a pool of reserve peers) and automatic loopback self-filtering to prevent self-peering.
  - **Flask**: Serves the web UI and metrics.
  - **H3**: Uber's Hexagonal Hierarchical Spatial Index for geographic filtering.

## 3. Communication and Data Flow

The main communication pattern is **Pub/Sub (Publish-Subscribe)** mixed with **Dynamic Peer Discovery**.

1. **Discovery**: Each Node broadcasts a UDP multicast beacon (default) announcing its `node_id`, H3 cell, and connection ports. Other nodes receive these beacons to build a local peer map.
2. **Subscription**: Upon discovering a peer, the Node dynamically `connect`s its ZMQ SUB socket to the peer's ZMQ PUB endpoint. It subscribes *only* to spatial topics of interest (its own cell + immediate neighbors).
3. **Publication**: Each Node publishes its JSON telemetry on its ZMQ PUB socket, prefixed with its `h3_cell` as the topic.
4. **Processing**:
    a. The `MeshNode` receive loop reads incoming messages.
    b. The payload is passed to the local `NodeRegistry`.
    c. After each ingest, `MeshNode` triggers `check_corroboration` on the cell. The registry uses a **pluggable** rule (MAD/zscore) to flag anomalous nodes as `FAULTY`.
5. **Visualization**:
    a. The local `DashboardServer` serves an HTML view of the *local* network perspective.
    b. The user can navigate between nodes via the "Connected Peers" sidebar, enabling cross-mesh exploration without centralized aggregation.

## 4. Deployment Architecture (Docker)

The system is designed to run in Docker containers, orchestrated via `docker-compose.yml`.

- **`node-N` services**: The `docker-compose.yml` spins up a configurable number of identical nodes (e.g., node-1 through node-4). Each runs the same unified image (`Dockerfile.node`), discovering peers over the `synapse_net` bridge network.

## 5. Architectural Decisions (ADR)

High-level architectural decisions and their rationale are documented using a lightweight "Architectural Decision Record" (ADR) format. This creates a persistent log of important choices made during the project's evolution.

The records are stored in [`docs/adr/`](./adr/); see [`docs/adr/README.md`](./adr/README.md) for the index.
