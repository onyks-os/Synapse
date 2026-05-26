# Threat model (V1 / V2 PoC)

This document states what Synapse assumes about attackers and networks today. It supports honest scoping for papers and early deployments. It is **not** a formal verification artifact.

## Assets

- **Sensor readings** (values, coarse location via H3, node identifiers).
- **Monitor state** (registry: who is alive, faulty, dead).
- **Availability** of the monitor (ingest + dashboard).
- **SQLite file** when `Synapse_REGISTRY_DB` is set: contains the same registry fields at rest — protect like any local credential or state file (permissions, volume encryption, backups).

## Trust boundaries

- **Sensors → Monitor (ZeroMQ PUB → SUB):** Payloads are JSON on TCP. By default there is **no** authentication or encryption. **`Synapse_DASHBOARD_API_KEY`** does **not** protect ZMQ — only HTTP routes documented in this file. Optional **CurveZMQ** (ADR-006) provides encryption and a **client public-key allowlist** on the monitor when configured.
- **Clients → Dashboard (HTTP):** By default the dashboard binds to **loopback** (`127.0.0.1`). Binding to all interfaces (`0.0.0.0`) is intended for containers or private LANs.
  When **`Synapse_DASHBOARD_API_KEY`** is set, the server enforces key-based auth for `/api/v1/*` (and legacy `/api/*` aliases) and `/metrics`. Health endpoints (`/live`, `/ready`, `/health`) remain unauthenticated.
  The token is embedded in the dashboard HTML only when the request is already authorized (otherwise the UI prompts for the key client-side).

## Adversaries (in scope for this PoC)

- **Network eavesdropper** on ZMQ or HTTP: can read traffic in cleartext.
- **Off-path injector** toward the monitor ZMQ port: can spoof sensor messages unless transport is hardened.
- **LAN client** hitting an exposed dashboard: can read API data unless a token is set and exposure is limited.

## Out of scope until later phases

- Cryptographic node identity, signed payloads, BFT/consensus (planned direction for V3).
- TLS wrappers (recommended before any Internet-facing HTTP/ZMQ).
- Full reverse-proxy auth (OAuth2, mTLS) for the dashboard—preferred for real production.

## Deployment posture (minimal)

1. **ZMQ:** Keep on a **private network** or tunnel; plan Curve or replacement before exposing beyond a controlled segment.
2. **HTTP:** Default bind **127.0.0.1**; in Docker set `DASHBOARD_HOST=0.0.0.0` only inside a user-defined network; add **TLS** and **proxy auth** for real operators.
3. **Secrets:** Prefer injecting `Synapse_DASHBOARD_API_KEY` via your orchestrator’s secret store, not committing it to compose files in public repos.
