"""A small in-process rate limiter for the authentication endpoints.

Login, registration and password reset are the three routes an attacker gets to
call as often as they like, so they are the three that need a ceiling:
credential stuffing, mass account creation and reset-email flooding are all
"same request, many times" attacks.

**What this is honestly worth.** The counters live in a plain dict in the
process that serves the request. ``backend/Dockerfile`` starts the API with
``fastapi run --workers 4``, and each of those four worker processes gets its
own dict — so a limit of "10 per 5 minutes" is really "10 per 5 minutes *per
worker*", i.e. up to 40 in the worst case where the OS spreads an attacker's
requests evenly. Restarting the container resets every counter, and a second
API replica would double the ceiling again.

That approximation is deliberate. The stack has no Redis (``docker-compose.yml``
runs db, adminer, prestart, backend, frontend, mailcatcher and nothing else) and
a Postgres-backed counter would put a write on the hot path of every login,
including the ones that fail. A 4x-loose limit still turns an unthrottled
credential-stuffing run into a rounding error; if that stops being enough, the
replacement is a shared store behind the same ``RateLimiter.check`` call, not a
cleverer dict.

**Disabled under ``settings.TESTING``.** The Playwright suite runs six workers
in parallel against one backend, all logging in as a handful of seeded users
from a single IP. Any sane per-IP limit trips within seconds and surfaces as
random 429s in unrelated specs — a bug that reads as flakiness. The unit tests
in ``tests/core/test_rate_limit.py`` flip the flag off explicitly so the counting
logic itself is still exercised.
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass

from fastapi import Request

from app.core.config import settings
from app.core.errors import raise_problem

# Above this many tracked keys a check also sweeps out the expired ones. Keys
# are attacker-controlled (an IP, an email address), so without a sweep a
# long-running process would accumulate one entry per address ever tried —
# a slow memory leak with an obvious trigger. The threshold keeps the sweep off
# the hot path for any realistic amount of legitimate traffic.
_PRUNE_THRESHOLD = 1024


@dataclass(slots=True)
class _Window:
    """One fixed window: how many hits it has seen and when it lapses."""

    hits: int
    expires_at: float


class RateLimiter:
    """A fixed-window counter, keyed by whatever the caller considers an actor.

    Fixed windows rather than a sliding log or token bucket: the failure mode is
    that a caller can spend its whole allowance at the end of one window and
    again at the start of the next (up to 2x the limit across a window
    boundary), which is a far better trade here than storing a timestamp per
    request for every address that has ever guessed a password.

    One instance per bucket. The instance *is* the bucket — ``check("1.2.3.4")``
    on the login limiter and on the register limiter count independently — which
    is why keys passed in only need to identify the actor, not the action.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows: dict[str, _Window] = {}
        # Every mutation of `_windows` happens between an await-free read and
        # write, so on a single event loop the lock is belt-and-braces. It costs
        # nothing and it means a future maintainer who adds an `await` inside
        # the critical section does not silently introduce a race that only
        # shows up as an under-count under load.
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> None:
        """Count one attempt by ``key``, raising a 429 problem once over budget.

        Call this *before* doing the work, and — for anything credential-shaped
        — count failures and successes alike. A limiter that only counts
        failures still lets an attacker walk the whole password list; it just
        stops counting the moment they find the right one.
        """
        if settings.TESTING:
            return

        now = time.monotonic()
        async with self._lock:
            if len(self._windows) > _PRUNE_THRESHOLD:
                self._prune(now)

            window = self._windows.get(key)
            if window is None or window.expires_at <= now:
                self._windows[key] = _Window(
                    hits=1, expires_at=now + self.window_seconds
                )
                return

            window.hits += 1
            if window.hits <= self.limit:
                return
            retry_after = max(1, math.ceil(window.expires_at - now))

        # Raised outside the lock: raise_problem builds an HTTPException, and
        # unwinding a raise through an `async with` is needless work to hold a
        # lock across.
        raise_problem(
            429,
            code="auth.rate_limited",
            detail=(f"Too many attempts. Please try again in {retry_after} seconds."),
            headers={"Retry-After": str(retry_after)},
        )

    def _prune(self, now: float) -> None:
        expired = [
            key for key, window in self._windows.items() if window.expires_at <= now
        ]
        for key in expired:
            del self._windows[key]

    def reset(self) -> None:
        """Forget every counter. For tests, and for nothing else."""
        self._windows.clear()


def client_ip(request: Request) -> str:
    """The caller's address, for use as a rate-limit key.

    Behind Traefik the socket's peer is the proxy for *every* caller; keying on
    it would put the whole internet in one bucket. ``ProxyHeadersMiddleware``
    (``app/main.py``) has already replaced it with the rightmost
    ``X-Forwarded-For`` entry that is not a trusted proxy
    (``FORWARDED_ALLOW_IPS``). A trusted proxy wrote that entry, so a caller
    cannot pick its own key by sending the header, which the leftmost entry
    would have let it do.
    """
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


# The buckets. Limits are per worker process (see the module docstring) and each
# entry names the key its callers must pass, because a mismatched key is the one
# bug here that fails silently — it still rate-limits, just the wrong thing.

# 10 per 5 minutes, keyed by "<ip>|<email>": tight enough to make guessing one
# account's password pointless, loose enough that a household behind one NAT and
# a user with caps lock on both survive.
login_limiter = RateLimiter(limit=10, window_seconds=5 * 60)

# 5 per hour, keyed by IP. Registration is a once-ever action for a real person.
register_limiter = RateLimiter(limit=5, window_seconds=60 * 60)

# 5 per hour, keyed by "<ip>|<email>". Each call sends mail to an address the
# caller chose, so the thing being limited is inbox flooding, not guessing.
forgot_password_limiter = RateLimiter(limit=5, window_seconds=60 * 60)

# 10 per hour, keyed by IP. Reset tokens are 256-bit; this exists to stop the
# hopeless brute-forcing of one from also being free.
reset_password_limiter = RateLimiter(limit=10, window_seconds=60 * 60)

# 3 per hour, keyed by user id — this route is authenticated, so the caller is
# known and their IP is irrelevant.
resend_verification_limiter = RateLimiter(limit=3, window_seconds=60 * 60)

# 3 per hour, keyed by IP. Anonymous *and* write-heavy: one call seeds an event,
# a dozen tasks, a few hundred shifts and a handful of accounts. Treat this as
# a courtesy speed bump only — the ceiling that actually protects the database
# is SANDBOX_MAX_ACTIVE, counted in SQL, because these counters are per worker
# process and this method returns immediately under TESTING.
sandbox_limiter = RateLimiter(limit=3, window_seconds=60 * 60)
