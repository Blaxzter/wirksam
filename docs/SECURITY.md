# Security Policy

Security is very important for this project. 🔒

Learn more about it below. 👇

## Authentication & Security Architecture

This project authenticates people itself, against its own database. There is no
third-party identity provider. `docs/AUTH.md` is the full description; the
security-relevant properties are:

-   **Split credentials** — a stateless HS256 access token that lives 15 minutes
    and is held in memory by the browser, plus an opaque refresh token that lives
    in an `httpOnly`, host-only, path-scoped cookie. JavaScript can never read
    the long-lived half.
-   **Passwords** — bcrypt with a per-hash salt, verified in constant time.
    Plaintext is never stored or logged.
-   **Tokens at rest are hashed** — refresh tokens and the email-borne
    verification and reset links are stored only as SHA-256 digests, so a leaked
    database dump hands out no live sessions and no live links.
-   **Rotation with reuse detection** — every refresh replaces the token.
    Presenting one that has already been spent is treated as theft and revokes
    every session that account owns.
-   **Revocation** — sessions are rows. Signing a device out, changing a
    password or resetting one takes effect immediately, not when a JWT lapses.
-   **Rate limiting** on login, registration, password reset and verification
    resends, keyed so that no caller can lock another account out.

### How Security Works

1. **Sign-in**: the Vue frontend posts credentials to `POST /api/v1/auth/login`;
   the backend verifies the bcrypt hash and issues the token pair.
2. **API protection**: every protected endpoint resolves the caller through the
   dependency aliases in `backend/app/api/deps.py`, which verify the access
   token's HS256 signature and expiry locally and load the user row by primary
   key.
3. **Session renewal**: `POST /api/v1/auth/refresh` exchanges the cookie for a
   fresh access token and a rotated cookie. Nothing else on the API is sent the
   cookie.
4. **Authorisation**: permissions are **per event**, decided against
   `EventMembership` rows by `backend/app/logic/permissions.py`. The one global
   role is `admin`, the platform superadmin. No permission is carried in a token,
   so a revoked role takes effect on the next request.
5. **Secure communication**: all traffic uses HTTPS in deployed environments, and
   the refresh cookie is marked `Secure` everywhere except local development.

### Shared lists

Shared lists (`docs/SHARED_LISTS.md`) let people sign up for shifts without an
account, through a public link. They carry two secrets of their own, handled
differently from the tokens above on purpose:

-   **List codes are stored in plain text.** A code is twelve random
    characters from a 55-symbol alphabet (about 69 bits), unique across the
    installation. Organisers copy the link again later, which a hash would not
    allow, and the link is public by design. Rotating a list replaces its code,
    and the old link then answers the same 404 as a code that never existed.
    A scan for codes meets a per-IP limit that counts only misses.
-   **Guest manage tokens are never stored.** A token is an HMAC-SHA256 over
    the guest's id and a 128-bit random nonce, under a key derived from
    `SECRET_KEY`, so every mail can rebuild the link and a database dump
    reveals none. Clearing the nonce revokes every link of that guest. The
    token travels only in the URL fragment and in POST bodies, never in a path
    or a query that a log would keep, and every token the manage routes refuse
    gets the same 404. The link in a mail uses a second key: only it may stop
    all mail to the address, so whoever typed someone else's address into a
    form cannot.
-   **Guests hold no credential.** A guest has no password and no session, and
    every dependency that loads a user refuses one (`403 auth.guest_account`).
-   **Addresses are kept as keyed hashes** in the abuse log and the opt-out
    list, and the log is pruned after seven days. No guest's IP address is
    written to the database.

### Operational notes

-   `SECRET_KEY` signs the access tokens. Every environment other than local
    refuses to start while it still reads `changethis`. Rotating it invalidates
    outstanding access tokens (at most 15 minutes of disruption) and leaves
    refresh cookies working. It also invalidates every shared-list guest's
    manage link and changes the keyed address hashes, so the opt-out list
    ("Das war ich nicht") and the day's mail counts stop matching.
-   The `X-Test-User-Email` impersonation header used by the E2E suite is
    reachable only while `TESTING` is true, and the configuration layer refuses
    to construct settings with `TESTING` on in production.

## Versions

The latest version or release is supported.

You are encouraged to write tests for your application and update your versions frequently after ensuring that your tests are passing. This way you will benefit from the latest features, bug fixes, and **security fixes**.

## Reporting a Vulnerability

If you think you found a vulnerability, and even if you are not sure about it, please report it right away by creating a security issue at: https://github.com/Blaxzter/fastapi-vue-fullstack-template/issues

Please try to be as explicit as possible, describing all the steps and example code to reproduce the security issue. When creating the issue, please label it with "security" and mark it as confidential if the platform supports it.

I ([@Blaxzter](https://github.com/Blaxzter)) will review it thoroughly and get back to you.

## Public Discussions

Please restrain from publicly discussing a potential security vulnerability. 🙊

It's better to discuss privately and try to find a solution first, to limit the potential impact as much as possible.

---

Thanks for your help!

The community and I thank you for that. 🙇
