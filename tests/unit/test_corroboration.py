"""
tests/unit/test_corroboration.py

Unit tests for spatial corroboration (V2).
Default fixture uses **MAD** (modified Z-score) — the runtime default.
"""

import pytest

from src.core.corroboration import (
    BothStrategy,
    ClassicZScoreStrategy,
    build_corroboration_strategy,
)
from src.core.node_registry import NodeRegistry


@pytest.fixture
def registry() -> NodeRegistry:
    return NodeRegistry(corroboration_strategy=build_corroboration_strategy("mad"))


@pytest.fixture
def registry_zscore() -> NodeRegistry:
    return NodeRegistry(corroboration_strategy=ClassicZScoreStrategy())


def _ping(node_id: str, cell: str, value: float, ts: float = 100.0) -> dict:
    """Helper to build a payload with a specific sensor value and cell."""
    return {
        "node_id": node_id,
        "type": "mock",
        "timestamp": ts,
        "status": "PING",
        "h3_cell": cell,
        "payload": {"value": value, "lat": 45.0, "lon": 9.0},
    }


class TestCheckCorroboration:
    """Tests for NodeRegistry.check_corroboration()."""

    def test_below_quorum_no_corroboration(self, registry: NodeRegistry) -> None:
        """With fewer than min_peers, no node is marked FAULTY."""
        registry.upsert(_ping("s1", "cellA", 20.0))
        registry.upsert(_ping("s2", "cellA", 999.0))  # extreme outlier
        faulty = registry.check_corroboration(
            "cellA", zscore_threshold=2.0, min_peers=3
        )
        assert faulty == []
        assert registry.get_node("s2")["status"] == "ALIVE"

    def test_outlier_marked_faulty(self, registry: NodeRegistry) -> None:
        """A clear outlier in a cell with enough peers is marked FAULTY."""
        registry.upsert(_ping("s1", "cellA", 20.0))
        registry.upsert(_ping("s2", "cellA", 21.0))
        registry.upsert(_ping("s3", "cellA", 19.5))
        registry.upsert(_ping("s4", "cellA", 999.0))  # extreme outlier
        faulty = registry.check_corroboration(
            "cellA", zscore_threshold=2.0, min_peers=3
        )
        assert "s4" in faulty
        assert registry.get_node("s4")["status"] == "FAULTY"
        # Others remain ALIVE
        assert registry.get_node("s1")["status"] == "ALIVE"
        assert registry.get_node("s2")["status"] == "ALIVE"
        assert registry.get_node("s3")["status"] == "ALIVE"

    def test_no_outlier_all_stay_alive(self, registry: NodeRegistry) -> None:
        """When all values are very similar, nobody is marked FAULTY."""
        # Use identical values — leave-one-out σ=0 skips Z-score check
        registry.upsert(_ping("s1", "cellA", 20.0))
        registry.upsert(_ping("s2", "cellA", 20.0))
        registry.upsert(_ping("s3", "cellA", 20.0))
        faulty = registry.check_corroboration(
            "cellA", zscore_threshold=2.0, min_peers=3
        )
        assert faulty == []

    def test_identical_values_no_fault(self, registry: NodeRegistry) -> None:
        """If all values are identical (sigma=0), no false positives."""
        registry.upsert(_ping("s1", "cellA", 22.0))
        registry.upsert(_ping("s2", "cellA", 22.0))
        registry.upsert(_ping("s3", "cellA", 22.0))
        faulty = registry.check_corroboration(
            "cellA", zscore_threshold=2.0, min_peers=3
        )
        assert faulty == []

    def test_recovery_after_normal_reading(self, registry: NodeRegistry) -> None:
        """A FAULTY node that sends a normal value recovers to ALIVE immediately."""
        # Setup: 3 normal + 1 outlier
        registry.upsert(_ping("s1", "cellA", 20.0))
        registry.upsert(_ping("s2", "cellA", 21.0))
        registry.upsert(_ping("s3", "cellA", 19.5))
        registry.upsert(_ping("s4", "cellA", 999.0))
        registry.check_corroboration("cellA", zscore_threshold=2.0, min_peers=3)
        assert registry.get_node("s4")["status"] == "FAULTY"

        # s4 sends a normal reading → upsert resets to ALIVE
        registry.upsert(_ping("s4", "cellA", 20.2, ts=200.0))
        assert registry.get_node("s4")["status"] == "ALIVE"

        # Re-run corroboration → still normal → stays ALIVE
        faulty = registry.check_corroboration(
            "cellA", zscore_threshold=2.0, min_peers=3
        )
        assert "s4" not in faulty
        assert registry.get_node("s4")["status"] == "ALIVE"

    def test_different_cells_independent(self, registry: NodeRegistry) -> None:
        """Corroboration only looks at nodes in the requested cell."""
        # Use enough peers with identical values in cellA
        registry.upsert(_ping("s1", "cellA", 20.0))
        registry.upsert(_ping("s2", "cellA", 20.0))
        registry.upsert(_ping("s3", "cellA", 20.0))
        registry.upsert(_ping("other", "cellB", 999.0))  # different cell
        faulty = registry.check_corroboration(
            "cellA", zscore_threshold=2.0, min_peers=3
        )
        assert faulty == []
        assert registry.get_node("other")["status"] == "ALIVE"

    def test_faulty_node_excluded_from_quorum(self, registry: NodeRegistry) -> None:
        """Only ALIVE nodes are considered — FAULTY nodes do not participate in corroboration."""
        # 5 normal + 1 extreme outlier
        registry.upsert(_ping("s1", "cellA", 20.0))
        registry.upsert(_ping("s2", "cellA", 20.5))
        registry.upsert(_ping("s3", "cellA", 19.5))
        registry.upsert(_ping("s4", "cellA", 20.2))
        registry.upsert(_ping("s5", "cellA", 19.8))
        registry.upsert(_ping("s6", "cellA", 999.0))
        registry.check_corroboration("cellA", zscore_threshold=2.0, min_peers=3)
        assert registry.get_node("s6")["status"] == "FAULTY"

        # Now 5 ALIVE remain (s1-s5). Add s7 within normal range.
        registry.upsert(_ping("s7", "cellA", 20.1))
        faulty = registry.check_corroboration(
            "cellA", zscore_threshold=2.0, min_peers=3
        )
        assert "s7" not in faulty
        assert registry.get_node("s7")["status"] == "ALIVE"

    def test_configurable_threshold(self, registry: NodeRegistry) -> None:
        """A lower threshold catches more subtle anomalies."""
        # 5 normal sensors + 1 mildly deviant
        registry.upsert(_ping("s1", "cellA", 20.0))
        registry.upsert(_ping("s2", "cellA", 20.5))
        registry.upsert(_ping("s3", "cellA", 19.5))
        registry.upsert(_ping("s4", "cellA", 20.2))
        registry.upsert(_ping("s5", "cellA", 19.8))
        registry.upsert(_ping("s6", "cellA", 25.0))  # mild outlier

        # With threshold=2.0 → may or may not flag s6
        _faulty_lenient = registry.check_corroboration(
            "cellA", zscore_threshold=2.0, min_peers=3
        )

        # Reset s6 to ALIVE for re-test
        registry.upsert(_ping("s6", "cellA", 25.0))

        # With threshold=1.0 → s6 SHOULD be faulty (lower threshold = more sensitive)
        faulty_strict = registry.check_corroboration(
            "cellA", zscore_threshold=1.0, min_peers=3
        )
        assert "s6" in faulty_strict

    def test_check_timeouts_catches_faulty_nodes(self, registry: NodeRegistry) -> None:
        """A FAULTY node that goes silent is marked DEAD by check_timeouts."""
        registry.upsert(_ping("s1", "cellA", 20.0, ts=100.0))
        registry.upsert(_ping("s2", "cellA", 21.0, ts=100.0))
        registry.upsert(_ping("s3", "cellA", 19.5, ts=100.0))
        registry.upsert(_ping("s4", "cellA", 999.0, ts=100.0))
        registry.check_corroboration("cellA", zscore_threshold=2.0, min_peers=3)
        assert registry.get_node("s4")["status"] == "FAULTY"

        # Time passes — s4 goes silent → should become DEAD
        dead = registry.check_timeouts(now=110.0, death_timeout=3.0)
        assert "s4" in dead
        assert registry.get_node("s4")["status"] == "DEAD"

    def test_cells_summary_includes_faulty(self, registry: NodeRegistry) -> None:
        """get_cells_summary correctly counts FAULTY nodes."""
        registry.upsert(_ping("s1", "cellA", 20.0))
        registry.upsert(_ping("s2", "cellA", 21.0))
        registry.upsert(_ping("s3", "cellA", 19.5))
        registry.upsert(_ping("s4", "cellA", 999.0))
        registry.check_corroboration("cellA", zscore_threshold=2.0, min_peers=3)

        summary = registry.get_cells_summary()
        assert summary["cellA"]["alive"] == 3
        assert summary["cellA"]["faulty"] == 1
        assert summary["cellA"]["dead"] == 0


class TestClassicZscoreMode:
    """Legacy mean/σ Z-score behaves like the pre-MAD implementation."""

    def test_outlier_marked_faulty(self, registry_zscore: NodeRegistry) -> None:
        registry_zscore.upsert(_ping("s1", "cellA", 20.0))
        registry_zscore.upsert(_ping("s2", "cellA", 21.0))
        registry_zscore.upsert(_ping("s3", "cellA", 19.5))
        registry_zscore.upsert(_ping("s4", "cellA", 999.0))
        faulty = registry_zscore.check_corroboration(
            "cellA",
            zscore_threshold=2.0,
            min_peers=3,
        )
        assert "s4" in faulty
        assert registry_zscore.get_node("s4")["status"] == "FAULTY"


class TestBothStrategyConservative:
    """``both`` requires classic Z *and* MAD to exceed the threshold."""

    def test_not_faulty_if_only_one_arm_fires(self) -> None:
        class _ZAlways:
            def evaluate(self, value, peer_values, threshold):  # noqa: ARG002
                return True, {"zscore": 99.0, "corroboration": "zscore"}

        class _MadNever:
            def evaluate(self, value, peer_values, threshold):  # noqa: ARG002
                return False, {"modified_z": 0.1, "corroboration": "mad"}

        reg = NodeRegistry(
            corroboration_strategy=BothStrategy(z=_ZAlways(), mad=_MadNever()),
        )
        reg.upsert(_ping("s1", "cellA", 20.0))
        reg.upsert(_ping("s2", "cellA", 21.0))
        reg.upsert(_ping("s3", "cellA", 19.5))
        reg.upsert(_ping("s4", "cellA", 999.0))
        faulty = reg.check_corroboration("cellA", zscore_threshold=2.0, min_peers=3)
        assert faulty == []
        assert reg.get_node("s4")["status"] == "ALIVE"

    def test_faulty_when_both_arms_fire(self) -> None:
        reg = NodeRegistry(corroboration_strategy=build_corroboration_strategy("both"))
        reg.upsert(_ping("s1", "cellA", 20.0))
        reg.upsert(_ping("s2", "cellA", 21.0))
        reg.upsert(_ping("s3", "cellA", 19.5))
        reg.upsert(_ping("s4", "cellA", 999.0))
        faulty = reg.check_corroboration("cellA", zscore_threshold=2.0, min_peers=3)
        assert "s4" in faulty


class TestCorroborationFactory:
    def test_unknown_method_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown CORROBORATION_METHOD"):
            build_corroboration_strategy("not_a_real_method")

    def test_custom_registration_roundtrip(self) -> None:
        from src.core.corroboration import (
            register_corroboration_method,
            unregister_corroboration_method,
        )

        register_corroboration_method("always_z", lambda: ClassicZScoreStrategy())
        try:
            strat = build_corroboration_strategy("always_z")
            assert isinstance(strat, ClassicZScoreStrategy)
        finally:
            unregister_corroboration_method("always_z")
