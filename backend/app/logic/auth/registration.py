"""Who may create an account, and what state the new account starts in.

The hosted instance runs open signup, but a deployment hosting its own copy can
put a door on it with three settings in ``app.core.config`` (read the comment
there for what each one means). Everything that decides *whether* a signup goes
through and *what status* it gets lives in this module, so the rules can be read
in one place and tested without a client:

* ``registration_policy`` is the configured policy, and the public summary the
  registration form renders. ``policy_for_request`` is the same thing with the
  E2E override applied (see below).
* ``admit_registration`` is the gate ``register_user`` calls before it writes a
  row. It either raises a problem the form can show, or returns the
  ``approval_status`` the account starts with.

The policy is passed in rather than read from ``settings`` inside the gate, for
the E2E suite's sake. Its backend runs four worker processes, so a test cannot
switch the mode by changing a setting: only the process that served that call
would see it. Instead, while ``TESTING`` is on, a request may carry the policy
it wants in ``X-Test-Registration-Policy``, the same way ``X-Test-User-Email``
carries an identity. Nothing global changes, so specs for different modes run
side by side.

Two exemptions apply in every mode, and both exist so a deployment cannot lock
itself out:

* An address in ``SUPERADMIN_EMAILS`` always gets in, approved. On a fresh
  "approval" or "invite" deployment the first superadmin is the only person who
  could approve or invite anyone else.
* A valid invitation addressed to the person signing up (or a link invitation
  they arrived through) counts as the decision the queue would have made, when
  ``REGISTRATION_INVITE_BYPASS`` is on. In "invite" mode it is required anyway.
"""

from __future__ import annotations

from fastapi import Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.core.errors import raise_problem
from app.crud.event_invitation import event_invitation as crud_invitation
from app.crud.event_invitation import invitation_invalid_reason
from app.models.event import Event
from app.models.event_invitation import EventInvitation
from app.schemas.auth import RegistrationPolicy
from app.schemas.user import ApprovalStatus

TEST_POLICY_HEADER = "X-Test-Registration-Policy"


def registration_policy() -> RegistrationPolicy:
    return RegistrationPolicy(
        mode=settings.REGISTRATION_MODE,
        allowed_domains=settings.registration_domains,
        invite_bypass=settings.REGISTRATION_INVITE_BYPASS,
    )


def policy_for_request(request: Request) -> RegistrationPolicy:
    """The configured policy, or the one a test request asked for.

    The header is ignored outright unless ``TESTING`` is on, so in production
    it is a header like any other. A malformed one is a 400 rather than a quiet
    fallback: a spec that thinks it is testing invite mode while the server ran
    open signup would pass for the wrong reason.
    """
    raw = request.headers.get(TEST_POLICY_HEADER)
    if not settings.TESTING or not raw:
        return registration_policy()
    try:
        policy = RegistrationPolicy.model_validate_json(raw)
    except ValidationError:
        raise_problem(
            400,
            code="testing.invalid_registration_policy",
            detail=f"{TEST_POLICY_HEADER} is not a valid registration policy.",
        )
    policy.allowed_domains = [
        d.strip().lstrip("@").lower() for d in policy.allowed_domains if d.strip()
    ]
    return policy


def is_superadmin_email(email: str) -> bool:
    configured = {str(address).lower() for address in settings.SUPERADMIN_EMAILS}
    return email.lower() in configured


def email_domain_allowed(email: str, domains: list[str]) -> bool:
    if not domains:
        return True
    return email.rsplit("@", 1)[-1].lower() in domains


async def _is_sandbox_event(db: AsyncSession, invitation: EventInvitation) -> bool:
    # A demo event's invitation must not open the door to a real account: the
    # demo is anonymous by design, and anyone can start one.
    is_sandbox = await db.scalar(
        select(col(Event.is_sandbox)).where(col(Event.id) == invitation.event_id)
    )
    return bool(is_sandbox)


async def has_valid_invitation(
    db: AsyncSession, *, email: str, invitation_token: str | None
) -> bool:
    """Whether this person holds an invitation that is still redeemable.

    Either the link they arrived through, or an open invitation sent to their
    address before they had an account. The second case matters because the
    mail an event admin sends links to the invitation, but a person who
    registers from the front page instead is no less invited.
    """
    if invitation_token:
        invitation = await crud_invitation.get_by_token(db, token=invitation_token)
        if (
            invitation is not None
            and invitation_invalid_reason(invitation) is None
            and (invitation.email is None or invitation.email.lower() == email.lower())
            and not await _is_sandbox_event(db, invitation)
        ):
            return True

    for invitation in await crud_invitation.list_pending_for_email(db, email=email):
        if not await _is_sandbox_event(db, invitation):
            return True
    return False


async def admit_registration(
    db: AsyncSession,
    *,
    email: str,
    invitation_token: str | None,
    policy: RegistrationPolicy,
) -> ApprovalStatus:
    """Refuse the signup, or say what status the new account starts with.

    Raises a 403 problem with a code the form can explain:

    * ``auth.invitation_required``: "invite" mode and no usable invitation.
    * ``auth.email_domain_not_allowed``: the address is outside
      the allowed domains and no invitation lets it past.
    """
    if is_superadmin_email(email):
        return "approved"

    mode = policy.mode
    # Only looked up when it can change the answer: in "open" mode with no
    # domain list there is nothing for an invitation to bypass.
    invited = False
    if mode == "invite" or (
        policy.invite_bypass and (mode == "approval" or policy.allowed_domains)
    ):
        invited = await has_valid_invitation(
            db, email=email, invitation_token=invitation_token
        )

    if mode == "invite" and not invited:
        raise_problem(
            403,
            code="auth.invitation_required",
            detail="Accounts on this site are by invitation only.",
        )

    bypass = invited and policy.invite_bypass
    if not email_domain_allowed(email, policy.allowed_domains) and not bypass:
        raise_problem(
            403,
            code="auth.email_domain_not_allowed",
            detail="This email address cannot be used to sign up on this site.",
        )

    if mode == "approval" and not bypass:
        return "pending"
    return "approved"
