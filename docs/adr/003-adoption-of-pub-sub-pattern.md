# ADR 003: Publish–subscribe pattern for sensor traffic

**Status:** Accepted

**Context:**

With ZeroMQ selected (ADR-002), we must fix the concrete pattern for sensor heartbeats. The goal is to **decouple publishers from subscribers at the messaging layer**: sensors should not need bespoke per-subscriber logic.

**Decision:**

We use **Publish–Subscribe (Pub/Sub)**:

- **Sensors** act as **PUB** clients: they `connect()` to the monitor’s ingest endpoint and send JSON heartbeats.
- **Monitor** acts as **SUB** and `bind()`s on the well-known port (default `tcp://*:5555`), subscribing to all topics (`""`) for the current PoC.

Sensors are configured with **monitor host and port** (`MONITOR_HOST`, `MONITOR_PORT`); they do not enumerate subscribers, and additional subscribers could attach to the same bind in principle without changing sensor code.

**Consequences:**

- **Pros:**
  - **Decoupled fan-out:** One push from a sensor can reach multiple subscribers if the topology is extended later.
  - **Simple sensor code:** Periodic JSON send without request/response pairing.
- **Cons:**
  - **Best-effort delivery:** Classic ZMQ Pub/Sub does not guarantee that a message is retained if no subscriber was connected; acceptable for heartbeats because later PINGs refresh state.
  - **Aggregator responsibility:** The monitor must handle an open-ended set of senders (rate limiting and validation are applied on ingest).
