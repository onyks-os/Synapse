# ADR 001: Distributed sensor and monitor architecture

**Status:** Accepted

**Context:**

The project must scale horizontally and tolerate individual node failures. Responsibilities should be decoupled so sensors and the monitor can be developed and deployed independently. A single monolith would not meet these flexibility and robustness goals.

**Decision:**

We adopt a **two-role distributed layout**:

1. **Sensor** — A worker node that performs edge duties and periodically reports health and readings (**heartbeat** / PING).
2. **Monitor** — A controller node that ingests sensor traffic, aggregates **in-memory** network state (`NodeRegistry`), runs lifecycle and corroboration logic, and serves the HTTP dashboard and API.

This is a **hub-and-spoke data plane**: many sensors publish toward one monitor process that subscribes and binds the ingest port. It is **brokerless** in the sense of **no separate MQTT-style message broker**; it is **not** yet a symmetric peer-to-peer mesh (that remains a later-phase direction).

**Consequences:**

- **Pros:**
  - **Scale-out:** Sensors can be added or removed with load; monitor is a separate role.
  - **Resilience:** Failure of one sensor does not take down the whole system.
  - **Separation of concerns:** Edge publishing logic is separate from aggregation, UI, and policy.
- **Cons:**
  - **Complexity:** Requires network transport, configuration (e.g. `MONITOR_HOST`), and operational understanding of timeouts and registry semantics.
  - **Monitor as locus of state:** The authoritative registry for this PoC lives on the monitor; restart clears it unless persistence is added later.
