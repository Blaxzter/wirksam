import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
)

from app.core.config import settings
from app.schemas.users import UserProfile

# bcrypt hashes at most 72 *bytes* of input and, since 5.0, raises rather than
# silently truncating. Bytes, not characters: "ä" costs two of them, so a German
# passphrase runs out of room a dozen characters earlier than an English one.
# This is a property of the algorithm rather than a policy knob, which is why it
# is a constant here while the lower bound is a setting.
BCRYPT_MAX_PASSWORD_BYTES = 72

UserTokenPurpose = Literal["verify_email", "reset_password"]
"""What an email-borne token authorises.

A token is only ever accepted by the flow whose purpose matches, so a
verification link that leaks out of an inbox cannot be replayed as a password
reset.
"""


def _validate_password(value: str) -> str:
    """Enforce the password policy once, at the edge.

    Both halves earn their place. The lower bound is the actual policy. The
    upper bound is bcrypt's hard limit, and exceeding it raises a ``ValueError``
    deep inside ``app.core.security.hash_password`` — which surfaces as a 500 —
    unless it is caught out here and returned as an ordinary field error the
    registration form can render next to the input.
    """
    if len(value) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters"
        )
    if len(value.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes long; "
            "accented and non-Latin characters count as more than one"
        )
    return value


Password = Annotated[str, AfterValidator(_validate_password)]
"""A password being *set*.

Never use it for a password being *checked* — see ``LoginRequest.password`` for
why validating a login against the current policy locks people out.
"""


def _clip_to(limit: int) -> Callable[[str | None], str | None]:
    """Build a validator that truncates instead of rejecting.

    ``user_agent`` and ``ip_address`` are labels on a device list, filled in
    from whatever the client sent. A header longer than the column is a cosmetic
    problem; failing the login it arrived with is not, and a ``ValidationError``
    raised while *constructing* an internal schema is a 500 rather than a 422.
    """

    def clip(value: str | None) -> str | None:
        return value if value is None else value[:limit]

    return clip


UserAgentLabel = Annotated[str | None, AfterValidator(_clip_to(255))]
IpAddressLabel = Annotated[str | None, AfterValidator(_clip_to(45))]

# Stripped *before* the length check, so a name of three spaces is rejected as
# empty rather than stored as one — this value ends up on every shift a person
# signs up for, and " " is not a name anyone can be recognised by.
DisplayName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


# ── Requests and responses ────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """Everything an account needs, in one round trip.

    What happens to the account afterwards is the deployment's call, not the
    caller's: ``REGISTRATION_MODE`` decides whether it works immediately, waits
    for a superadmin, or is refused without an invitation. So there is no
    approval field here, only the invitation that can stand in for one.
    """

    email: EmailStr = Field(
        ..., description="Address that becomes the login credential"
    )
    password: Password = Field(
        ..., description="Chosen password, hashed before storage"
    )
    name: DisplayName = Field(
        ..., description="Display name shown to other participants"
    )
    preferred_language: str = Field(
        default="en",
        pattern="^(en|de)$",
        description="Language for the verification mail and later notifications",
    )
    # Optional in the schema, required by the route whenever the deployment has
    # a Turnstile secret configured. Making it mandatory here instead would be
    # the wrong shape twice over: a 422 listing a field no human filled in is
    # not an answer a form can render next to an input, and every deployment
    # without Turnstile — local development included — would have to invent a
    # value to satisfy a check nobody is running.
    turnstile_token: str | None = Field(
        default=None,
        description=(
            "Token from the Cloudflare Turnstile challenge on the registration "
            "form. Required when the deployment has Turnstile configured; "
            "ignored when it does not."
        ),
    )

    invitation_token: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "Token of the event invitation the visitor arrived through. Needed "
            "to sign up on an invitation-only deployment, and lets an invited "
            "address past the approval queue and the domain list where "
            "REGISTRATION_INVITE_BYPASS allows it. Not redeemed here; accepting "
            "the invitation is still its own step."
        ),
    )


class RegistrationPolicy(BaseModel):
    """What the registration form needs to know before anyone fills it in.

    Public, because the visitor reading it has no account yet. Everything in it
    is also discoverable by simply trying to register, so it gives nothing away.
    """

    mode: Literal["open", "approval", "invite"] = Field(
        ...,
        description="open, approval (a superadmin approves) or invite (invitation only)",
    )
    allowed_domains: list[str] = Field(
        default_factory=list,
        description="Email domains self-signup is limited to; empty means any",
    )
    invite_bypass: bool = Field(
        ...,
        description="Whether an invitation skips the approval queue and domain list",
    )


class LoginRequest(BaseModel):
    """Credentials for an existing account."""

    email: EmailStr = Field(..., description="Address the account was registered with")
    # Deliberately a bare ``str`` and not ``Password``. Accounts predate the
    # current policy, and raising PASSWORD_MIN_LENGTH later must not turn their
    # owners' sign-in attempts into a 422 complaining about a password that is
    # in fact the right one. Whether the password is correct is a question for
    # the hash, and a wrong one always answers "auth.invalid_credentials".
    password: str = Field(..., description="Password as typed; never stored or logged")


class RefreshResponse(BaseModel):
    """A fresh access token, minted from the refresh cookie.

    Carries no user object: the client already knows who it is by the time it
    refreshes, and re-serialising the full profile on a call that fires every
    fifteen minutes would be pure overhead.
    """

    access_token: str = Field(..., description="Short-lived HS256 JWT, bearer token")
    token_type: Literal["bearer"] = Field(
        default="bearer", description="Always 'bearer'; present for RFC 6750 clients"
    )
    expires_in: int = Field(
        ..., description="Seconds until the access token stops being accepted"
    )


class TokenResponse(BaseModel):
    """What a successful register or login hands back.

    The refresh token is *not* in here — it goes out as an httpOnly cookie the
    JavaScript can never read. This body holds only what the client is meant to
    keep in memory.

    The profile rides along so the app can render a signed-in shell without a
    second round trip on the one screen where latency is most visible.
    """

    access_token: str = Field(..., description="Short-lived HS256 JWT, bearer token")
    token_type: Literal["bearer"] = Field(
        default="bearer", description="Always 'bearer'; present for RFC 6750 clients"
    )
    expires_in: int = Field(
        ..., description="Seconds until the access token stops being accepted"
    )
    user: UserProfile = Field(..., description="Profile of the account just signed in")


class ForgotPasswordRequest(BaseModel):
    """Ask for a reset link.

    The endpoint answers 202 whether or not the address exists, so this schema
    is also the whole of what an attacker learns from it.
    """

    email: EmailStr = Field(..., description="Address to send the reset link to")


class ResetPasswordRequest(BaseModel):
    """Redeem a reset link and choose a new password."""

    token: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Secret from the reset link; only its sha256 is stored server-side",
    )
    password: Password = Field(..., description="New password")


class VerifyEmailRequest(BaseModel):
    """Redeem a verification link."""

    token: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Secret from the verification link",
    )


class ChangePasswordRequest(BaseModel):
    """Change the password of the signed-in account.

    The current password is required even though the caller is already
    authenticated: it is what stops a borrowed, unlocked browser from becoming a
    permanent takeover.
    """

    current_password: str = Field(..., description="The password in use right now")
    new_password: Password = Field(..., description="Replacement password")


class AuthSessionRead(BaseModel):
    """One signed-in device, as shown in the Security settings card.

    Nothing secret is exposed: the refresh token hash stays server-side, and
    what is left is only enough for the owner to recognise a device they no
    longer want signed in.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime = Field(..., description="When this device signed in")
    last_used_at: datetime | None = Field(
        default=None, description="Last token refresh through this session"
    )
    expires_at: datetime = Field(
        ..., description="When the session lapses without being used"
    )
    user_agent: str | None = Field(
        default=None, description="Browser and platform reported at sign-in"
    )
    ip_address: str | None = Field(
        default=None, description="Client address at sign-in"
    )
    # Not a column — the route fills it in by comparing each row against the
    # ``jti`` of the access token making the request, so the UI can label one
    # entry "this device" instead of inviting someone to sign themselves out
    # and wonder why the page went blank.
    is_current: bool = Field(
        default=False,
        description="True for the session the current request is authenticated by",
    )


# ── Persistence schemas ───────────────────────────────────────────────────
#
# These never appear in the OpenAPI document; they exist to give
# ``CRUDBase[Model, Create, Update]`` its type parameters and to keep row
# construction in one typed place rather than scattered keyword arguments.


class AuthSessionCreate(BaseModel):
    """A newly minted refresh session."""

    user_id: uuid.UUID = Field(..., description="Account this session signs in as")
    refresh_token_hash: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="sha256 hexdigest of the opaque refresh token",
    )
    expires_at: datetime = Field(
        ..., description="When the refresh token stops being accepted (naive UTC)"
    )
    user_agent: UserAgentLabel = Field(
        default=None, description="User-Agent header at sign-in, truncated to fit"
    )
    ip_address: IpAddressLabel = Field(
        default=None, description="Client address at sign-in, truncated to fit"
    )


class AuthSessionUpdate(BaseModel):
    """Partial update of a refresh session.

    Rotation and revocation both have dedicated CRUD methods that stamp the
    right timestamps; prefer those. This exists for ``CRUDBase``'s signature and
    for the rare one-off.
    """

    refresh_token_hash: str | None = Field(
        default=None, description="Replacement sha256 hexdigest after rotation"
    )
    expires_at: datetime | None = Field(
        default=None, description="New expiry (naive UTC)"
    )
    revoked_at: datetime | None = Field(
        default=None, description="When the session was revoked (naive UTC)"
    )
    last_used_at: datetime | None = Field(
        default=None, description="Last successful refresh (naive UTC)"
    )


class UserTokenCreate(BaseModel):
    """A secret about to be mailed to a user."""

    user_id: uuid.UUID = Field(..., description="Account the token acts on")
    purpose: UserTokenPurpose = Field(
        ..., description="Which flow may redeem this token"
    )
    token_hash: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="sha256 hexdigest of the secret carried in the link",
    )
    expires_at: datetime = Field(
        ..., description="When the token stops being accepted (naive UTC)"
    )


class UserTokenUpdate(BaseModel):
    """Partial update of an email-borne token.

    Redemption goes through ``crud.user_token.consume`` so the timestamp is
    stamped consistently; this exists for ``CRUDBase``'s signature.
    """

    consumed_at: datetime | None = Field(
        default=None, description="When the token was redeemed (naive UTC)"
    )
