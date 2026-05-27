"""
tests/unit/test_rate_limiter.py

Unit tests for the token-bucket rate limiter embedded in zmq_listener.
"""

import time

from src.network.zmq_mesh import _TokenBucket


class TestTokenBucket:
    """Tests for _TokenBucket rate limiter."""

    def test_allows_within_burst(self) -> None:
        """Consuming up to burst capacity should always succeed."""
        bucket = _TokenBucket(rate=10.0, burst=5)
        results = [bucket.consume() for _ in range(5)]
        assert all(results), "All burst tokens should be allowed"

    def test_blocks_over_burst(self) -> None:
        """After burst is exhausted (without refill time), consume returns False."""
        bucket = _TokenBucket(rate=10.0, burst=3)
        for _ in range(3):
            bucket.consume()
        assert not bucket.consume(), "Should be blocked after burst exhausted"

    def test_refills_over_time(self) -> None:
        """After waiting, tokens refill according to rate."""
        bucket = _TokenBucket(rate=100.0, burst=5)
        # Exhaust all tokens
        for _ in range(5):
            bucket.consume()
        assert not bucket.consume()

        # Wait enough time for at least 1 token refill (100 tokens/s → 10ms per token)
        time.sleep(0.05)
        assert bucket.consume(), "Should have refilled after waiting"

    def test_burst_caps_tokens(self) -> None:
        """Tokens never exceed burst capacity, even after long waits."""
        bucket = _TokenBucket(rate=1000.0, burst=3)
        time.sleep(0.05)  # would add 50 tokens at 1000/s, but capped at 3
        results = [bucket.consume() for _ in range(4)]
        assert results[:3] == [True, True, True]
        assert results[3] is False

    def test_zero_burst_always_blocks(self) -> None:
        """With burst=0, no tokens are ever available."""
        bucket = _TokenBucket(rate=100.0, burst=0)
        assert not bucket.consume()
