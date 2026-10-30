# pyright: reportPrivateUsage=false
"""Tests for the in-process rate limiter (app.core.rate_limit).

Every test that exercises counting has to turn ``settings.TESTING`` off first —
the limiter is a deliberate no-op while it is on, so that six parallel Playwright
workers hammering one backend do not trip a per-IP limit and read as flakiness.
The ``limiter`` fixture does that, and ``TestDisabledUnderTesting`` asserts the
no-op itself.

Time is driven by a fake ``monotonic`` rather than by sleeping, so a
window-expiry test costs microseconds instead of the five minutes the login
bucket actually spans.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import HTTPException, Request

from app.core import rate_limit
from app.core.config import settings
from app.core.rate_limit import (
    RateLimiter,
    client_ip,
    forgot_password_limiter,
    login_limiter,
    register_limiter,
    resend_verification_limiter,
    reset_password_limiter,
)


class _FakeClock:
    """A stand-in for the ``time`` module with a hand-cranked monotonic clock."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    fake = _FakeClock()
    monkeypatch.setattr(rate_limit, "time", fake)
    return fake


@pytest.fixture
def limiter(monkeypatch: pytest.MonkeyPatch) -> RateLimiter:
    """A fresh 3-per-60s limiter with the TESTING no-op switched off."""
    monkeypatch.setattr(settings, "TESTING", False)
    return RateLimiter(limit=3, window_seconds=60)


def _request(headers: dict[str, str] | None = None, *, client: Any = ...) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": [
            (key.lower().encode(), value.encode())
            for key, value in (headers or {}).items()
        ],
    }
    if client is not ...:
        scope["client"] = client
    return Request(scope)


class TestDisabledUnderTesting:
    async def test_that_the_limiter_never_fires_while_testing(self) -> None:
        """Test that the E2E suite cannot be throttled by its own traffic."""
        assert settings.TESTING is True
        quiet = RateLimiter(limit=1, window_seconds=60)
        for _ in range(50):
            await quiet.check("same-key")

    async def test_that_nothing_is_recorded_while_testing(self) -> None:
        """Test that the no-op is a real short-circuit, not a silent count."""
        quiet = RateLimiter(limit=1, window_seconds=60)
        await quiet.check("same-key")
        assert quiet._windows == {}


class TestWithinLimit:
    async def test_that_the_first_call_passes(self, limiter: RateLimiter) -> None:
        """Test that a previously unseen key is allowed."""
        await limiter.check("1.2.3.4")

    async def test_that_the_whole_allowance_passes(self, limiter: RateLimiter) -> None:
        """Test that exactly `limit` attempts are permitted."""
        for _ in range(3):
            await limiter.check("1.2.3.4")

    async def test_that_keys_are_counted_independently(
        self, limiter: RateLimiter
    ) -> None:
        """Test that one noisy address cannot lock out another."""
        for _ in range(3):
            await limiter.check("noisy")
        await limiter.check("quiet")

    async def test_that_buckets_are_independent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that spending the login budget leaves registration alone."""
        monkeypatch.setattr(settings, "TESTING", False)
        first = RateLimiter(limit=1, window_seconds=60)
        second = RateLimiter(limit=1, window_seconds=60)
        await first.check("1.2.3.4")
        await second.check("1.2.3.4")


class TestOverLimit:
    async def test_that_the_next_attempt_is_refused(self, limiter: RateLimiter) -> None:
        """Test that attempt limit+1 raises."""
        for _ in range(3):
            await limiter.check("1.2.3.4")
        with pytest.raises(HTTPException):
            await limiter.check("1.2.3.4")

    async def test_that_it_raises_a_429_problem(
        self, limiter: RateLimiter, clock: _FakeClock
    ) -> None:
        """Test that the refusal carries the auth.rate_limited problem code."""
        for _ in range(3):
            await limiter.check("1.2.3.4")
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check("1.2.3.4")
        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == {
            "code": "auth.rate_limited",
            "type": "urn:problem:auth.rate_limited",
            "detail": "Too many attempts. Please try again in 60 seconds.",
        }

    async def test_that_it_sets_retry_after(
        self, limiter: RateLimiter, clock: _FakeClock
    ) -> None:
        """Test that the client is told how long to wait."""
        for _ in range(3):
            await limiter.check("1.2.3.4")
        clock.advance(20)
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check("1.2.3.4")
        assert exc_info.value.headers is not None
        assert exc_info.value.headers["Retry-After"] == "40"

    async def test_that_retry_after_is_never_zero(
        self, limiter: RateLimiter, clock: _FakeClock
    ) -> None:
        """Test that a window about to lapse still asks for a one-second wait."""
        for _ in range(3):
            await limiter.check("1.2.3.4")
        clock.advance(59.9)
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check("1.2.3.4")
        assert exc_info.value.headers is not None
        assert exc_info.value.headers["Retry-After"] == "1"

    async def test_that_a_refused_attempt_still_counts(
        self, limiter: RateLimiter
    ) -> None:
        """Test that hammering a blocked key does not reset anything."""
        for _ in range(3):
            await limiter.check("1.2.3.4")
        for _ in range(5):
            with pytest.raises(HTTPException):
                await limiter.check("1.2.3.4")
        assert limiter._windows["1.2.3.4"].hits == 8


class TestWindowExpiry:
    async def test_that_the_allowance_returns_after_the_window(
        self, limiter: RateLimiter, clock: _FakeClock
    ) -> None:
        """Test that a lapsed window starts a fresh count."""
        for _ in range(3):
            await limiter.check("1.2.3.4")
        clock.advance(61)
        await limiter.check("1.2.3.4")

    async def test_that_the_window_does_not_slide(
        self, limiter: RateLimiter, clock: _FakeClock
    ) -> None:
        """Test that attempts inside one window share its deadline."""
        await limiter.check("1.2.3.4")
        clock.advance(59)
        await limiter.check("1.2.3.4")
        await limiter.check("1.2.3.4")
        with pytest.raises(HTTPException):
            await limiter.check("1.2.3.4")


class TestPruning:
    async def test_that_expired_keys_are_swept_once_the_dict_grows(
        self, limiter: RateLimiter, clock: _FakeClock
    ) -> None:
        """Test that attacker-supplied keys do not accumulate forever."""
        for index in range(rate_limit._PRUNE_THRESHOLD + 1):
            await limiter.check(f"key-{index}")
        clock.advance(61)
        await limiter.check("survivor")
        assert list(limiter._windows) == ["survivor"]

    async def test_that_live_keys_survive_the_sweep(
        self, limiter: RateLimiter, clock: _FakeClock
    ) -> None:
        """Test that pruning only drops windows that have actually lapsed."""
        for index in range(rate_limit._PRUNE_THRESHOLD + 1):
            await limiter.check(f"key-{index}")
        await limiter.check("late-arrival")
        assert len(limiter._windows) > rate_limit._PRUNE_THRESHOLD


class TestConcurrency:
    async def test_that_parallel_checks_are_counted_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that concurrent attempts on one key cannot under-count."""
        monkeypatch.setattr(settings, "TESTING", False)
        limiter = RateLimiter(limit=5, window_seconds=60)
        results = await asyncio.gather(
            *(limiter.check("1.2.3.4") for _ in range(20)),
            return_exceptions=True,
        )
        refused = [item for item in results if isinstance(item, HTTPException)]
        assert len(refused) == 15


class TestReset:
    async def test_that_reset_clears_every_counter(self, limiter: RateLimiter) -> None:
        """Test that reset() hands the whole allowance back."""
        for _ in range(3):
            await limiter.check("1.2.3.4")
        limiter.reset()
        await limiter.check("1.2.3.4")


class TestClientIp:
    def test_that_the_peer_address_is_the_key(self) -> None:
        """Test that the client the proxy middleware settled on is keyed."""
        request = _request(client=("198.51.100.4", 51234))
        assert client_ip(request) == "198.51.100.4"

    def test_that_the_header_alone_counts_for_nothing(self) -> None:
        """Test that X-Forwarded-For is left to the middleware, not read here."""
        request = _request(
            {"x-forwarded-for": "203.0.113.7"}, client=("198.51.100.4", 1)
        )
        assert client_ip(request) == "198.51.100.4"

    def test_that_a_missing_client_is_survivable(self) -> None:
        """Test that an ASGI scope without a client does not raise."""
        request = _request(client=None)
        assert client_ip(request) == "unknown"


class TestConfiguredBuckets:
    def test_login_bucket(self) -> None:
        """Test that login allows 10 attempts per 5 minutes."""
        assert (login_limiter.limit, login_limiter.window_seconds) == (10, 300)

    def test_register_bucket(self) -> None:
        """Test that registration allows 5 per hour."""
        assert (register_limiter.limit, register_limiter.window_seconds) == (5, 3600)

    def test_forgot_password_bucket(self) -> None:
        """Test that forgot-password allows 5 per hour."""
        assert (
            forgot_password_limiter.limit,
            forgot_password_limiter.window_seconds,
        ) == (5, 3600)

    def test_reset_password_bucket(self) -> None:
        """Test that reset-password allows 10 per hour."""
        assert (
            reset_password_limiter.limit,
            reset_password_limiter.window_seconds,
        ) == (10, 3600)

    def test_resend_verification_bucket(self) -> None:
        """Test that resending a verification email allows 3 per hour."""
        assert (
            resend_verification_limiter.limit,
            resend_verification_limiter.window_seconds,
        ) == (3, 3600)

    def test_that_the_buckets_are_distinct_objects(self) -> None:
        """Test that no two routes accidentally share one counter."""
        buckets = [
            login_limiter,
            register_limiter,
            forgot_password_limiter,
            reset_password_limiter,
            resend_verification_limiter,
        ]
        assert len({id(bucket) for bucket in buckets}) == len(buckets)
