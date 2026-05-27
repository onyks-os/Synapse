# ADR 005: Docker for repeatable environments

**Status:** Accepted

**Context:**

The system comprises multiple processes (sensor, monitor) with native dependencies (Python, ZeroMQ). Developers, CI, and demos need **reproducible** environments across machines.

**Decision:**

We containerise with **Docker**:

- Separate **Dockerfiles** for the sensor and monitor images.
- **`docker-compose`** (under `docker/`) to run multi-container stacks on a single host, scale sensors, and inject consistent environment defaults.

**Consequences:**

- **Pros:**
  - **Environment parity** across laptops and servers.
  - **Fast onboarding** via `docker compose up` (see `docs/DEPLOYMENT.md`).
  - **Portability** wherever Docker runs.
- **Cons:**
  - **Operational overhead** (images, daemon) vs bare-metal Python.
  - **Docker becomes a dev/demo dependency** for the recommended path.
