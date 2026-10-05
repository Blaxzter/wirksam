"""Everything that hands out, renews or takes away a credential.

A thin adapter over ``app.logic.auth.service``: this module owns the HTTP
shape — status codes, the refresh cookie, rate-limit keys and which mails get
scheduled — and nothing else. The flows themselves live in the logic layer so
they can be tested without a client.

Three things about this file are easy to get wrong and expensive to notice
late:

* **The refresh cookie is read from the request, not declared as a parameter.**
  It is httpOnly, so the browser attaches it automatically and no client code
  could ever supply it. Declaring it with ``Cookie(...)`` would put a parameter
  in the OpenAPI document, and the generated TypeScript client would grow an
  argument that is impossible to fill.
* **Function names are API.** ``custom_generate_unique_id`` turns
  ``{tag}-{function_name}`` into the operation id, which becomes the generated
  client's method name — ``login`` under ``tags=["auth"]`` is ``authLogin()``.
  Renaming a function here renames a method in the frontend.
* **Every failure carries an ``auth.*`` code.** The frontend translates those
  codes through its ``errorCodes`` i18n namespace; a code with no entry renders
  as the raw string on screen, and a bare ``HTTPException`` carries no code at
  all.
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Request, Response, status

from app.api.deps import CurrentUser, DBDep
from app.core.config import settings
from app.core.errors import raise_problem
from app.core.logger import get_logger
from app.core.rate_limit import (
    client_ip,
    forgot_password_limiter,
    login_limiter,
    register_limiter,
    resend_verification_limiter,
    reset_password_limiter,
    sandbox_limiter,
)
from app.core.security import AuthTokenError, decode_access_token
from app.core.turnstile import verify_turnstile
from app.logic.auth import service
from app.logic.auth.emails import send_password_reset_email, send_verify_email
from app.logic.auth.registration import policy_for_request
from app.logic.notifications.triggers import dispatch_user_registered
from app.logic.sandbox import service as sandbox_service
from app.models.auth_session import AuthSession
from app.schemas.auth import (
    AuthSessionRead,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshResponse,
    RegisterRequest,
    RegistrationPolicy,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.schemas.sandbox import SandboxCreate, SandboxSessionResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# The cookie is scoped to this application's own auth endpoints, so it is not
# attached to any other API call — a request that cannot use the refresh token
# should not be carrying it.
REFRESH_COOKIE_PATH = f"{settings.API_V1_STR}/auth"


# ── Cookie and request plumbing ───────────────────────────────────


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Attach the rotating refresh token to the response.

    Deliberately **no** ``domain`` argument. Omitting it yields a host-only
    cookie, sent to the API host and nowhere else; setting it to the shared
    apex would broadcast a live session credential to every unrelated
    application hosted on that domain.

    ``max_age`` mirrors the row's ``expires_at`` so the browser drops a cookie
    the server would refuse anyway — but the server-side expiry is the one that
    decides, since the client's copy is trivially editable.
    """
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=bool(settings.REFRESH_COOKIE_SECURE),
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Remove the refresh cookie.

    Every attribute has to match the one used to set it — path included, and
    the absence of a domain included. A ``Set-Cookie`` that differs in scope
    creates a *second*, empty cookie and leaves the original in place, which
    reads as "logout does nothing" and is very hard to see from the server.
    """
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=bool(settings.REFRESH_COOKIE_SECURE),
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )


def _refresh_token_from(request: Request) -> str | None:
    """Read the refresh cookie the browser attached, if it attached one."""
    return request.cookies.get(settings.REFRESH_COOKIE_NAME)


def _client_labels(request: Request) -> tuple[str | None, str | None]:
    """The (user agent, IP) pair shown against a device in Security settings.

    Both are self-reported and are stored as labels only — never as an
    authentication signal. Over-long values are truncated by the schema rather
    than rejected, because a strange ``User-Agent`` must not be able to fail
    the login it arrived with.
    """
    return request.headers.get("user-agent"), client_ip(request)


def _requesting_session_id(request: Request) -> uuid.UUID | None:
    """Which ``auth_sessions`` row this request's access token belongs to.

    Used to label "this device" in the session list and to spare the caller's
    own session when a password change signs the others out. Both are cosmetic
    or fail-safe, which is why this returns ``None`` instead of raising: the
    routes that call it are already behind ``CurrentUser``, so the token has
    been validated by the time we get here, and under the E2E header bypass
    there is no bearer token to read at all.

    The decode is repeated rather than taken from ``deps.AccessClaimsDep``
    precisely because of that bypass — as a dependency it would turn the
    Security settings screen into a 401 for the entire Playwright suite.
    """
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        return decode_access_token(token).session_id
    except AuthTokenError:
        return None


def _to_session_read(
    session_row: AuthSession, current_session_id: uuid.UUID | None
) -> AuthSessionRead:
    """Serialise one session, flagging the one making this request."""
    item = AuthSessionRead.model_validate(session_row)
    item.is_current = session_row.id == current_session_id
    return item


# ── Registration and sign-in ──────────────────────────────────────


@router.get("/registration-policy", response_model=RegistrationPolicy)
async def get_registration_policy(request: Request) -> RegistrationPolicy:
    """Who may sign up on this deployment, for the registration form to render.

    Public: the visitor asking has no account yet. The form uses it to say
    "by invitation only" instead of offering fields the server would refuse,
    and to warn about the approval queue and the domain list up front.
    """
    return policy_for_request(request)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    session: DBDep,
) -> TokenResponse:
    """Create an account and sign it straight in.

    ``REGISTRATION_MODE`` decides whether the signup is allowed and whether the
    account works at once (see ``app.logic.auth.registration``). Either way the
    caller is signed in: a pending account needs a session to be told it is
    waiting, and the superadmins are alerted that someone is.

    The verification mail is scheduled rather than awaited. It carries a live
    token, so it must not be sent from inside the transaction that creates the
    account: background tasks run after ``get_db`` has committed, which is
    exactly the ordering a token-bearing mail needs.
    """
    await register_limiter.check(client_ip(request))

    # Both gates, in the order that costs least. The rate limit is a dict
    # lookup and rejects the flood; Turnstile is a network round trip to
    # Cloudflare and rejects the script that stayed under the limit. Neither
    # replaces the other, and this one runs before a single row is written.
    if settings.turnstile_enabled and not await verify_turnstile(body.turnstile_token):
        raise_problem(status.HTTP_403_FORBIDDEN, code="auth.captcha_failed")

    user_agent, ip_address = _client_labels(request)
    registered = await service.register_user(
        session,
        data=body,
        user_agent=user_agent,
        ip_address=ip_address,
        policy=policy_for_request(request),
    )

    background_tasks.add_task(
        send_verify_email,
        email=str(body.email),
        name=body.name,
        token=registered.verification_token,
        language=body.preferred_language,
    )
    new_user = registered.session.user
    if new_user.approval_status == "pending":
        background_tasks.add_task(
            dispatch_user_registered,
            user_id=new_user.id,
            user_name=new_user.name,
            user_email=new_user.email,
        )

    _set_refresh_cookie(response, registered.session.refresh_token)
    return TokenResponse(
        access_token=registered.session.access_token,
        expires_in=registered.session.expires_in,
        user=await service.build_user_profile(session, registered.session.user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: DBDep,
) -> TokenResponse:
    """Exchange an email address and password for a session.

    Rate-limited per IP *and* address together: keying on the IP alone would
    let one household's shared connection lock out everybody behind it, and
    keying on the address alone would let anyone lock a known user out of their
    own account by failing ten logins on their behalf.
    """
    await login_limiter.check(f"{client_ip(request)}|{str(body.email).lower()}")

    user_agent, ip_address = _client_labels(request)
    signed_in = await service.authenticate(
        session, data=body, user_agent=user_agent, ip_address=ip_address
    )

    _set_refresh_cookie(response, signed_in.refresh_token)
    return TokenResponse(
        access_token=signed_in.access_token,
        expires_in=signed_in.expires_in,
        user=await service.build_user_profile(session, signed_in.user),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    request: Request,
    response: Response,
    session: DBDep,
) -> RefreshResponse:
    """Rotate the refresh cookie and mint a new access token.

    Takes no body and no bearer token: the credential is the httpOnly cookie,
    which is the point — it survives a page reload that wipes the in-memory
    access token, and JavaScript can never read it.

    Rotation is a write, and it must be durable before the client is told the
    new token works. It is: ``DBDep``'s transaction commits *before* the
    response is sent (see ``deps.get_db``), so a client that immediately reuses
    its new cookie cannot outrun its own rotation.
    """
    refreshed = await service.refresh_session(
        session, refresh_token=_refresh_token_from(request)
    )

    _set_refresh_cookie(response, refreshed.refresh_token)
    return RefreshResponse(
        access_token=refreshed.access_token,
        expires_in=refreshed.expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: DBDep,
) -> None:
    """End this device's session and clear the cookie.

    Never fails. A missing or unknown cookie means the session is already gone,
    which is the state the caller asked for; answering 401 would leave a dead
    cookie in a browser that was trying to clean up after itself.
    """
    _ = await service.sign_out(session, refresh_token=_refresh_token_from(request))
    _clear_refresh_cookie(response)


# ── The demo session ──────────────────────────────────────────────
#
# These two live in this file, and must keep living in it, for one unglamorous
# reason: the refresh cookie is scoped to REFRESH_COOKIE_PATH, which is this
# router's prefix. A sandbox endpoint mounted under any other prefix would set
# a cookie the browser never sends back to /auth/refresh, and the demo would
# die silently at the first fifteen-minute token renewal — long after the
# visitor stopped watching, and with no error anywhere to explain it.


@router.post("/sandbox", response_model=SandboxSessionResponse, status_code=201)
async def sandbox(
    body: SandboxCreate,
    request: Request,
    response: Response,
    session: DBDep,
) -> SandboxSessionResponse:
    """Hand an anonymous visitor a throwaway account and an event to play in.

    This is the only endpoint in the application that writes on behalf of a
    caller who has not identified themselves, so it is fenced in three ways:
    a deployment-level switch, a per-IP rate limit, and a hard ceiling counted
    against live rows. See ``logic.sandbox.service`` for why all three, and why
    the rate limiter is the weakest of them.

    What comes back is an ordinary sign-in response. The demo is not a special
    rendering mode — it is a real session belonging to an account that will be
    deleted within the hour, which is what lets every screen in the app work
    against it unmodified.
    """
    await sandbox_limiter.check(client_ip(request))

    user_agent, ip_address = _client_labels(request)
    signed_in, event = await sandbox_service.create_sandbox(
        session,
        role=body.role,
        language=body.language,
        user_agent=user_agent,
        ip_address=ip_address,
    )
    _set_refresh_cookie(response, signed_in.refresh_token)

    assert event.sandbox_expires_at is not None  # set by create_sandbox
    return SandboxSessionResponse(
        access_token=signed_in.access_token,
        expires_in=signed_in.expires_in,
        user=await service.build_user_profile(session, signed_in.user),
        event_id=event.id,
        role=body.role,
        expires_at=event.sandbox_expires_at,
    )


@router.delete("/sandbox", status_code=status.HTTP_204_NO_CONTENT)
async def exit_sandbox(
    current_user: CurrentUser,
    response: Response,
    session: DBDep,
) -> None:
    """End the demo now and delete everything it created.

    The TTL sweep would get there eventually; this is for the visitor who is
    done and would rather not leave their fake bookings lying around. Refuses a
    real account with 403 — this deletes an event and its members, and must
    never be reachable for one that matters.
    """
    await sandbox_service.end_sandbox(session, user=current_user)
    _clear_refresh_cookie(response)


# ── Password reset ────────────────────────────────────────────────


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: DBDep,
) -> None:
    """Send a reset link, if that address belongs to an account.

    Answers 202 either way, and says nothing about which happened. Anything
    else — a different status, a different body, a noticeably different
    response time — turns this endpoint into a way to ask "does this person
    have an account here?", which for a volunteer-scheduling app is a real
    disclosure about who is involved in what.

    The mail is scheduled as a background task, so the response goes out before
    SMTP is even contacted and its latency cannot leak the answer either.
    """
    email = str(body.email)
    await forgot_password_limiter.check(f"{client_ip(request)}|{email.lower()}")

    link = await service.request_password_reset(session, email=email)
    if link is None:
        return

    background_tasks.add_task(
        send_password_reset_email,
        email=link.email,
        name=link.name,
        token=link.token,
        language=link.language,
    )


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    session: DBDep,
) -> None:
    """Set a new password from a reset link and sign every device out.

    Signing *everything* out is the point of the flow. Someone who reaches for
    a password reset is usually telling us they think their account is in
    somebody else's hands; leaving that somebody's refresh cookie alive would
    make the reset decorative.
    """
    await reset_password_limiter.check(client_ip(request))
    user = await service.reset_password(
        session, token=body.token, new_password=body.password
    )
    logger.info(f"Password reset completed for user {user.id}")


# ── Email verification ────────────────────────────────────────────


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(
    body: VerifyEmailRequest,
    session: DBDep,
) -> None:
    """Confirm an email address from a verification link.

    Unauthenticated on purpose: the link is routinely opened in a different
    browser from the one that registered — a phone, or a mail client's
    in-app view — and requiring a session there would strand people who did
    exactly what the mail told them to.
    """
    _ = await service.verify_email(session, token=body.token)


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    session: DBDep,
) -> None:
    """Send the verification mail again.

    Flat 202 in every case, including the two where nothing is sent (the
    address is already confirmed, or the account has none). There is nothing
    for the caller to do differently and nothing worth a different screen.
    """
    if current_user.is_sandbox:
        raise_problem(
            403,
            code="sandbox.not_available",
            detail="Account settings are not part of the demo",
        )
    await resend_verification_limiter.check(str(current_user.id))

    token = await service.issue_verification(session, user=current_user)
    if token is None or not current_user.email:
        return

    background_tasks.add_task(
        send_verify_email,
        email=current_user.email,
        name=current_user.name,
        token=token,
        language=current_user.preferred_language,
    )


# ── Account security ──────────────────────────────────────────────


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: CurrentUser,
    session: DBDep,
) -> None:
    """Change the signed-in account's password and sign the other devices out.

    The caller's own session survives — being signed out of the tab you just
    used reads as an error, and the devices worth ejecting are the other ones.
    """
    if current_user.is_sandbox:
        # A guest has no password to change, and the generic error for that
        # ("no password set, use the reset link") sends them to a flow that
        # answers 202 and mails nothing, because the account has no address.
        # Refusing here is the only way out of that loop.
        raise_problem(
            403,
            code="sandbox.not_available",
            detail="Account settings are not part of the demo",
        )
    revoked = await service.change_password(
        session,
        user=current_user,
        data=body,
        current_session_id=_requesting_session_id(request),
    )
    logger.info(
        f"Password changed for user {current_user.id}; "
        f"revoked {revoked} other session(s)."
    )


@router.get("/sessions", response_model=list[AuthSessionRead])
async def list_sessions(
    request: Request,
    current_user: CurrentUser,
    session: DBDep,
) -> list[AuthSessionRead]:
    """Every device currently signed in as this account, newest sign-in first.

    One entry is flagged ``is_current`` so the Security settings card can label
    it rather than inviting someone to sign themselves out and wonder why the
    page went blank.
    """
    current_session_id = _requesting_session_id(request)
    rows = await service.list_sessions(session, user=current_user)
    return [_to_session_read(row, current_session_id) for row in rows]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    session: DBDep,
) -> None:
    """Sign one device out.

    Revoking the session making the request is allowed: it is a perfectly
    reasonable way to say "sign out everywhere including here", and the effect
    is simply that the next refresh fails and the client returns to the login
    screen.
    """
    await service.revoke_session(session, user=current_user, session_id=session_id)
