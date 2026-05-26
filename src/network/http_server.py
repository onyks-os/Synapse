"""
src/network/http_server.py

Flask HTTP server for the Synapse dashboard and operators' endpoints.

Endpoints:
  GET /live       → Liveness probe (no auth)
  GET /ready      → Readiness probe (no auth)
  GET /health     → Backward-compatible alias for /ready (no auth)
  GET /metrics    → Prometheus metrics (requires API key when configured)
  GET /           → Serves the Leaflet dashboard HTML (unauthenticated; UI prompts for key when needed)
  GET /api/v1/*   → Versioned JSON API (auth if API key enabled)
  GET /api/*      → Backward-compatible aliases for /api/v1/*.

Auth model:
  When a dashboard API key is configured, the server requires it for:
    - '/api/v1/*' and '/api/*'
    - '/metrics'
  Health endpoints remain unauthenticated for orchestration tooling.

API key is taken from `Synapse_DASHBOARD_API_KEY` (preferred) or `Synapse_API_TOKEN`
(legacy compatibility). It can be sent as:
  - Authorization: Bearer <key>
  - X-API-Key: <key>
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request

from src.core.node_registry import NodeRegistry

logger = logging.getLogger(__name__)

_DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"
_DASHBOARD_INDEX = _DASHBOARD_DIR / "index.html"


def _effective_api_token(explicit: str | None) -> str | None:
    raw = (
        explicit if explicit is not None else os.getenv("Synapse_DASHBOARD_API_KEY", "")
    )
    if not raw:
        # Legacy compatibility
        raw = os.getenv("Synapse_API_TOKEN", "")
    raw = raw.strip()
    return raw if raw else None


def create_app(
    registry: NodeRegistry,
    *,
    api_token: str | None = None,
    peer_info_fn: Callable[[], list[dict]] | None = None,
    identity: dict | None = None,
) -> Flask:
    app = Flask(__name__, static_folder=None)
    # Suppress Flask's default request logger to keep node logs clean
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    token = _effective_api_token(api_token)
    base_html = _DASHBOARD_INDEX.read_text(encoding="utf-8")

    @app.before_request
    def _require_api_auth() -> None:
        if not token:
            return
        path = request.path or ""
        # Keep orchestration probes unauthenticated.
        if path in ("/live", "/ready", "/health"):
            return
        # Require auth for the versioned API + metrics.
        # The dashboard HTML itself is allowed without auth so the page can
        # prompt for the key and fetch /api/* securely.
        requires = path.startswith("/api") or path == "/metrics"
        if not requires:
            return
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            got = auth[7:].strip()
            if got == token:
                return
        if request.headers.get("X-API-Key", "").strip() == token:
            return
        abort(401)

    def _ok() -> Response:
        return jsonify({"status": "ok"})

    @app.get("/live")
    def live() -> Response:
        return _ok()

    @app.get("/ready")
    def ready() -> Response:
        snap = registry.metrics_snapshot()
        return jsonify(
            {
                "status": "ok",
                "nodes_total": snap["nodes_total"],
                "nodes_alive": snap["nodes_alive"],
            }
        )

    @app.get("/health")
    def health() -> Response:
        return ready()

    @app.get("/")
    def index() -> Response:
        html = base_html
        if token:
            auth = request.headers.get("Authorization", "")
            ok = False
            if auth.startswith("Bearer "):
                ok = auth[7:].strip() == token
            if not ok and request.headers.get("X-API-Key", "").strip() == token:
                ok = True
            if ok:
                inject = (
                    "<script>window.__Synapse_DASHBOARD_API_KEY="
                    f"{json.dumps(token)};</script>\n"
                )
                html = base_html.replace("<head>", "<head>\n    " + inject, 1)
        return Response(html, mimetype="text/html; charset=utf-8")

    # ── Versioned API ─────────────────────────────────────────────────────

    @app.get("/api/v1/nodes")
    def api_v1_nodes() -> Response:
        return jsonify(list(registry.get_all().values()))

    @app.get("/api/v1/cells")
    def api_v1_cells() -> Response:
        return jsonify(registry.get_cells_summary())

    @app.get("/api/v1/peers")
    def api_v1_peers() -> Response:
        if peer_info_fn:
            return jsonify(peer_info_fn())
        return jsonify([])

    @app.get("/api/v1/identity")
    def api_v1_identity() -> Response:
        return jsonify(identity or {})

    # ── Legacy aliases (keep for backward compatibility) ────────────────

    @app.get("/api/nodes")
    def api_nodes() -> Response:
        return api_v1_nodes()

    @app.get("/api/cells")
    def api_cells() -> Response:
        return api_v1_cells()

    # ── Prometheus metrics ───────────────────────────────────────────────

    @app.get("/metrics")
    def metrics() -> Response:
        snap = registry.metrics_snapshot()
        # Prometheus exposition format (text; UTF-8)
        lines: list[str] = [
            "# HELP Synapse_messages_total Total accepted heartbeat messages.",
            "# TYPE Synapse_messages_total counter",
            f"Synapse_messages_total {snap['messages_total']}",
            "# HELP Synapse_invalid_payload_total Total discarded/malformed payloads.",
            "# TYPE Synapse_invalid_payload_total counter",
            f"Synapse_invalid_payload_total {snap['invalid_payload_total']}",
            "# HELP Synapse_rate_limited_total Total rate-limited messages.",
            "# TYPE Synapse_rate_limited_total counter",
            f"Synapse_rate_limited_total {snap['rate_limited_total']}",
            "# HELP Synapse_corroboration_faulty_total Total nodes marked FAULTY by corroboration.",
            "# TYPE Synapse_corroboration_faulty_total counter",
            f"Synapse_corroboration_faulty_total {snap['corroboration_faulty_total']}",
            "# HELP Synapse_nodes_total Total nodes tracked in memory.",
            "# TYPE Synapse_nodes_total gauge",
            f"Synapse_nodes_total {snap['nodes_total']}",
            "# HELP Synapse_nodes_alive Nodes currently in ALIVE state.",
            "# TYPE Synapse_nodes_alive gauge",
            f"Synapse_nodes_alive {snap['nodes_alive']}",
            "# HELP Synapse_nodes_faulty Nodes currently in FAULTY state.",
            "# TYPE Synapse_nodes_faulty gauge",
            f"Synapse_nodes_faulty {snap['nodes_faulty']}",
            "# HELP Synapse_nodes_dead Nodes currently in DEAD state.",
            "# TYPE Synapse_nodes_dead gauge",
            f"Synapse_nodes_dead {snap['nodes_dead']}",
        ]
        return Response("\n".join(lines) + "\n", mimetype="text/plain; version=0.0.4")

    return app


class DashboardServer:
    """Runs Flask in a background daemon thread — non-blocking for asyncio."""

    def __init__(
        self,
        registry: NodeRegistry,
        port: int | None = None,
        host: str | None = None,
        api_token: str | None = None,
        peer_info_fn: Callable[[], list[dict]] | None = None,
        identity: dict | None = None,
    ) -> None:
        self._app = create_app(
            registry,
            api_token=api_token,
            peer_info_fn=peer_info_fn,
            identity=identity,
        )
        self._port = port or int(os.getenv("DASHBOARD_PORT", "8080"))
        self._host = (
            host if host is not None else os.getenv("DASHBOARD_HOST", "127.0.0.1")
        )
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start Flask in a daemon thread."""
        self._thread = threading.Thread(
            target=self._app.run,
            kwargs={
                "host": self._host,
                "port": self._port,
                "debug": False,
                "use_reloader": False,
            },
            daemon=True,
            name="Synapse-dashboard",
        )
        self._thread.start()
        logger.info("[Dashboard] Live map at http://%s:%d", self._host, self._port)
