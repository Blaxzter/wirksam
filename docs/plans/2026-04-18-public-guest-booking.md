## Public Guest Booking — Feature Plan (Draft)

> **Superseded** by [`2026-11-10-shared-lists.md`](2026-11-10-shared-lists.md), which is what was built; see [`docs/SHARED_LISTS.md`](../SHARED_LISTS.md).

**Status:** Idea — not yet approved for implementation
**Created:** 2026-04-18

**Goal:** Let unauthenticated visitors book a shift via a public link (e.g. QR code at the task, or a link shared in a group chat) without going through Auth0.

**Motivation:** Auth0 signup is the right friction for recurring users, but it kills conversion for casual / one-time attendees. A public link captures people who'd never bother making an account, while still feeding their booking into the same `Shift` / `Booking` data flow.

---

## Concept

1. Manager generates a **public link** for an task (or event). The link contains a signed token (`/public/tasks/{task_id}?key=…`).
2. Visitor opens the link → sees task info + available shifts (read-only-ish view).
3. Visitor picks a shift → enters minimal info (name + email, phone optional) → captcha → booking confirmed.
4. After booking, optional upsell: "Want reminders / to manage future bookings? Sign up." → Auth0 flow with email prefilled.
5. On Auth0 callback, if the verified email matches an existing guest [`User`](../../backend/app/models/user.py), the account is **promoted** (guest rows + their bookings attach to the new authenticated user).

---

## Open Questions

### 1. Data model: guest-as-user vs. separate `GuestRegistration` table
- **Guest-as-user (recommended):** existing `User` row with `auth0_sub IS NULL` and `is_guest=True`. [`Booking.user_id`](../../backend/app/models/booking.py#L31) FK keeps working unchanged. Promotion = setting `auth0_sub` + flipping the flag.
- **Separate table:** cleaner separation, but every booking query needs a UNION or polymorphic FK. Painful.
- → Lean toward guest-as-user. Need to confirm `User.email` uniqueness/index implications and whether [`auth0_sub`](../../backend/app/models/user.py#L15) can be made nullable without breaking other constraints/queries.

### 2. Captcha + cookie banner
- **reCAPTCHA v3:** low friction, high coverage, but sets Google cookies → likely needs consent banner under GDPR.
- **Cloudflare Turnstile:** explicitly cookie-free, no consent banner needed, comparable UX.
- → Recommend Turnstile unless there's a reason we already need Google's risk signals.

### 3. Returning-visitor recognition
- Store a UUID `device_key` in `localStorage` on first booking; send as optional header on later visits to prefill the form ("Welcome back").
- Mirror the key on the guest `User` row server-side so we don't trust the client to claim someone else's identity.
- **GDPR caveat:** a long-lived recognition key isn't strictly-necessary functional storage. Either gate behind a "remember me on this device" checkbox or include in the cookie/storage notice.

### 4. Public link scope and lifetime
- One link per task? Per event? Per shift batch?
- Expiry: never / task end / manual revoke?
- Revocation strategy: rotate the signing key per task, or store issued tokens in DB so we can mark them revoked?
- Should one link allow multiple bookings (whole task open) or one booking per visit?

### 5. Abuse prevention layers
- Signed URL key handles "random scraper finds the endpoint."
- Backend rate limit per IP + per token (needed regardless — also benefits authenticated routes).
- Captcha on the booking submit.
- Email verification? Magic-link confirmation before booking is "real," or accept unconfirmed and let no-shows be a manager problem?

### 6. Manager UX
- Where in the existing task manager flow does "Create public link" live? Task detail page? Event settings?
- Show a list of guest bookings distinctly (badge / icon) vs. authenticated bookings?

### 7. Notifications for guest users
- Guest gave us an email → can we send a single confirmation + reminder, or do we need explicit consent?
- Reuse existing [`booking_reminder`](../../backend/app/models/booking_reminder.py) infra with a sensible default offset.
- Push/Telegram clearly out of scope for guests; email is the only viable channel.

---

## Technical Approach (if approved)

### Backend
1. Migration: make `User.auth0_sub` nullable, add `User.is_guest` (bool, default false), add `User.device_key` (uuid, indexed, nullable). Keep `email` indexed; consider partial unique index `WHERE is_guest=false` so guest dupes don't block real signups.
2. New `TaskPublicLink` model: `task_id`, `token_hash`, `created_by`, `expires_at`, `revoked_at`. Signed token in URL = `task_id.token`, validated against hash + expiry.
3. New router `app/api/routes/public.py`, mounted **outside** the `CurrentUser` dependency. Endpoints:
   - `GET /public/tasks/{task_id}?key=…` — task + shifts payload
   - `POST /public/tasks/{task_id}/bookings` — create guest user (or reuse via email/device_key) + booking. Captcha token in body, validated server-side.
   - `GET /public/me?device_key=…` — return prior guest bookings for the prefill UX.
4. Rate limit middleware (per IP, per token). [`slowapi`](https://github.com/laurentS/slowapi) is the usual FastAPI pick.
5. Auth0 callback / first-login path in [`users.py`](../../backend/app/api/routes/users.py): on `POST /users/me`, if a guest `User` exists with the same verified email, merge instead of creating a new row (transfer bookings, set `auth0_sub`, clear `is_guest`).
6. Captcha verification helper in `app/logic/`.

### Frontend
1. New `preauth/` views: `PublicTaskView.vue`, `PublicBookingForm.vue`, `PublicBookingConfirmation.vue`. Routed under `PreAuthLayout`.
2. Captcha component (Turnstile widget wrapper).
3. `localStorage` helper for `device_key` (generate on first booking, send via interceptor on public routes only).
4. Post-booking CTA component → existing Auth0 signup flow with email prefill.
5. Manager UI: "Public link" tab on task detail — generate, copy, show QR (a small lib like `qrcode` or server-rendered SVG), revoke.
6. i18n keys in both `en/` and `de/`.
7. Regenerate API client.

### Effort estimate
Medium. Backend is the trickier half (token model, merge logic, rate limit, captcha integration). Frontend is mostly new public views + a manager link-management panel. Migration is straightforward but touches the central `User` table, so worth careful review.

---

## Decision Log

| Date | Decision |
|------|----------|
| 2026-04-18 | Idea captured after exploratory chat. Leaning Turnstile over reCAPTCHA v3, guest-as-user over separate table, email-based merge on Auth0 promotion, optional `localStorage` device key for prefill. |
