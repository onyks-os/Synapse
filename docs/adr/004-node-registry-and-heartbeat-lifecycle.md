# ADR 004: In-memory node registry and heartbeat-driven lifecycle

**Status:** Accepted

**Context:**

Under Pub/Sub (ADR-003), the monitor receives a continuous stream of heartbeats. We need a explicit model for **who is in the network**, **who has gone silent**, and **when to remove tombstone entries** from memory.

**Decision:**

We implement **heartbeat-driven liveness** plus an in-memory **node registry**:

1. **Heartbeat:** Each sensor sends a PING message on a configurable interval (`PING_INTERVAL`).
2. **NodeRegistry:** The monitor keeps a map from `node_id` to **`NodeEntry`** (status, `last_seen`, H3 cell, last reading, etc.). First sighting **registers** the node; each valid message **upserts** it and sets status to **`ALIVE`** (subject to corroboration in V2).
3. **GarbageCollector:** A background loop marks nodes as **`DEAD`** when `last_seen` exceeds **`DEATH_TIMEOUT`**, then **evicts** entries that have been dead longer than **`EVICTION_TTL`**.

V2 extends states with **`FAULTY`** when spatial corroboration flags anomalous readings. The detector is **pluggable** (`CORROBORATION_METHOD` — default MAD-based modified Z); see `docs/TDD.md` §4.5–4.6 and `NodeRegistry.check_corroboration`.

**Consequences:**

- **Pros:**
  - **Automatic failure detection** for silent or crashed sensors.
  - **Live inventory** for the dashboard and APIs without a separate service-discovery product.
- **Cons:**
  - **Eventual consistency:** Detection lag is bounded by timeout configuration, not instantaneous.
  - **Ephemeral registry:** State is **in RAM** on the monitor; process restart loses history until sensors send again (persistence is out of scope for the current PoC).
