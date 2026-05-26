# ADR 007: Transition to Symmetric P2P Mesh Architecture

**Date**: 2026-05-23
**Status**: Accepted

## Context
Synapse was originally designed using a Hub-and-Spoke architecture: many edge "Sensors" publishing via ZeroMQ PUB sockets to a central "Monitor" node acting as the source of truth, maintaining the global node registry and UI dashboard. While effective for initial prototyping of the spatial corroboration algorithms, this design introduced a single point of failure (the Monitor) and contradicted the decentralization goals of a true edge-native system.

To achieve fault-tolerance and dynamic scalability at the edge, the system needed a decentralized topology where each participant could function autonomously.

## Decision
We are replacing the Hub-and-Spoke architecture with a Symmetric P2P Mesh topology.
- **Unified Node (`MeshNode`)**: The `main_sensor.py` and `main_monitor.py` processes are unified into a single `main_node.py` executable. Each node performs sensing, data ingestion (PUB/SUB), local registry maintenance, and spatial corroboration independently.
- **Dynamic Peer Discovery**: Implemented a flexible `PeerProvider` interface with two strategies:
  1. `BeaconPeerProvider` (Default): Uses UDP multicast beacons to dynamically discover peers on the local network.
  2. `StaticPeerProvider` (Fallback): Uses a static list of IP:Port addresses defined via environment variables (`SYNAPSE_PEERS`).
- **Spatial Subscriptions**: Nodes only subscribe to ZMQ topics matching their H3 cell and adjacent cells (k-ring 1). This filters out irrelevant traffic and scales corroboration efficiently without a global state.
- **Mutual Authentication (CURVE)**: Extended CurveZMQ support to allow mutual authentication. Nodes share a peer trust list (`peer_keys.txt`) acting as an allowlist, where each node validates both inbound connections and the identities of outbound peers.

## Consequences
- **Pros**:
  - Eliminated the central Monitor single point of failure.
  - Improved network resilience; nodes can join or leave the mesh dynamically without affecting the rest of the network.
  - Better alignment with edge-computing principles.
- **Cons**:
  - Increased complexity in network discovery and connection management (UDP multicast limitations in some cloud environments).
  - Dashboards are now localized to each node's perspective rather than global. Cross-node navigation is provided via a "Peer Network" UI bar.
