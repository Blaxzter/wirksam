# Authentication

WirkSam authenticates people itself, against its own database. There is no
identity provider, no JWKS endpoint and no third party that can lock everybody
out by having an outage.

This document covers the token model, the refresh cookie, rotation and reuse
detection, the two email-borne flows, and the settings that tune all of it. For
*authorisation* — who may do what inside an event — see the Auth Pattern section
of `CLAUDE.md`; nothing here touches it. Authentication decides *who is calling*,
`app/logic/permissions.py` decides *what they may do*, and those two questions
have stayed independent on purpose.

## The two tokens

Sessions are split across two credentials with deliberately opposite properties.

| | Access token | Refresh token |
|---|---|---|
| Format | HS256 JWT | opaque, `secrets.token_urlsafe(32)` |
| Lifetime | 15 minutes | 30 days, sliding |
| Where the client keeps it | memory only | httpOnly cookie |
| Where the server keeps it | nowhere | `auth_sessions.refresh_token_hash` (sha256) |
| Revocable | no | yes |
| Sent with | `Authorization: Bearer …` on every API call | the cookie, on `/api/v1/auth/*` only |

The access token is stateless, so every request validates locally with no
database round-trip — and it therefore cannot be withdrawn. Fifteen minutes is
the entire mitigation for a stolen one. Everything long-lived is the refresh
token, which is a row: revoking a session is an `UPDATE`, and a signed-out
device stops working immediately rather than when its JWT happens to lapse.

Claims are minimal (`app/core/security.py`):

- `sub` — the `users.id` UUID. It is the primary key, so resolving a request to
  a `User` is one lookup with no second identity path to keep in sync.
- `jti` — the `auth_sessions.id` the token was minted for, which is what ties a
  stateless token back to a revocable session.
- `typ` — always `"access"`. A JWT with any other type is refused.
- `iat` / `exp`.

There is deliberately **no `aud` claim**: setting one obliges every `jwt.decode`
call in the codebase to pass a matching `audience=` argument or raise, for no
benefit in a system with one issuer and one audience. Nothing role-shaped is
embedded either, so a permission change takes effect on the next request rather
than whenever the token expires.

## The refresh cookie

Set by `/auth/register`, `/auth/login` and `/auth/refresh`; cleared by
`/auth/logout`. Attributes come from settings and are listed in
`app/api/routes/auth.py::_set_refresh_cookie`:

- `httponly=True` — JavaScript can never read it, which is what makes it safe to
  keep across a page reload when the access token cannot be.
- `path=/api/v1/auth` — it is attached to the auth endpoints and nothing else. A
  request that cannot spend the refresh token should not be carrying it.
- `secure` from `REFRESH_COOKIE_SECURE`, `samesite` from
  `REFRESH_COOKIE_SAMESITE`.
- **No `Domain` attribute**, ever. Omitting it yields a host-only cookie. The
  apex this API is deployed under hosts unrelated applications, and a `Domain`
  cookie would be sent to every one of them.

Two failure modes here are invisible from the server and worth naming:

- `SameSite=None` without `Secure` is rejected outright by browsers. `config.py`
  refuses to start on that combination rather than let it become "the session
  silently ends at the first refresh".
- A `Set-Cookie` that clears the cookie must match every attribute used to set
  it — path included, absence of a domain included. A mismatch creates a
  *second*, empty cookie and leaves the original alive, which reads as "logout
  does nothing".

## Rotation and reuse detection

Every successful `/auth/refresh` **revokes the presented session and creates a
new row**, rather than swapping the hash in place. That costs one row per
refresh and buys the property the whole design exists for: after rotation the
old digest still matches something, and what it matches is a dead session.

`app/logic/auth/tokens.py::rotate_refresh_session` has four outcomes:

1. **No such token** → 401 `auth.invalid_token`. The value never existed here,
   or its row was cascaded away with a deleted account.
2. **Already revoked** → treated as theft. Either the token was rotated away (so
   someone kept a copy of a secret they should have discarded) or the session
   was ended deliberately and someone kept the cookie. Both mean the account may
   be in two pairs of hands, so **every** session that account owns is revoked
   and everyone signs in again. 401 `auth.session_revoked`, logged at WARNING
   with the user id and no token material.
3. **Expired** → 401 `auth.token_expired`, and the row is closed on the way out
   so a later replay lands in the theft branch rather than the expiry branch.
4. **Live** → revoke, mint, hand back. The successor inherits the original
   `created_at` so the Security settings list keeps showing when the device
   actually signed in.

The expiry window slides: each rotation gets the full 30 days again, so a weekly
user stays signed in indefinitely while an abandoned session dies thirty days
after it was last touched.

The known false positive is two tabs refreshing in the same instant, where the
second still holds the token the first just spent — that signs the account out
everywhere. The frontend dedupes concurrent refreshes behind a single promise
precisely so this stays theoretical. Do not "fix" it with a grace window in
which a spent token still works; that is exactly the hole rotation closes.

Rotation must be durable before the client is told its new token works, and it
is: `deps.get_db` commits *before* the response is sent, so a client that
immediately reuses its new cookie cannot outrun its own rotation.

## Email-borne tokens

Verification and password-reset links carry opaque tokens stored in
`user_tokens` — hashed, single-use, and purpose-bound, so a verification link
that escapes an inbox cannot be replayed as a password reset.

| Purpose | Lifetime | Setting |
|---|---|---|
| `verify_email` | 48 hours | `EMAIL_VERIFY_TOKEN_EXPIRE_HOURS` |
| `reset_password` | 1 hour | `EMAIL_RESET_TOKEN_EXPIRE_HOURS` |

The lifetimes differ by more than an order of magnitude on purpose. A reset link
is a live password sitting in an inbox. A verification link grants nothing on
its own — **sign-in is not blocked on an unverified address**; verification is a
soft nudge in the UI — and is routinely opened the next day on a phone.

Flow notes:

- `POST /auth/forgot-password` answers **202 in every case** and says nothing
  about whether the address exists. The mail is scheduled as a background task
  so the response latency cannot leak the answer either. For a
  volunteer-scheduling app, "does this person have an account here?" is a real
  disclosure.
- `POST /auth/reset-password` revokes **all** of that account's sessions.
  Someone reaching for a reset is usually telling us they think the account is
  in somebody else's hands; leaving that somebody's cookie alive would make the
  reset decorative.
- `POST /auth/change-password` revokes every session **except the caller's own**
  — being signed out of the tab you just used reads as a bug.
- `POST /auth/verify-email` is unauthenticated on purpose: the link is routinely
  opened in a different browser from the one that registered.

### Mail delivery

`app/logic/auth/emails.py` talks to SMTP directly and **bypasses
`NotificationService` entirely**. That service needs a seeded `NotificationType`
row, writes an in-app notification alongside the mail, applies the recipient's
per-channel preferences — so someone who turned email notifications off would
never receive a password reset — and BCC-batches recipients from the first one's
body. All three are wrong for a message carrying a one-time token.

Delivery is gated on `settings.emails_configured` alone, **not** on
`emails_enabled` (which is `ENVIRONMENT != "local"`): local development and the
e2e stack both run `ENVIRONMENT=local` against the mailcatcher container on port
1025, and honouring `emails_enabled` would mean nobody could ever finish a
registration outside production. When SMTP is not configured at all, the link is
written to the log at WARNING so a local flow can still be completed, and the
function returns `False`. It never raises — a mail failure must not surface as
an HTTP error.

## Endpoints

All under `/api/v1/auth` (`app/api/routes/auth.py`). Function names are API:
`custom_generate_unique_id` turns `{tag}-{function_name}` into the operation id,
which becomes the generated client's method name — `login` under `tags=["auth"]`
is `authLogin()`. Renaming a function here renames a method in the frontend.

| Method | Path | Auth | Result |
|---|---|---|---|
| POST | `/auth/register` | — | 201 `TokenResponse`, sets cookie, schedules verify mail |
| POST | `/auth/login` | — | 200 `TokenResponse`, sets cookie |
| POST | `/auth/refresh` | cookie | 200 `RefreshResponse`, rotates cookie |
| POST | `/auth/logout` | cookie | 204, revokes session, clears cookie |
| POST | `/auth/forgot-password` | — | 202 always |
| POST | `/auth/reset-password` | — | 204, revokes **all** sessions |
| POST | `/auth/verify-email` | — | 204 |
| POST | `/auth/resend-verification` | `CurrentUser` | 202 always |
| POST | `/auth/change-password` | `CurrentUser` | 204, revokes all *other* sessions |
| POST | `/auth/sandbox` | — | 201 `SandboxSessionResponse`, sets cookie, seeds a demo |
| DELETE | `/auth/sandbox` | `CurrentUser` | 204, purges the demo, clears cookie |
| GET | `/auth/sessions` | `CurrentUser` | `list[AuthSessionRead]` |
| DELETE | `/auth/sessions/{id}` | `CurrentUser` | 204 |

The router keeps its own `/auth` prefix rather than living under `/users`,
because `GET /users/{user_id}` is a catch-all: a literal `/users/login`
registered after it would be shadowed silently.

Failures are RFC 7807 problems (`raise_problem`) carrying an `auth.*` code the
frontend translates through its `errorCodes` i18n namespace: `auth.invalid_credentials`,
`auth.email_taken`, `auth.invalid_token`, `auth.token_expired`, `auth.rate_limited`,
`auth.weak_password`, `auth.no_password_set`, `auth.session_revoked`,
`auth.session_not_found` — plus, from the two demo endpoints,
`sandbox.disabled`, `sandbox.capacity_reached`, `sandbox.forbidden` and
`sandbox.not_available`. A code with
no i18n entry renders as the raw string on screen, and a bare `HTTPException`
carries no code at all.

## Data model

- **`users.subject`** — this application's own opaque identity string. It was
  renamed in place from the identity-provider column it replaced; the
  `20260823_0001` migration has the details. The prefixes are behavioural, not
  cosmetic: `demo|` accounts are
  the ones every notification channel refuses to send mail to, `sandbox|`
  accounts are the throwaway guests behind the "try a test event" button and are
  refused the same way (see [`SANDBOX.md`](SANDBOX.md)), `test|` accounts
  are the ones `POST /testing/reset` is allowed to delete, and password accounts
  get `local|<uuid4hex>`.
- **`users.password_hash`** — bcrypt, nullable. Null means the account has no
  password (demo, test, or provisioned before local auth existed).
- **`users.email`** — unique case-insensitively via a partial index on
  `lower(email) WHERE email IS NOT NULL`. The column stays nullable because
  legacy rows have no address; registration requires one.
- **`auth_sessions`** — one row per signed-in device. `refresh_token_hash`
  (sha256 hex, unique), `expires_at`, `revoked_at`, `last_used_at`, plus
  `user_agent` / `ip_address` as display labels for the Security settings card.
  Those two are self-reported and are **never** an authentication signal.
- **`user_tokens`** — one row per outstanding verification or reset link:
  `purpose`, `token_hash`, `expires_at`, `consumed_at`.

Both new tables use `ondelete="CASCADE"` on their user FK — `SET NULL` on a user
FK is forbidden in this schema (see `backend/app/models/CLAUDE.md`), and cascade
also means deleting an account destroys every credential that could reach it in
the same statement.

All stored datetimes are **naive UTC**: `datetime.now(timezone.utc).replace(tzinfo=None)`.
Comparing a naive `expires_at` against an aware `now()` raises `TypeError` — and
it would do so in the refresh path, on a live session, rather than anywhere a
test would notice.

## Rate limiting

`app/core/rate_limit.py` is a small in-process fixed-window counter — there is
no Redis in this stack. **Limits are therefore per worker process**, and the
image runs `fastapi run --workers 4`, so the effective ceiling is roughly four
times each number below. That is an accepted approximation: these limits exist
to make online guessing and inbox flooding pointless, not to be exact.

| Bucket | Limit | Key |
|---|---|---|
| `login` | 10 / 5 min | `<ip>\|<email>` |
| `register` | 5 / hour | `<ip>` |
| `forgot_password` | 5 / hour | `<ip>\|<email>` |
| `reset_password` | 10 / hour | `<ip>` |
| `resend_verification` | 3 / hour | `<user id>` |

Login is keyed on IP *and* address together on purpose: keying on the IP alone
would let one household's shared connection lock out everybody behind it, and
keying on the address alone would let anyone lock a known user out of their own
account by failing ten logins on their behalf.

The whole limiter is a **no-op under `settings.TESTING`**. Six parallel
Playwright workers would otherwise trip any sane per-IP limit, and it would read
as flakiness rather than as a limit doing its job.

`client_ip()` prefers the leftmost `X-Forwarded-For` entry because in production
the API sits behind Traefik and `request.client.host` is the proxy's address for
every caller. That header is client-supplied and spoofable — build nothing but
rate-limit keys on it.

## Bot protection on registration

Rate limiting caps how *fast* accounts can be created; it cannot tell a person
from a script. A bot that registers five accounts an hour and then waits is
inside every ceiling above. So `POST /auth/register` — the only endpoint that
turns an anonymous caller into a row in `users` and a message to an arbitrary
address — sits behind a [Cloudflare Turnstile](https://developers.cloudflare.com/turnstile/)
challenge as well.

The browser solves the challenge, the form posts the resulting token as
`turnstile_token`, and `app/core/turnstile.py` asks Cloudflare's `siteverify`
whether that token is one it issued. A refusal is **403 `auth.captcha_failed`**,
raised before anything is written — no user row, no verification mail.

Four properties are deliberate:

- **Enforcement is opt-in, gated on `TURNSTILE_SECRET_KEY` alone.** Unset means
  no check at all, which is what local development, the test suite and the E2E
  stack run with — no Cloudflare account required to work on this repository.
  It is *not* gated on `ENVIRONMENT`, so a staging deployment that configures
  the key exercises the real path.
- **It fails closed.** A missing token, a rejected token, a malformed reply and
  an unreachable `siteverify` all count as "not human". Treating an outage as
  "must be human" would turn a Cloudflare incident into an open door, and would
  let an attacker who can *cause* that outage choose when it opens.
- **`remoteip` is not sent.** Cloudflare requires it to match the address that
  solved the challenge, and a dual-stack client routinely solves over IPv6 and
  posts over IPv4 — which would reject a real person. The token is already
  bound to the client that solved it.
- **The token is single-use.** Cloudflare answers `timeout-or-duplicate` the
  second time it sees one, so `RegisterView.vue` resets its widget after *any*
  failed submission. Without that, the retry after a "this address is taken"
  error would be refused for a reason unrelated to what the person just fixed.

The site key is public and reaches the browser as runtime config
(`window.__APP_CONFIG__.TURNSTILE_SITE_KEY`, written by
`frontend/docker-entrypoint.sh` from `TURNSTILE_SITE_KEY`); an empty value means
the widget never renders. Both halves come from one widget in the Cloudflare
dashboard — it is free, and needs no DNS change, so the domain does not have to
be on Cloudflare.

To exercise the real path locally, use Cloudflare's
[test keys](https://developers.cloudflare.com/turnstile/troubleshooting/testing/).
They must be set as a pair — a dummy secret rejects real tokens and a real
secret rejects dummy ones:

| Behaviour | Site key | Secret key |
|---|---|---|
| always passes | `1x00000000000000000000AA` | `1x0000000000000000000000000000000AA` |
| always fails | `2x00000000000000000000AB` | `2x0000000000000000000000000000000AA` |

## Settings

All in `backend/app/core/config.py`; every one has a default, so `.env.example`
is enough to boot.

| Setting | Default | Notes |
|---|---|---|
| `SECRET_KEY` | `"changethis"` | Signs the access tokens. **Must** be changed outside local — `_enforce_non_default_secrets` warns locally and refuses to boot anywhere else. Give it at least 32 bytes; below that PyJWT warns on every encode. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Sliding, reset on each rotation. |
| `PASSWORD_MIN_LENGTH` | `8` | Upper bound is bcrypt's 72 **bytes** — not characters; a German umlaut costs two. |
| `REFRESH_COOKIE_NAME` | `wirksam_refresh` | |
| `REFRESH_COOKIE_SAMESITE` | `lax` | |
| `REFRESH_COOKIE_SECURE` | `None` | `None` derives from `ENVIRONMENT != "local"`; an explicit value in the env file wins. |
| `EMAIL_RESET_TOKEN_EXPIRE_HOURS` | `1` | |
| `EMAIL_VERIFY_TOKEN_EXPIRE_HOURS` | `48` | |
| `SUPERADMIN_EMAILS` | `[]` | See below. |
| `TURNSTILE_SECRET_KEY` | `None` | Unset disables the registration bot check entirely. See above. |
| `REGISTRATION_MODE` | `"open"` | `open`, `approval` or `invite`. See "Who may register" below. |
| `REGISTRATION_ALLOWED_DOMAINS` | `[]` | Email domains signup is limited to, comma-separated. Empty means any. |
| `REGISTRATION_INVITE_BYPASS` | `True` | A valid invitation skips the approval queue and the domain list. |

`SECRET_KEY` deliberately does **not** default to a freshly minted random value.
The image runs four workers, so a per-process random default would hand them
four different signing keys and roughly three requests in four would fail
verification — intermittently, in production only.

Rotating `SECRET_KEY` invalidates every outstanding access token (at most 15
minutes of disruption); refresh cookies survive it, because they are opaque and
validated against the database rather than a signature.

## Who may register

Open signup is the default, and it is what the hosted instance runs: an account
grants nothing until an event admits it, so there is nothing to approve. A
self-hosted deployment can put a door on it with three settings. Every rule
lives in `app/logic/auth/registration.py`, which `register_user` calls before
it writes a row.

| Mode | Who can sign up | What the new account is |
|---|---|---|
| `open` | anyone | approved |
| `approval` | anyone | `pending` until a superadmin approves it |
| `invite` | only someone holding a usable invitation | approved |

"Holding an invitation" means either the link the visitor arrived through
(`invitation_token` on `POST /auth/register`; the invite page hands it to the
form) or an open invitation addressed to their email. A revoked, used or
expired invitation does not count, nor does one for a different address, nor
one to a demo event, since anyone can start a demo.

`REGISTRATION_ALLOWED_DOMAINS` applies on top of any mode and refuses addresses
outside the list with `auth.email_domain_not_allowed`. With
`REGISTRATION_INVITE_BYPASS` on (the default), an invited address skips both
the domain list and the approval queue: an event admin who invited someone by
name has already made the decision the queue exists for.

Two exemptions keep a deployment from locking itself out: an address in
`SUPERADMIN_EMAILS` always gets in, approved, and `sync_superadmin_role`
approves a listed account on sign-in if it was waiting.

**The queue.** Approval is tracked in `users.approval_status` (`approved`,
`pending`, `rejected`), separate from `is_active`, which stays the moderation
switch. A pending or rejected account can sign in and read or delete its own
profile (`AnyUser`); every `CurrentUser` route refuses it with
`auth.account_pending` or `auth.account_rejected`, and the router guard shows
the waiting screen. Superadmins are notified of each new signup
(`user.registered`) and decide with `POST /users/{id}/approve` or
`POST /users/{id}/reject`, which notify the person (`user.approved`,
`user.rejected`). Those three notification types are only listed in the
preference screens while the mode is `approval`.

`GET /auth/registration-policy` is public and returns the three settings, so
the registration form can say "by invitation only" or "an administrator
approves new accounts" before anyone types.

## Bootstrapping the first administrator

`app/logic/auth/service.py::sync_superadmin_role` is the **only** mechanism that
grants the platform `admin` role. It runs on both registration and sign-in — on
sign-in too because of bootstrapping order: an operator typically adds their
address to `SUPERADMIN_EMAILS` *after* discovering they cannot reach the admin
screens, by which time their account already exists.

Matching is case-insensitive. Activation rides along, so a listed address is
reactivated if it was suspended — locking the only administrator out of their own
installation has no recovery path through the UI. Removal is deliberately not
mirrored: taking an address off the list does not strip the role, because roles
are also granted by hand in the admin screens and a startup reconciliation would
silently undo those.

Delete this function and a fresh deployment has no way to reach the admin screens
at all.

## The E2E bypass

`X-Test-User-Email` (`app/api/deps.py`) resolves a request to a user by email,
with no token at all. It is reachable **only** while `settings.TESTING` is true,
and `config.py` refuses to construct settings with `TESTING` on in production.

It survived the move to local auth because in CI the Playwright browser origin
and `VITE_API_URL=http://backend:8787` are genuinely cross-site: a `SameSite=Lax`
refresh cookie is silently dropped, and `SameSite=None` requires `Secure`
requires HTTPS. Real-login E2E would pass locally and fail in CI. Replacing the
bypass with real logins is a separate change, not a leftover to tidy away.

A second header, `X-Test-Registration-Policy`, carries a JSON registration
policy (`{"mode": "approval", "allowed_domains": [], "invite_bypass": true}`)
that replaces the configured one for that request
(`app/logic/auth/registration.py::policy_for_request`). It exists because the
E2E backend runs four worker processes: a test cannot switch
`REGISTRATION_MODE` at runtime, since only the process that served the call
would see it. The header keeps the override per request, so specs for different
modes run in parallel. Like the user bypass, it is ignored unless `TESTING` is
on; a malformed one is a 400 so a spec cannot pass against the wrong mode.
