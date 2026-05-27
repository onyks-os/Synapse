"""
tests/unit/test_event_logger.py

Unit tests for the structured event logger.
"""

import json
from unittest.mock import patch

from src.core import event_logger


class TestEventLoggerJSON:
    """Tests for JSON-format event output."""

    def test_emit_json_has_required_fields(self) -> None:
        """Every JSON event must contain timestamp, event, and node_id."""
        with (
            patch.object(event_logger, "_FORMAT", "json"),
            patch.object(event_logger.logger, "info") as mock_log,
        ):
            event_logger.emit("NODE_FAULTY", "sensor_42", cell="cellA")

        mock_log.assert_called_once()
        record = json.loads(mock_log.call_args[0][0])
        assert record["event"] == "NODE_FAULTY"
        assert record["node_id"] == "sensor_42"
        assert record["cell"] == "cellA"
        assert "timestamp" in record

    def test_emit_json_with_detail(self) -> None:
        """Extra kwargs appear under the 'detail' key."""
        with (
            patch.object(event_logger, "_FORMAT", "json"),
            patch.object(event_logger.logger, "info") as mock_log,
        ):
            event_logger.emit(
                "NODE_FAULTY",
                "s1",
                cell="c1",
                zscore=3.14,
                threshold=2.0,
            )

        record = json.loads(mock_log.call_args[0][0])
        assert record["detail"]["zscore"] == 3.14
        assert record["detail"]["threshold"] == 2.0

    def test_emit_json_without_cell(self) -> None:
        """When cell is omitted, the 'cell' key is absent from the record."""
        with (
            patch.object(event_logger, "_FORMAT", "json"),
            patch.object(event_logger.logger, "info") as mock_log,
        ):
            event_logger.emit("NODE_EVICTED", "s1")

        record = json.loads(mock_log.call_args[0][0])
        assert "cell" not in record

    def test_emit_json_safe_values(self) -> None:
        """Infinity/NaN are serialised safely (no JSON crash)."""
        with (
            patch.object(event_logger, "_FORMAT", "json"),
            patch.object(event_logger.logger, "info") as mock_log,
        ):
            event_logger.emit(
                "NODE_FAULTY",
                "s1",
                value=float("inf"),
                bad=float("nan"),
            )

        record = json.loads(mock_log.call_args[0][0])
        assert record["detail"]["value"] == "Infinity"
        assert record["detail"]["bad"] == "NaN"


class TestEventLoggerText:
    """Tests for human-readable text-format output."""

    def test_emit_text_format(self) -> None:
        """Text mode produces a human-readable string."""
        with (
            patch.object(event_logger, "_FORMAT", "text"),
            patch.object(event_logger.logger, "info") as mock_log,
        ):
            event_logger.emit("NODE_DEAD", "s1", cell="cellX", timeout=3.0)

        msg = mock_log.call_args[0][0]
        assert "[NODE_DEAD]" in msg
        assert "node=s1" in msg
        assert "cell=cellX" in msg
        assert "timeout=3.0" in msg
