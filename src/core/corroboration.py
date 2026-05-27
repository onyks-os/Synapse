"""
src/core/corroboration.py

Pluggable spatial corroboration strategies (leave-one-out peer comparison).

Default is **modified Z-score with MAD** (robust to a few bad peers in small cells).
Classic mean/σ Z-score and a conservative **both** (AND) mode are also available.

Extensibility
-------------
1. Implement ``CorroborationStrategy`` (see protocol below).
2. Register at startup: ``register_corroboration_method("my_method", lambda: MyStrategy())``.
3. Set ``CORROBORATION_METHOD=my_method``.

Alternatively, add a built-in entry in ``_builtin_strategies`` and ship it in this module.
"""

from __future__ import annotations

import os
import statistics
from collections.abc import Callable
from typing import Protocol, runtime_checkable

# Iglewicz–Hoaglin-style scaling so MAD-based scores are comparable to σ-based Z for normal data
MAD_NORMALIZATION = 0.6745


@runtime_checkable
class CorroborationStrategy(Protocol):
    """Strategy: given leave-one-out peer values, is ``value`` an outlier?"""

    def evaluate(
        self,
        value: float,
        peer_values: list[float],
        threshold: float,
    ) -> tuple[bool, dict[str, float | str]]:
        """
        Args:
            value: Reading of the candidate node.
            peer_values: Other ALIVE nodes' readings in the same H3 cell (≥2 elements).
            threshold: Compare against ``ANOMALY_ZSCORE_THRESHOLD`` (used for both classic Z and modified Z).

        Returns:
            (is_outlier, metrics) — metrics may include ``zscore``, ``modified_z``, ``peer_median``, etc.
        """
        ...


class ClassicZScoreStrategy:
    """Classic leave-one-out Z = |x − μ_peers| / σ_peers (sample stdev)."""

    def evaluate(
        self,
        value: float,
        peer_values: list[float],
        threshold: float,
    ) -> tuple[bool, dict[str, float | str]]:
        if len(peer_values) < 2:
            return False, {"corroboration": "zscore_skip", "reason": "too_few_peers"}

        # Noise floor: prevent division by near-zero if sensors are too similar.
        # Can be made configurable via env in the future.
        MIN_SIGMA = 0.5

        sigma = max(statistics.stdev(peer_values), MIN_SIGMA)
        mu = statistics.mean(peer_values)
        z = abs(value - mu) / sigma
        return (z > threshold), {"zscore": z, "corroboration": "zscore"}


class ModifiedZScoreMADStrategy:
    """
    Robust modified Z-score using peer median and MAD:

        M = 0.6745 × |x − median(peers)| / MAD(peers)

    where MAD is the median of |p − median(peers)| over peers in the leave-one-out set.
    """

    def evaluate(
        self,
        value: float,
        peer_values: list[float],
        threshold: float,
    ) -> tuple[bool, dict[str, float | str]]:
        if len(peer_values) < 2:
            return False, {"corroboration": "mad_skip", "reason": "too_few_peers"}

        # Noise floor: if MAD is too small, use a minimum floor (e.g. 0.5 units).
        MIN_MAD = 0.5

        med = statistics.median(peer_values)
        abs_devs = [abs(p - med) for p in peer_values]
        mad = max(statistics.median(abs_devs), MIN_MAD)

        modified_z = MAD_NORMALIZATION * abs(value - med) / mad
        return (modified_z > threshold), {
            "modified_z": modified_z,
            "peer_median": med,
            "corroboration": "mad",
        }


class BothStrategy:
    """
    Conservative hybrid: outlier only if **both** classic Z-score **and** MAD-based
    modified Z exceed ``threshold`` for this leave-one-out slice.
    If either side cannot compute (σ=0, MAD=0, etc.), that side counts as **not** an outlier, so **both** rarely fires.
    """

    def __init__(
        self,
        z: CorroborationStrategy | None = None,
        mad: CorroborationStrategy | None = None,
    ) -> None:
        self._z = z or ClassicZScoreStrategy()
        self._mad = mad or ModifiedZScoreMADStrategy()

    def evaluate(
        self,
        value: float,
        peer_values: list[float],
        threshold: float,
    ) -> tuple[bool, dict[str, float | str]]:
        z_bad, z_m = self._z.evaluate(value, peer_values, threshold)
        m_bad, m_m = self._mad.evaluate(value, peer_values, threshold)
        merged: dict[str, float | str] = {"corroboration": "both"}
        for d in (z_m, m_m):
            for k, v in d.items():
                if k != "corroboration":
                    merged[k] = v
        return (z_bad and m_bad), merged


_builtin_factories: dict[str, Callable[[], CorroborationStrategy]] = {
    "mad": lambda: ModifiedZScoreMADStrategy(),
    "zscore": lambda: ClassicZScoreStrategy(),
    "both": lambda: BothStrategy(),
}

_custom_factories: dict[str, Callable[[], CorroborationStrategy]] = {}


def register_corroboration_method(
    name: str,
    factory: Callable[[], CorroborationStrategy],
) -> None:
    """Register or override a strategy name (lowercased). Intended for tests and extensions."""
    _custom_factories[name.strip().lower()] = factory


def unregister_corroboration_method(name: str) -> None:
    """Remove a custom method (no-op for built-ins). Useful in tests."""
    _custom_factories.pop(name.strip().lower(), None)


def build_corroboration_strategy(method: str | None = None) -> CorroborationStrategy:
    """
    Build a strategy from ``method`` or env ``CORROBORATION_METHOD`` (default ``mad``).
    """
    key = (
        (method if method is not None else os.getenv("CORROBORATION_METHOD", "mad"))
        .strip()
        .lower()
    )
    if key in _custom_factories:
        return _custom_factories[key]()
    if key in _builtin_factories:
        return _builtin_factories[key]()
    allowed = sorted(set(_builtin_factories) | set(_custom_factories))
    raise ValueError(
        f"Unknown CORROBORATION_METHOD={key!r}; allowed: {', '.join(allowed)}"
    )
