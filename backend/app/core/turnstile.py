"""Cloudflare Turnstile verification for the open, unauthenticated forms.

Registration is the one endpoint a stranger can call as often as they like and
have something to show for it afterwards: a row in ``users``, a message sent to
whatever address they typed, and a name that shows up in every event's member
picker. ``app.core.rate_limit`` caps how *fast* that can happen, but it cannot
tell a person from a script — a bot that registers five accounts an hour and
then waits is inside every ceiling this codebase has.

Turnstile is the missing half. The browser solves a challenge, the form carries
the resulting token, and this module asks Cloudflare whether that token is one
it actually issued.

Three decisions worth keeping:

* **Enforcement is opt-in, on the secret alone.** It runs only when
  ``TURNSTILE_SECRET_KEY`` is set, so local development, the test suite and any
  deployment that has not signed up for Turnstile yet keep working unchanged.
  Deliberately *not* gated on ``ENVIRONMENT`` as ``emails_enabled`` is: a
  staging deployment that has the key configured should be exercising the real
  path, not a stub.

* **It fails closed.** A missing token, a rejected token, a malformed reply and
  an unreachable ``siteverify`` all return False. The tempting alternative —
  treat "Cloudflare is unreachable" as "must be human" — turns an outage into
  an open door, and hands an attacker who can *cause* that outage the choice of
  when the door opens.

* **``remoteip`` is deliberately not sent.** It is optional, and when it *is*
  sent Cloudflare requires it to match the address that solved the challenge.
  The only address available here is the one ``client_ip`` derives from
  ``X-Forwarded-For``, and on a dual-stack client the browser routinely solves
  the challenge over IPv6 and posts the form over IPv4 (or the reverse), which
  would compare two genuinely different addresses and reject a real person.
  The token is already bound to the client that solved it; the extra parameter
  buys little and its failure mode is "nobody can register", diagnosed from a
  bare ``success: false``.
"""

from typing import Any, cast

import httpx

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# This call sits on the registration hot path, in front of a user watching a
# spinner. Cloudflare answers in tens of milliseconds; anything near this bound
# means siteverify is effectively down, and waiting longer only turns a fast
# failure into a slow one.
TIMEOUT_SECONDS = 5.0


async def verify_turnstile(token: str | None) -> bool:
    """Ask Cloudflare whether ``token`` came from a solved challenge.

    Returns True only on an explicit ``success: true``. Every other outcome —
    no token, a rejection, a non-2xx reply, a body that is not JSON, a network
    error — is False, because this is the check that decides whether an
    anonymous caller gets an account.

    Never raises: the caller is a route that has to answer either way, and an
    exception escaping here would be a 500 on a form submission that Cloudflare
    merely could not vouch for.
    """
    if not token:
        return False

    payload = {"secret": settings.TURNSTILE_SECRET_KEY or "", "response": token}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(SITEVERIFY_URL, data=payload)
        response.raise_for_status()
        body: object = response.json()
    except Exception:
        # Warning rather than exception(): a siteverify timeout is an operational
        # event, not a bug in this process, and a stack trace per blocked
        # registration would bury the outage it is reporting.
        logger.warning(
            "Turnstile siteverify was unreachable; treating the challenge as "
            "unsolved. Registration is closed until it answers again.",
            exc_info=True,
        )
        return False

    # A 200 whose body is not the documented object is not a pass. Captive
    # portals and misrouted proxies both answer 200 with HTML, and reading a
    # missing "success" as anything but a rejection is how a verifier ends up
    # waving those through.
    if not isinstance(body, dict):
        logger.warning("Turnstile siteverify answered with a non-object body")
        return False

    data = cast(dict[str, Any], body)
    if data.get("success") is True:
        return True

    # The codes are Cloudflare's own ("invalid-input-response",
    # "timeout-or-duplicate", "invalid-input-secret", …) and are the only way to
    # tell a bot being turned away from a misconfigured deployment turning
    # everyone away. They describe the *token*, never the person, so there is
    # nothing here worth withholding from the log.
    logger.info(f"Turnstile rejected a challenge token: {data.get('error-codes')}")
    return False
