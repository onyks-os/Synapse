"""
tests/integration/test_h3_api.py

Integration tests for the V2 H3 node registry and Flask HTTP endpoints.
Uses real ZMQ TCP on loopback + Flask test client (no real HTTP server started).
"""

import time

import pytest

from src.core.node_registry import NodeRegistry
from src.network.http_server import create_app

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def registry() -> NodeRegistry:
    return NodeRegistry()


@pytest.fixture
def client(registry: NodeRegistry):
    app = create_app(registry, api_token="")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _ping(
    node_id: str, lat: float, lon: float, h3_cell: str, ts: float | None = None
) -> dict:
    return {
        "node_id": node_id,
        "type": "mock",
        "timestamp": ts or time.time(),
        "status": "PING",
        "h3_cell": h3_cell,
        "payload": {"value": 22.0, "lat": lat, "lon": lon},
    }


# ── NodeRegistry spatial tests ────────────────────────────────────────────────


class TestNodeRegistrySpatial:
    def test_h3_cell_stored_correctly(self, registry: NodeRegistry) -> None:
        """h3_cell from the payload is stored in the NodeEntry."""
        registry.upsert(_ping("s1", 45.4, 9.1, "871fb4670ffffff"))
        entry = registry.get_node("s1")
        assert entry is not None
        assert entry["h3_cell"] == "871fb4670ffffff"
        assert entry["lat"] == pytest.approx(45.4)
        assert entry["lon"] == pytest.approx(9.1)

    def test_get_by_cell_returns_correct_nodes(self, registry: NodeRegistry) -> None:
        """get_by_cell returns only nodes that belong to the requested cell."""
        registry.upsert(_ping("s_a", 45.4, 9.1, "cell_A"))
        registry.upsert(_ping("s_b", 45.4, 9.1, "cell_A"))
        registry.upsert(_ping("s_c", 38.1, 13.3, "cell_B"))

        in_a = registry.get_by_cell("cell_A")
        assert len(in_a) == 2
        assert all(e["h3_cell"] == "cell_A" for e in in_a)

    def test_get_cells_summary_counts(self, registry: NodeRegistry) -> None:
        """get_cells_summary produces correct alive/dead counts per cell."""
        registry.upsert(_ping("s1", 45.0, 9.0, "cellX", ts=100.0))
        registry.upsert(_ping("s2", 45.1, 9.1, "cellX", ts=100.0))
        registry.upsert(_ping("s3", 38.0, 13.0, "cellY", ts=100.0))
        # mark s2 as dead
        registry.check_timeouts(now=110.0, death_timeout=3.0)
        # but s3 is still alive (upsert it again with fresh ts)
        registry.upsert(_ping("s3", 38.0, 13.0, "cellY", ts=115.0))

        summary = registry.get_cells_summary()
        assert "cellX" in summary
        assert "cellY" in summary
        # Both s1 and s2 timed out (last_seen=100, now=110 > 3s)
        assert summary["cellX"]["dead"] == 2
        assert summary["cellX"]["alive"] == 0
        assert summary["cellY"]["alive"] == 1

    def test_empty_h3_cell_excluded_from_summary(self, registry: NodeRegistry) -> None:
        """Nodes with no h3_cell value are excluded from the cells summary."""
        # Simulate a V1-era payload with no h3_cell
        registry.upsert(
            {
                "node_id": "legacy",
                "type": "mock",
                "timestamp": time.time(),
                "status": "PING",
                "payload": {"value": 0.0, "lat": 0.0, "lon": 0.0},
            }
        )
        summary = registry.get_cells_summary()
        assert "" not in summary


# ── Flask API tests ───────────────────────────────────────────────────────────


class TestFlaskAPI:
    def test_api_nodes_empty(self, client, registry: NodeRegistry) -> None:
        """/api/v1/nodes returns an empty list when no nodes are registered."""
        res = client.get("/api/v1/nodes")
        assert res.status_code == 200
        assert res.get_json() == []

    def test_api_nodes_returns_all(self, client, registry: NodeRegistry) -> None:
        """/api/v1/nodes returns all registered nodes as a list."""
        registry.upsert(_ping("s1", 45.0, 9.0, "c1"))
        registry.upsert(_ping("s2", 45.1, 9.1, "c1"))
        res = client.get("/api/v1/nodes")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) == 2
        node_ids = {d["node_id"] for d in data}
        assert node_ids == {"s1", "s2"}

    def test_api_cells_empty(self, client, registry: NodeRegistry) -> None:
        """/api/v1/cells returns an empty dict when no nodes are registered."""
        res = client.get("/api/v1/cells")
        assert res.status_code == 200
        assert res.get_json() == {}

    def test_api_cells_groups_correctly(self, client, registry: NodeRegistry) -> None:
        """/api/v1/cells groups nodes by h3_cell with correct alive/dead counts."""
        registry.upsert(_ping("s1", 45.0, 9.0, "cellX"))
        registry.upsert(_ping("s2", 45.1, 9.1, "cellX"))
        registry.upsert(_ping("s3", 38.0, 13.0, "cellY"))

        res = client.get("/api/v1/cells")
        assert res.status_code == 200
        data = res.get_json()
        assert "cellX" in data
        assert "cellY" in data
        assert data["cellX"]["alive"] == 2
        assert data["cellY"]["alive"] == 1
        assert set(data["cellX"]["nodes"]) == {"s1", "s2"}


class TestFlaskHardening:
    def test_health_ok(self, client, registry: NodeRegistry) -> None:
        res = client.get("/health")
        assert res.status_code == 200
        body = res.get_json()
        assert body["status"] == "ok"

    def test_api_rejects_without_bearer_when_token_set(
        self,
        registry: NodeRegistry,
    ) -> None:
        app = create_app(registry, api_token="test-secret")
        app.config["TESTING"] = True
        with app.test_client() as c:
            assert c.get("/api/v1/nodes").status_code == 401
            assert (
                c.get(
                    "/api/v1/nodes", headers={"Authorization": "Bearer wrong"}
                ).status_code
                == 401
            )

    def test_api_accepts_bearer_when_token_set(
        self,
        registry: NodeRegistry,
    ) -> None:
        registry.upsert(_ping("s1", 45.0, 9.0, "c1"))
        app = create_app(registry, api_token="test-secret")
        app.config["TESTING"] = True
        with app.test_client() as c:
            res = c.get(
                "/api/v1/nodes",
                headers={"Authorization": "Bearer test-secret"},
            )
            assert res.status_code == 200
            assert len(res.get_json()) == 1

    def test_api_accepts_x_api_key_when_token_set(
        self,
        registry: NodeRegistry,
    ) -> None:
        app = create_app(registry, api_token="key1")
        app.config["TESTING"] = True
        with app.test_client() as c:
            res = c.get("/api/v1/cells", headers={"X-API-Key": "key1"})
            assert res.status_code == 200

    def test_metrics_require_auth_when_token_set(
        self,
        registry: NodeRegistry,
    ) -> None:
        registry.upsert(_ping("s1", 45.0, 9.0, "c1"))
        app = create_app(registry, api_token="metric-secret")
        app.config["TESTING"] = True
        with app.test_client() as c:
            assert c.get("/metrics").status_code == 401
            res = c.get("/metrics", headers={"X-API-Key": "metric-secret"})
            assert res.status_code == 200
            txt = res.data.decode("utf-8")
            assert "Synapse_nodes_total" in txt

    def test_health_unaffected_by_api_token(self, registry: NodeRegistry) -> None:
        app = create_app(registry, api_token="secret")
        app.config["TESTING"] = True
        with app.test_client() as c:
            assert c.get("/health").status_code == 200
            assert c.get("/live").status_code == 200
            assert c.get("/ready").status_code == 200


class TestUnauthedEndpoints:
    def test_metrics_works_without_token(self, client, registry: NodeRegistry) -> None:
        res = client.get("/metrics")
        assert res.status_code == 200
        txt = res.data.decode("utf-8")
        assert "Synapse_messages_total" in txt
