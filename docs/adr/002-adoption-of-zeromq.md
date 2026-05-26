# ADR 002: Adoption of ZeroMQ for node-to-node messaging

**Status:** Accepted

**Context:**

Given the distributed sensor/monitor architecture (ADR-001), we need efficient, asynchronous messaging. Alternatives considered:

- **HTTP/REST:** Simple, but request/response is a poor fit for continuous heartbeats.
- **gRPC:** Strong contracts and performance, but heavier operational setup for this PoC.
- **Raw TCP/UDP:** Maximum control, but reinvents reconnection, framing, and backpressure.

**Decision:**

We standardise on **ZeroMQ (`pyzmq`)** for all sensor-to-monitor **data-plane** messaging, using its high-level socket patterns on top of efficient transports.

**Consequences:**

- **Pros:**
  - **Low latency** suited to frequent heartbeats.
  - **Mature patterns** (Pub/Sub, etc.) with reconnect and buffering behaviour we can rely on in the PoC.
  - **Less custom networking code** than raw sockets.
- **Cons:**
  - **Dependency:** libzmq / pyzmq required on every node image.
  - **Ecosystem:** Endpoints must speak ZMQ; unlike plain HTTP, debugging needs ZMQ-aware tools.
