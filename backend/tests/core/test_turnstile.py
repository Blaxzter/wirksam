"""Tests for the Cloudflare Turnstile check (app.core.turnstile).

The one property worth testing here is that it **fails closed**. A verifier
that returns True when it cannot reach Cloudflare is worse than no verifier at
all: it looks like protection, and it stops protecting at precisely the moment
somebody is attacking the thing it guards. So most of what follows feeds
``verify_turnstile`` a different kind of broken and asserts the same False.

The network is stubbed with ``httpx.MockTransport`` rather than by replacing
``verify_turnstile``'s internals — the real client still parses the reply,
still applies ``raise_for_status``, and still raises the real exception types,
which is what makes "a 500 from siteverify is a rejection" a meaningful claim
rather than a restatement of the stub.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.core import turnstile
from app.core.config import settings
from app.core.turnstile import SITEVERIFY_URL, verify_turnstile

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the module a secret, as a deployment with Turnstile enabled has."""
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", "test-secret")


@pytest.fixture
def siteverify(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Handler], list[httpx.Request]]:
    """Answer every outbound request from a handler; return the requests made.

    ``verify_turnstile`` builds its own ``AsyncClient``, so the seam is the
    class it reaches for. Swapping in a factory that pins a ``MockTransport``
    keeps every other httpx behaviour intact.
    """

    # Captured before the patch goes on: the factory below must build a *real*
    # client, and by the time it runs ``httpx.AsyncClient`` is the factory
    # itself.
    real_client = httpx.AsyncClient

    def install(handler: Handler) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        def factory(**kwargs: Any) -> httpx.AsyncClient:
            return real_client(transport=httpx.MockTransport(record), **kwargs)

        monkeypatch.setattr(turnstile.httpx, "AsyncClient", factory)
        return seen

    return install


def _json(payload: dict[str, Any], status_code: int = 200) -> Handler:
    return lambda _request: httpx.Response(status_code, json=payload)


@pytest.mark.asyncio
class TestVerifyTurnstile:
    async def test_accepts_a_token_cloudflare_vouches_for(
        self, siteverify: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        """Test that an explicit success is the one case that returns True."""
        requests = siteverify(_json({"success": True, "hostname": "example.com"}))

        assert await verify_turnstile("solved-token") is True

        assert len(requests) == 1
        sent = requests[0]
        assert str(sent.url) == SITEVERIFY_URL
        assert sent.method == "POST"
        # Form-encoded, and carrying the pair siteverify actually reads.
        body = dict(httpx.QueryParams(sent.content.decode()))
        assert body == {"secret": "test-secret", "response": "solved-token"}

    async def test_does_not_send_the_client_ip(
        self, siteverify: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        """Test that ``remoteip`` stays out of the request.

        Cloudflare requires it to *match* when present, and a dual-stack client
        that solves the challenge over IPv6 and posts the form over IPv4 would
        fail that comparison while being an entirely real person. See the module
        docstring in ``app.core.turnstile``.
        """
        requests = siteverify(_json({"success": True}))

        await verify_turnstile("solved-token")

        assert "remoteip" not in httpx.QueryParams(requests[0].content.decode())

    async def test_rejects_a_missing_token_without_asking_cloudflare(
        self, siteverify: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        """Test that an absent token is refused locally, not round-tripped.

        This is the shape a scripted POST takes — the form field simply is not
        there — so it is also the most common rejection, and it should not cost
        a call to Cloudflare each time.
        """
        requests = siteverify(_json({"success": True}))

        assert await verify_turnstile(None) is False
        assert await verify_turnstile("") is False

        assert requests == []

    async def test_rejects_what_cloudflare_rejects(
        self, siteverify: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        """Test that ``success: false`` is a refusal, error codes and all."""
        siteverify(_json({"success": False, "error-codes": ["invalid-input-response"]}))

        assert await verify_turnstile("forged-token") is False

    async def test_rejects_a_replayed_token(
        self, siteverify: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        """Test that Cloudflare's single-use rule is honoured.

        ``timeout-or-duplicate`` is what a second submission of the same token
        earns, which is why the registration form has to reset its widget after
        a failed attempt rather than resubmit what it already has.
        """
        siteverify(_json({"success": False, "error-codes": ["timeout-or-duplicate"]}))

        assert await verify_turnstile("already-spent") is False

    async def test_rejects_when_siteverify_errors(
        self, siteverify: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        """Test that a 5xx from Cloudflare closes the door rather than opening it."""
        siteverify(_json({"success": True}, status_code=500))

        assert await verify_turnstile("solved-token") is False

    async def test_rejects_when_the_reply_is_not_json(
        self, siteverify: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        """Test that an HTML error page from a captive proxy is not a pass."""
        siteverify(lambda _r: httpx.Response(200, text="<html>Gateway</html>"))

        assert await verify_turnstile("solved-token") is False

    async def test_rejects_when_cloudflare_is_unreachable(
        self, siteverify: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        """Test the outage case: no answer at all is not consent.

        Treating an unreachable siteverify as "must be human" would mean an
        attacker who can degrade the connection also chooses when the check
        stops applying.
        """

        def timeout(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("siteverify unreachable", request=request)

        siteverify(timeout)

        assert await verify_turnstile("solved-token") is False

    async def test_a_token_solved_on_another_form_is_refused(
        self, siteverify: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        """Test that ``expected_action`` binds a token to its form.

        Without it, a token solved on the registration widget would also pass
        the shared-list sign-up.
        """
        siteverify(_json({"success": True, "action": "register"}))

        assert (
            await verify_turnstile("solved-token", expected_action="shared-list-signup")
            is False
        )

    async def test_a_token_solved_on_the_expected_form_passes(
        self, siteverify: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        """Test that the action the widget was rendered with is accepted."""
        siteverify(_json({"success": True, "action": "shared-list-signup"}))

        assert (
            await verify_turnstile("solved-token", expected_action="shared-list-signup")
            is True
        )

    async def test_without_an_expected_action_the_action_is_not_checked(
        self, siteverify: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        """Test that existing callers (registration) behave as before."""
        siteverify(_json({"success": True, "action": "anything"}))

        assert await verify_turnstile("solved-token") is True

    async def test_a_rejected_token_stays_rejected_whatever_its_action(
        self, siteverify: Callable[[Handler], list[httpx.Request]]
    ) -> None:
        siteverify(_json({"success": False, "action": "shared-list-signup"}))

        assert (
            await verify_turnstile("forged", expected_action="shared-list-signup")
            is False
        )
