# Architecture Decision Records (ADRs)

Immutable-style log of significant technical choices for Synapse. All records are in **English** and numbered for stable references.

| ID | File | Topic |
| --- | --- | --- |
| 001 | [001-distributed-sensor-monitor-architecture.md](./001-distributed-sensor-monitor-architecture.md) | Sensor vs monitor roles; hub-and-spoke data plane |
| 002 | [002-adoption-of-zeromq.md](./002-adoption-of-zeromq.md) | ZeroMQ as transport |
| 003 | [003-adoption-of-pub-sub-pattern.md](./003-adoption-of-pub-sub-pattern.md) | PUB sensors, SUB monitor, topic `""` |
| 004 | [004-node-registry-and-heartbeat-lifecycle.md](./004-node-registry-and-heartbeat-lifecycle.md) | Registry, timeouts, eviction, V2 `FAULTY` |
| 005 | [005-adoption-of-docker.md](./005-adoption-of-docker.md) | Container images and Compose |
| 006 | [006-adoption-of-curvezmq.md](./006-adoption-of-curvezmq.md) | Optional CurveZMQ + client allowlist |
