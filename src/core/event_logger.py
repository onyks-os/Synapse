"""
src/core/event_logger.py

Structured event logger for Synapse node lifecycle events.
Emits JSON (default) or human-readable text to stdout via the
standard logging module.

Events: NODE_REGISTERED, NODE_FAULTY, NODE_DEAD,
        NODE_RESURRECTED, NODE_EVICTED, RATE_LIMITED.

Controlled by env var Synapse_LOG_FORMAT: "json" (default) | "text".
"""

import json
import logging
import os
from datetime import UTC, datetime

logger = logging.getLogger("Synapse.events")

_FORMAT: str = os.getenv("Synapse_LOG_FORMAT", "json").lower()


def emit(event: str, node_id: str, *, cell: str = "", **detail: object) -> None:
    """
    Emit a structured lifecycle event.

    Args:
        event:   Event type (e.g. NODE_FAULTY, NODE_DEAD).
        node_id: ID of the node involved.
        cell:    H3 cell index (optional).
        **detail: Arbitrary key-value context (zscore, timeout, etc.).
    """
    record: dict = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        "node_id": node_id,
    }
    if cell:
        record["cell"] = cell
    if detail:
        record["detail"] = {k: _safe(v) for k, v in detail.items()}

    if _FORMAT == "json":
        logger.info(json.dumps(record, ensure_ascii=False))
    else:
        parts = [f"[{record['event']}] node={node_id}"]
        if cell:
            parts.append(f"cell={cell}")
        for k, v in detail.items():
            parts.append(f"{k}={v}")
        logger.info(" ".join(parts))


def _safe(value: object) -> object:
    """Ensure values are JSON-serialisable."""
    if isinstance(value, float):
        if value != value:  # NaN
            return "NaN"
        if value == float("inf"):
            return "Infinity"
        if value == float("-inf"):
            return "-Infinity"
    return value
