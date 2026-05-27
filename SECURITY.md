# Security Policy

## Supported Versions

This project is currently a **Proof of Concept (PoC)** and is not intended for production use. As such, there are no officially "supported" or "stable" versions at this time. We encourage academic and research use, but strongly advise against deploying Synapse in a live, security-critical environment.

The security model is a primary focus for the **V3 (WASM/DePIN Migration)** phase of the project, which will introduce cryptographic signatures, sandboxed execution, and formal consensus mechanisms.

For a concise statement of assumptions, assets, and in-scope adversaries for the current codebase, see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

### Hardening knobs (current PoC)

- **`DASHBOARD_HOST`** — defaults to `127.0.0.1` for local runs. Use `0.0.0.0` only when the process sits on a trusted network (e.g. Docker bridge) or behind a reverse proxy.
- **`Synapse_DASHBOARD_API_KEY`** — when set, `/api/v1/*` (and legacy `/api/*` aliases) and `/metrics` require `Authorization: Bearer …` or `X-API-Key: …`.
  Health probes (`/live`, `/ready`, `/health`) remain unauthenticated. For strong deployments prefer proxy-level authentication and TLS.

## Reporting a Vulnerability

We take security seriously, even in this early phase. If you discover a security vulnerability, we would appreciate your help in disclosing it to us privately.

Please use GitHub's private vulnerability reporting feature to submit your report. You can do this by going to the "Security" tab of the repository and clicking "Report a Vulnerability".

**Please do not disclose the vulnerability publicly** until a resolution has been reached. We will do our best to respond to your report promptly and keep you updated on our progress.
