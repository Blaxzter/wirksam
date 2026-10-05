"""The authentication flows: what actually happens on register, sign-in, reset.

Everything here takes an ``AsyncSession`` and returns data. Nothing here knows
about cookies, headers, status codes for *success*, background tasks or the
request at all — those belong to ``app.api.routes.auth``, which is a thin
adapter over this module. The split is what makes the flows testable without a
client, and it is why the route file reads as a list of eleven short functions.

Two things in this module are load-bearing beyond their size:

* ``sync_superadmin_role`` is the **only** mechanism that grants the platform
  admin role. On a fresh deployment nobody has it, no route can grant it, and
  the first person to register or sign in with an address listed in
  ``SUPERADMIN_EMAILS`` becomes the administrator. Delete it and a new
  installation has no way to reach the admin screens at all.
* ``build_user_profile`` resolves the caller's role in each of their events.
  The frontend renders its entire navigation from that map, so a login response
  without it shows a signed-in user with no events.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.core.errors import raise_problem
from app.core.security import create_access_token, verify_password
from app.crud.auth_session import auth_session as crud_auth_session
from app.crud.event_membership import event_membership as crud_membership
from app.crud.user import user as crud_user
from app.crud.user_token import user_token as crud_user_token
from app.logic.auth.passwords import hash_new_password
from app.logic.auth.registration import admit_registration, registration_policy
from app.logic.auth.tokens import (
    consume_user_token,
    issue_refresh_session,
    issue_user_token,
    revoke_all_sessions,
    revoke_refresh_session,
    rotate_refresh_session,
)
from app.models.auth_session import AuthSession
from app.models.event import Event
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    RegistrationPolicy,
)
from app.schemas.user import UserCreate
from app.schemas.users import UserProfile

# Local password accounts get their own identity prefix, alongside the two that
# already carry behaviour: ``demo|`` accounts are the ones every notification
# channel refuses to send to, and ``test|`` accounts are the ones the E2E reset
# endpoint is allowed to delete. A registration that produced a bare UUID would
# be indistinguishable from either.
LOCAL_SUBJECT_PREFIX = "local|"


@dataclass(frozen=True, slots=True)
class SignedInSession:
    """Everything a successful register or sign-in produces.

    ``refresh_token`` is the raw value destined for the httpOnly cookie and
    must never reach a response body; ``access_token`` is the opposite, and is
    the only one of the two the client's JavaScript is allowed to see.
    """

    user: User
    access_token: str
    expires_in: int
    refresh_token: str
    session_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class RegisteredAccount:
    """A new account, signed in, plus the secret for its verification mail.

    The token is handed back rather than mailed here so that the route can
    dispatch it through ``BackgroundTasks`` — the mail must not be sent from
    inside the transaction that creates the account, or a rollback would leave
    a live link pointing at a user that does not exist.
    """

    session: SignedInSession
    verification_token: str


@dataclass(frozen=True, slots=True)
class RefreshedSession:
    """A rotated refresh token and the access token minted alongside it."""

    access_token: str
    expires_in: int
    refresh_token: str


@dataclass(frozen=True, slots=True)
class PasswordResetLink:
    """A reset link waiting to be mailed, when the address matched an account.

    Carries the four values the mail needs rather than the ``User`` it came
    from, so the route can hand them straight to a background task. Note that
    ``email`` is the address **on the account**, not the one that was typed
    into the form: the lookup is case-insensitive, and the message should go to
    the address its owner registered.
    """

    token: str
    email: str
    name: str | None
    language: str


# ── Roles and profile ─────────────────────────────────────────────


def sync_superadmin_role(user: User) -> bool:
    """Grant the platform admin role to a configured superadmin address.

    Called on both registration and sign-in, and the reason it must be called
    on *sign-in* too is bootstrapping order: an operator typically adds their
    address to ``SUPERADMIN_EMAILS`` after discovering they cannot reach the
    admin screens, by which time their account already exists. Registration
    alone would mean deleting and recreating it.

    Activation rides along with the role. An account that a moderator suspended
    is reactivated here if it is listed, on the grounds that the list is a
    deployment-level statement about who runs the platform and outranks a
    moderation decision — and because locking the only administrator out of
    their own installation has no recovery path through the UI.

    Removal is deliberately **not** mirrored: taking an address off the list
    does not strip the role. Roles are also granted by hand through the admin
    screens, and a startup-time reconciliation would silently undo those. Use
    the user-management screen to demote someone.

    Returns whether anything changed, so the caller can skip a pointless write.
    """
    if not user.email:
        return False

    # Compared case-insensitively, matching ``crud_user.get_by_email`` and the
    # ``lower(email)`` unique index. The previous implementation compared the
    # raw strings, so an operator who wrote "Admin@example.com" in the env file
    # while the account held "admin@example.com" got no role and no explanation.
    configured = {str(address).lower() for address in settings.SUPERADMIN_EMAILS}
    if user.email.lower() not in configured:
        return False

    changed = False
    if "admin" not in user.roles:
        # Reassigned rather than appended: ``roles`` is a JSONB column, and
        # SQLAlchemy only notices a mutation if the attribute itself is set.
        user.roles = [*user.roles, "admin"]
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True
    # Same reasoning for the registration queue: the superadmin is the person
    # who would approve it, so they cannot be left waiting in it.
    if user.approval_status != "approved":
        user.approval_status = "approved"
        user.rejection_reason = None
        changed = True
    return changed


async def build_user_profile(db: AsyncSession, user: User) -> UserProfile:
    """Serialise a user together with their role in each of their events.

    ``event_roles`` is not a column; it is a join the frontend needs on every
    profile load to decide what to render, so it is resolved once here rather
    than by one request per event.
    """
    roles_by_event = await crud_membership.get_roles_for_user(db, user_id=user.id)
    profile = UserProfile.model_validate(user)
    profile.event_roles = {str(k): v for k, v in roles_by_event.items()}
    if user.is_sandbox:
        # The demo banner counts down to this. Resolving it here — rather than
        # duplicating the deadline onto the user row — keeps one source of
        # truth for when the sweep will take the event away.
        profile.sandbox_expires_at = (
            (
                await db.execute(
                    select(col(Event.sandbox_expires_at)).where(
                        col(Event.is_sandbox).is_(True),
                        col(Event.created_by_id) == user.id,
                    )
                )
            )
            .scalars()
            .first()
        )
    return profile


# ── Sign-in and registration ──────────────────────────────────────


async def _sign_in(
    db: AsyncSession,
    *,
    user: User,
    user_agent: str | None,
    ip_address: str | None,
) -> SignedInSession:
    """Open a session for a user who has already proved who they are."""
    issued = await issue_refresh_session(
        db, user_id=user.id, user_agent=user_agent, ip_address=ip_address
    )
    access_token, expires_in = create_access_token(
        user_id=user.id, session_id=issued.session.id
    )
    return SignedInSession(
        user=user,
        access_token=access_token,
        expires_in=expires_in,
        refresh_token=issued.raw_token,
        session_id=issued.session.id,
    )


async def sign_in_user(
    db: AsyncSession,
    *,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> SignedInSession:
    """Open a session for a user this module did not authenticate itself.

    The one supported caller is ``logic.sandbox``, which mints a guest account
    and needs it signed in without a credential to check — there is none, and
    there never will be: sandbox rows carry a NULL ``password_hash``, which
    ``verify_password`` folds to a failed comparison.

    It exists so that path goes through the same session machinery as every
    other login rather than reaching for ``issue_refresh_session`` and
    ``create_access_token`` on its own. Anything that reimplements those two
    will eventually disagree with them about expiry, rotation or revocation.
    """
    return await _sign_in(db, user=user, user_agent=user_agent, ip_address=ip_address)


async def register_user(
    db: AsyncSession,
    *,
    data: RegisterRequest,
    user_agent: str | None = None,
    ip_address: str | None = None,
    policy: RegistrationPolicy | None = None,
) -> RegisteredAccount:
    """Create an account, sign it in, and mint its verification token.

    Whether the signup is allowed at all, and whether the account works at once
    or waits for a superadmin, is ``logic.auth.registration``'s decision. An
    account that is let in still grants nothing on its own: every permission in
    this application is per-event membership, so an account with no memberships
    can see nothing but its own profile.

    A pending account is signed in all the same. It needs a session to be told
    it is waiting, and every route behind ``CurrentUser`` refuses it until a
    superadmin approves it.

    The address is checked for uniqueness *and* the insert is guarded, because
    the check and the insert are not atomic. A double-clicked submit button
    sends two requests that both pass the check and then race on
    ``ix_users_email_lower``; without the guard the loser gets a 500 for what is
    plainly "you already have an account".
    """
    email = str(data.email)
    if await crud_user.get_by_email(db, email=email) is not None:
        raise_problem(
            409,
            code="auth.email_taken",
            detail="An account with this email address already exists.",
        )

    # After the duplicate check, so an existing account is told it exists
    # rather than that it needs an invitation it does not need.
    approval_status = await admit_registration(
        db,
        email=email,
        invitation_token=data.invitation_token,
        policy=policy or registration_policy(),
    )

    # Hashed before the row is written, so a password the policy rejects costs
    # an INSERT that has to be rolled back. bcrypt takes roughly a quarter of a
    # second and blocks this worker for the duration; that is accepted here (see
    # the note in ``app.core.security``) because registration is rare.
    password_hash = hash_new_password(data.password)

    try:
        user = await crud_user.create(
            db,
            obj_in=UserCreate(
                subject=f"{LOCAL_SUBJECT_PREFIX}{uuid.uuid4().hex}",
                email=email,
                name=data.name,
                email_verified=False,
                is_active=True,
                approval_status=approval_status,
                preferred_language=data.preferred_language,
            ),
        )
    except IntegrityError:
        raise_problem(
            409,
            code="auth.email_taken",
            detail="An account with this email address already exists.",
        )

    # ``UserCreate`` has no ``password_hash`` field on purpose — it is also the
    # body of the admin-facing user-creation endpoint, and a schema that accepts
    # a hash is a schema that can be handed one. The value is stamped onto the
    # row we just made instead; both statements are in the same transaction.
    user.password_hash = password_hash
    _ = sync_superadmin_role(user)
    db.add(user)
    await db.flush()

    verification_token = await issue_user_token(
        db, user_id=user.id, purpose="verify_email"
    )
    session = await _sign_in(
        db, user=user, user_agent=user_agent, ip_address=ip_address
    )
    return RegisteredAccount(session=session, verification_token=verification_token)


async def authenticate(
    db: AsyncSession,
    *,
    data: LoginRequest,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> SignedInSession:
    """Check credentials and open a session.

    An unknown address and a wrong password produce the same code, the same
    sentence and — because ``verify_password`` burns the same CPU against a
    dummy hash when there is nothing to check — very nearly the same latency.
    Anything else turns this endpoint into a "does this person have an account
    here?" oracle, which for a volunteer-scheduling app is a real disclosure.

    A suspended account **can** still sign in. Its tokens open nothing:
    ``CurrentUser`` refuses an inactive user on every protected route. What
    signing in buys is the profile read behind ``AnyUser``, which is how the
    frontend knows to show "your account is awaiting approval" and the reason
    given, instead of a login form that rejects a correct password with no
    explanation.
    """
    user = await crud_user.get_by_email(db, email=str(data.email))
    password_ok = verify_password(
        data.password, user.password_hash if user is not None else None
    )
    if user is None or not password_ok:
        raise_problem(
            401,
            code="auth.invalid_credentials",
            detail="That email address and password do not match an account.",
        )

    if sync_superadmin_role(user):
        db.add(user)
        await db.flush()

    return await _sign_in(db, user=user, user_agent=user_agent, ip_address=ip_address)


async def refresh_session(
    db: AsyncSession, *, refresh_token: str | None
) -> RefreshedSession:
    """Rotate a refresh token and mint the access token that goes with it.

    A missing cookie is answered with the same 401 as a bad one. It is the
    ordinary state of a browser that has never signed in, and it is what the
    frontend's ``bootstrap()`` call at app start expects to receive; there is
    nothing to distinguish and nothing useful to say.
    """
    if not refresh_token:
        raise_problem(
            401,
            code="auth.invalid_token",
            detail="You are not signed in.",
        )

    issued = await rotate_refresh_session(db, raw_token=refresh_token)
    access_token, expires_in = create_access_token(
        user_id=issued.session.user_id, session_id=issued.session.id
    )
    return RefreshedSession(
        access_token=access_token,
        expires_in=expires_in,
        refresh_token=issued.raw_token,
    )


async def sign_out(db: AsyncSession, *, refresh_token: str | None) -> bool:
    """End the session the presented refresh token belongs to."""
    return await revoke_refresh_session(db, raw_token=refresh_token)


# ── Password reset ────────────────────────────────────────────────


async def request_password_reset(
    db: AsyncSession, *, email: str
) -> PasswordResetLink | None:
    """Mint a reset token for an address, or ``None`` if nobody owns it.

    The caller answers 202 either way — the distinction never reaches the
    client. It is returned here only so the route knows whether there is a mail
    to schedule.

    Accounts with no password at all are included deliberately: this is exactly
    how a demo account, or one provisioned before local authentication existed,
    acquires its first password.
    """
    user = await crud_user.get_by_email(db, email=email)
    if user is None or not user.email:
        return None
    token = await issue_user_token(db, user_id=user.id, purpose="reset_password")
    return PasswordResetLink(
        token=token,
        email=user.email,
        name=user.name,
        language=user.preferred_language,
    )


async def reset_password(db: AsyncSession, *, token: str, new_password: str) -> User:
    """Redeem a reset link, set the new password and sign every device out.

    Order matters twice over. The new password is hashed **before** the token is
    consumed, so a password the policy rejects does not burn a one-time link the
    user would have to request all over again. And every session is revoked
    **after** the password changes, because a reset is the flow someone reaches
    for when they believe their account is compromised — leaving the attacker's
    refresh cookie alive would make the whole exercise decorative.
    """
    password_hash = hash_new_password(new_password)

    token_row = await consume_user_token(db, raw_token=token, purpose="reset_password")
    user = await crud_user.get(db, token_row.user_id)
    if user is None:
        # The row survives its user only in the window between a cascade delete
        # and this read; treat it as any other dead link.
        raise_problem(
            400,
            code="auth.invalid_token",
            detail="This link is not valid. Please request a new one.",
        )

    user.password_hash = password_hash
    db.add(user)
    await db.flush()

    # Every *other* reset link now in an inbox is a spare key to an account
    # whose owner has just told us they are worried about it — including the one
    # an attacker may have requested. They go too.
    _ = await crud_user_token.consume_outstanding(
        db, user_id=user.id, purpose="reset_password"
    )
    _ = await revoke_all_sessions(db, user_id=user.id)
    return user


async def change_password(
    db: AsyncSession,
    *,
    user: User,
    data: ChangePasswordRequest,
    current_session_id: uuid.UUID | None,
) -> int:
    """Change a signed-in user's password, signing their other devices out.

    The current password is required even though the caller is authenticated:
    it is the only thing standing between a borrowed unlocked laptop and a
    permanent account takeover.

    The caller's own session is spared. Being signed out of the tab you just
    used is confusing rather than reassuring, and the point of the sweep is the
    *other* devices — the shared machine, the old phone, the session someone
    else may be holding. When the session cannot be identified (the E2E header
    bypass authenticates without a bearer token, so there is no ``jti`` to
    spare) everything is revoked, which is the safe direction to fail in.

    Returns how many sessions were closed.
    """
    if not user.password_hash:
        raise_problem(
            400,
            code="auth.no_password_set",
            detail=(
                "This account does not have a password yet. "
                "Use the password-reset link to set one."
            ),
        )
    if not verify_password(data.current_password, user.password_hash):
        raise_problem(
            401,
            code="auth.invalid_credentials",
            detail="Your current password is not correct.",
        )

    user.password_hash = hash_new_password(data.new_password)
    db.add(user)
    await db.flush()

    return await revoke_all_sessions(
        db, user_id=user.id, except_session_id=current_session_id
    )


# ── Email verification ────────────────────────────────────────────


async def verify_email(db: AsyncSession, *, token: str) -> User:
    """Redeem a verification link and mark the address confirmed."""
    token_row = await consume_user_token(db, raw_token=token, purpose="verify_email")
    user = await crud_user.get(db, token_row.user_id)
    if user is None:
        raise_problem(
            400,
            code="auth.invalid_token",
            detail="This link is not valid. Please request a new one.",
        )

    if not user.email_verified:
        user.email_verified = True
        db.add(user)
        await db.flush()
    return user


async def issue_verification(db: AsyncSession, *, user: User) -> str | None:
    """Mint a fresh verification token, or ``None`` when there is nothing to do.

    Returning ``None`` for an already-verified address (or one that is not set
    at all) keeps the route's answer a flat 202 in every case, so a request that
    changes nothing is not distinguishable from one that sends a mail.
    """
    if user.email_verified or not user.email:
        return None
    return await issue_user_token(db, user_id=user.id, purpose="verify_email")


# ── Session management ────────────────────────────────────────────


async def list_sessions(db: AsyncSession, *, user: User) -> Sequence[AuthSession]:
    """The devices currently signed in as this user, newest sign-in first."""
    return await crud_auth_session.list_active_for_user(db, user_id=user.id)


async def revoke_session(
    db: AsyncSession, *, user: User, session_id: uuid.UUID
) -> None:
    """Sign one device out, by id.

    A session belonging to somebody else answers 404 rather than 403 — the same
    choice ``logic.permissions.require_event_visible`` makes, and for the same
    reason: a 403 would confirm that the id names a real session, which is one
    bit more than a stranger should get from a guess.
    """
    session_row = await crud_auth_session.get(db, session_id)
    if session_row is None or session_row.user_id != user.id:
        raise_problem(
            404,
            code="auth.session_not_found",
            detail="That session no longer exists.",
        )
    _ = await crud_auth_session.revoke(db, db_obj=session_row)
