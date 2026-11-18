# Shared lists ("Geteilte Listen")

Created 2026-11-10 on `feat/shared-lists` (based on `origin/dev`, HEAD 7fb950f), and
revised the same day after the security/privacy and codebase-fit review.
Supersedes `2026-04-18-public-guest-booking.md`, which was written for Auth0, guest
rows with `auth0_sub IS NULL`, slowapi and one link per task. None of that matches
the code today.

The product owner approved the clickable prototype
(`geteilte-listen.html`, kept outside the repo). There are three corrections, and
they override the prototype:

- (a) Selecting days and selecting shifts must never disagree. The model is one set
  of tasks plus one set of excluded shifts, and the days are derived from it.
- (b) "Schichten pro Person" defaults to "so viele, wie frei sind" (unlimited).
- (c) The management views need real tables with sort controls and server-side
  pagination, and must be built with the usual code-quality care.

### Decisions taken before implementation (2026-11-10)

*Amended by [2026-11-12-shared-lists-guest-vouchers.md](2026-11-12-shared-lists-guest-vouchers.md).*

These override the rest of this document wherever they disagree.

- **Q1: no claiming in v1.** D4, §4.17, §6.4 and every claim item are deferred to a
  follow-up: `claim_grants_membership`, `require_claim_flag_allowed`,
  `shared_list.claim_admin_only`, `guest_claim.*`, `UserProfile.claimable_guest_signups`,
  `app/api/routes/guest_claims.py`, `logic/shared_lists/claim.py`, `GuestClaimsView`,
  `GuestClaimBanner`, the `guest-claims` route and breadcrumb, `stores/guestClaim.ts`,
  the upsell box and "Anmeldung übernehmen" on the public page, the `?email=` prefill in
  `RegisterView`, `tests/api/routes/test_guest_claims.py` and
  `e2e/tests/authenticated/guest-claim.spec.ts`. Everyone who signs up through a list
  stays a guest. Keep the model forward-compatible (guest `users` rows, chains bound to
  a list, guests settled at 0 in `settle_earnings`), so a claim can be added later
  without a data migration. Ignore claim-only steps in algorithms and lock orders.
- **Q2:** `GUEST_DATA_RETENTION_DAYS=30`, counted from the guest's own last shift.
- **Q3:** voucher tasks are allowed on lists; guests earn nothing, and the wizard says so.
- **Q4:** the Terms stay unchanged in 0.29.0. The privacy text covers guests and names
  the operator as controller; it is checked by whoever owns the legal texts before
  release.
- **Q5:** the existing invitation "Geteilte Links" become "Einladungslinks" /
  "Invitation links" in the UI and docs, so they are not confused with "Geteilte Listen".

Paths are relative to the repository root. `app/` means `backend/app/`, and `src/`
means `frontend/src/`. Line numbers refer to HEAD 7fb950f. Re-check them before
editing.

---

## 1. Summary and scope

Organisers, and people in charge of tasks, publish a **shared list**. A shared list
is a public link `/l/<code>` that bundles not-yet-started shifts from one or more
tasks of **one** event. People open the link **without an account**, pick a shift,
type their name (and an email address and phone number if the list asks for them),
and are booked. Organisers get a management page. It shows:

- which lists are live, and who signed up through which list;
- actions to pause, resume, end and rotate a list, singly or in bulk;
- a task overview that shows which free places are in no open list;
- a three-step create/edit wizard.

### In scope (v1)

- Backend:
  - data model and migration;
  - management API with server-side filtering, sorting and pagination;
  - public read and sign-up API;
  - a manage link for guests (cancel, reminders on/off, erase their data, "Das war
    ich nicht");
  - organiser removal of guest sign-ups, singly or in bulk, optionally erasing the
    guest's data (event admins);
  - superadmin lookup, export and erasure of guest data (API only), so data-subject
    requests can be answered;
  - an explicit claim of guest sign-ups into an account with a verified email, only
    on lists whose event admins allowed it (D4);
  - a retention sweep, based on each guest's own shifts;
  - hardening of existing booking code for guest rows;
  - a fix for the existing capacity race in `create_booking`, and for the existing
    reminder collision when a cancelled booking is booked again (§4.12).
- Guest mails, sent directly and never through the in-app channels, built only from
  database fields (no organiser free text):
  - one confirmation per sign-up chain, with the manage link;
  - an optional reminder by email one day before;
  - "your shift was cancelled / moved / you were removed".
- Frontend:
  - the management page (tabs Links / Aufgaben / So sehen es Helfende);
  - the wizard;
  - the detail dialog;
  - the public page `/l/:code` and the guest manage page `/guest-signup`;
  - the claim banner (dashboard and event picker) and the claim page `/app/guest-claims`;
  - an "ohne Konto" tag in the existing rosters and hours;
  - a reusable table kit (pagination, sortable headers, selection bar, filter chips).
- Abuse protection:
  - Turnstile on sign-up (a boot warning outside `local` when it is off);
  - per-IP rate limits;
  - an append-only `guest_activity_log` that every sign-up and every guest mail is
    counted in, with daily ceilings per address, per list, per event and per
    organiser that survive erasure, claims and event deletion (D17);
  - a per-address mail suppression ("Das war ich nicht");
  - an event setting that lets event admins stop people in charge from sharing (D18);
  - a kill switch, `SHARED_LISTS_ENABLED`.
- Docs, privacy copy, landing and FAQ claims, the feature page, and the changelog.

### Non-goals (v1)

- Notifying organisers or people in charge about each sign-up, and digests. Member
  bookings do not notify them either.
- Signed-in members booking *as themselves* through a list. Everybody signs up as a
  guest, and a verified account can claim the sign-up afterwards where the list
  allows it (D4).
- Claiming without becoming a member. The app is built around the selected event
  (`PUT /users/me/selected-event` requires a membership, users.py:118-150), so a
  claimed booking without membership could not be shown anywhere (D4).
- A UI for the superadmin guest lookup. v1 ships the API (§6.2) and documents it.
- Debouncing time-change mails to guests. A debounce that drops later changes would
  leave a guest with a wrong time; the per-address mail ceiling (D17) is the fence.
- Organisers typing in guests by hand, waitlists, a multi-shift cart, SMS, push or
  Telegram for guests.
- Lists spanning events, and cloning lists together with an event (`POST
  /events/{id}/clone` keeps ignoring them).
- Attendance or no-show for guests. Vouchers for guests who have not claimed their
  sign-up (D10).
- Link-preview cards (OpenGraph) per list. Messenger bots do not run JS, so `/l/…`
  previews as the generic WirkSam card.
- Counting unique viewers. `view_count` is approximate.
- Changing the Terms of Service (open question Q4).
- TanStack Table. Rationale in D15.

---

## 2. Decisions with rationale

### D1. Guest identity: a password-less "list guest" `users` row, plus a contact table

There are three options:

| Option | What breaks |
|---|---|
| A. `bookings.user_id` nullable, with guest columns on `bookings` | See the list below. |
| B. A separate sign-up table next to `bookings` | Every free-place count reads `bookings` and would need a UNION with the new table. That is about 12 sites: `crud/booking.py:47-62`, `routes/shifts.py:45-61`, `dashboard.py:249,284,481-492,696-745`, `tasks/feed.py:75-84`, `crud/task.py:162`, `crud/venue_map.py:455`, `crud/event_team.py:221`, `routes/locations.py:233`, `reporting.py:553`, `unfilled_shifts.py:116-125`. |
| **C. A guest `User` row** (`is_list_guest=True`, subject `listguest|<hex>`, `email=NULL`, `password_hash=NULL`), with the contact email in `shared_list_guests` | The guests have to be excluded in a short list of places (§4.12), following the `is_sandbox` precedent. |

What option A breaks:

- **Crash:** `logic/vouchers.py::settle_earnings` (217-320) inserts
  `VoucherEarning.user_id NOT NULL`.
- `BookingReminder.user_id` is NOT NULL.
- `ShiftBookingEntry.user_id` (schemas/booking.py:79), `ShiftBooker.user_id` and
  `AffectedBookingInfo.user_id` are required, so every guest row would be a 500.
- These INNER JOIN `User` and silently drop guest rows: `confirmed_bookers`
  (crud/booking.py:341-368), the CSV export (reporting.py:104) and top volunteers.
- `uq_booking_shift_user` does nothing for NULL user ids.
- The generated client types change in six or more components.

**Chosen: C.** With it, these keep working with no change: capacity,
`uq_booking_shift_user`, `find_conflicting_booking`, reminders and their
`reschedule`, rosters, print views, reporting joins and the user-id-keyed tallies.

These are closed by construction:

- `users.email` stays NULL. So `ix_users_email_lower` (models/user.py:41-48),
  `get_by_email`, the 409 `auth.email_taken` oracle, `request_password_reset`
  (service.py:419-441), `sync_superadmin_role` (service.py:128-176) and the invitation
  lookups (`events.py:1654,1736`, `logic/invitations.py:392`, `triggers.py:744`) never
  see a guest.
- `password_hash` is NULL, so login is impossible.

The remaining touch points are additive (`is_guest` flags) and are listed in §4.12.
That is also what lets the backend work run in parallel (§10).

The `users` row holds `name`, `phone_number` and `preferred_language`. That way the
existing manager-only phone exposure (`shifts.py:356`, `tasks/crud.py:346-350`)
works as it is. `shared_list_guests` holds the email address (never put into
`users.email`), the event, the list the chain started on, the first-name consent
(D12) and the manage-token nonce.

Guests can never hold a token: `password_hash` is NULL, so `authenticate` fails, and
no `auth_sessions` row is ever created for them. The refusal in `api/deps.py` (§4.12)
is defence in depth on every dependency that loads a `User`. `AccessClaimsDep` loads
no row and cannot check the flag, which is acceptable because no token exists.

### D2. One guest user per *sign-up chain*, never per typed email address

The first sign-up from a page visit creates a guest user. "Noch eine Schicht
eintragen" sends back the `guest_token` from the first response and adds to the
same guest user.

- A chain belongs to **one list**: the token only continues a chain whose
  `shared_list_guests.shared_list_id` is the list being signed up on (otherwise 403
  `shared_list.guest_token_invalid`). The button lives on that list's page anyway, and
  this keeps the first-name consent (D12) and the claim permission (D4) one value per
  guest.
- An identity is **never** resolved from a typed email address. Otherwise anyone who
  types X's address would attach bookings to X's guest identity.

This also gives us, for free, `uq_booking_shift_user` and the overlap check
(`find_conflicting_booking`, logic/booking_conflicts.py:147) within one chain.

### D3. Normalisation and deduplication

There is no organiser data entry for guests in v1. Names, email addresses and phone
numbers come only from the public form. If manual entry is added later, it must use
the same functions in `logic/shared_lists/normalize.py`:

- `normalize_name`: NFC, trim, collapse whitespace; 2-100 characters.
- `normalize_email`: trim, lower-case, validated as `EmailStr`, at most 254
  characters. There is no provider-specific folding (no dropping dots for Gmail).
- `normalize_phone`: trim; allowed characters `0-9 +()/-.` and space; 5-30
  characters.
- `first_name`: the first whitespace token, truncated to 30 characters.

The dedupe rules, all checked under the per-shift lock (§4.5):

1. **Same chain, same shift.** `uq_booking_shift_user` applies, and the code answers
   409 `shared_list.already_signed_up`.
2. **Same normalised email on the same shift**, through any list and any chain:
   409 `shared_list.already_signed_up`.
   - We do not compare with `users.email` of member bookings. That would be an
     oracle for "does account X book shift S".
3. **`max_per_person`** is counted per list, by normalised email (§4.6).
4. **No email given.** Nothing can be deduplicated across chains. The organiser's
   sign-up table marks `possible_duplicate=true` when two confirmed guest bookings on
   the same shift have the same `casefold()` name.

### D4. Claiming guest sign-ups: explicit, verified, and only where an event admin allowed it

A claim makes the person a `member` of the event, and a member sees every member's
email address (`GET /events/{id}/members`, events.py:1405-1426) and every published
task. Lists are made to be broadcast (group chats, a QR code on a poster), people in
charge can create them (§4.13), and private events are invitation-only: inviting is
admin-only (events.py:1644, `minimum="admin"`) and join requests are refused
(events.py:1820-1825, `event.not_joinable`). A claim that always granted membership
would let anyone who reaches a posted link into a private event, and would let a
person in charge grant membership, which their role cannot do today.

A claim **without** membership is not offered either: the app is scoped by the
selected event, `PUT /users/me/selected-event` needs a membership (users.py:118-150),
and `GET /bookings/me` filters by it, so the claimed booking could not be shown.

So:

- **Per-list permission.** `shared_lists.claim_grants_membership: bool`, default
  `false`. Only an event admin may set it to `true` (create or PATCH by anyone else
  with `true` → 403 `shared_list.claim_admin_only`; a PATCH that leaves it out keeps
  it). It is the same authority as minting a shareable invitation link (events.py:
  1636-1650), which already turns a broadcast link into membership. The wizard shows
  the option to admins only (§7.4). Open question Q1 asks for its default.
- **Claimable** means: the guest's chain started on a list (`shared_list_guests.
  shared_list_id`) that has `claim_grants_membership = true` and still belongs to
  the guest's event, the guest is not erased, and the event is not a sandbox.
  Sign-ups on other lists stay guest sign-ups, managed through the manage link.
- **Detection.** `build_user_profile` (logic/auth/service.py:179) fills a new
  `UserProfile.claimable_guest_signups: int` (schemas/users.py:32): the number of
  claimable guests with `lower(email) = lower(user.email)` and at least one
  confirmed booking. It is only computed when `user.email_verified`, and uses the
  expression index.
- **Nothing moves automatically.** It does not happen in `verify_email`
  (service.py:531-546), in `register_user`, or in `authenticate`.
  - A banner on the dashboard **and** on the event picker links to an exempt page,
    `/app/guest-claims` (§7.5), which lists the sign-ups; the person confirms.
  - Reason: anyone can type someone else's address. Moving sign-ups automatically
    would let a stranger put a victim's future account into events, and with it
    the `dispatch_task_published` fan-out.
- **Claiming** (`POST /guest-claims`, `CurrentUser`, which requires active and
  approved; additionally `email_verified`), §4.17:
  - settle vouchers for the guest's ended shifts **first** (they earn nothing, D10);
  - create the `member` membership;
  - move each confirmed guest booking to the account (`user_id` changes,
    `shared_list_id` stays) and re-point its voucher earning row;
  - resolve `uq_booking_shift_user` collisions;
  - replace the reminders with the account's defaults;
  - delete the guest user.
- `registration.has_valid_invitation` (registration.py:108-131) does **not** count
  guest sign-ups. A list link is not an invitation into a closed registration.

### D5. Attribution: `bookings.shared_list_id`, without a FK

It is a nullable UUID with an index and **no foreign key**. That is the same pattern
as `VoucherEarning.booking_id` and `WorkLog.created_by_id`.

- It survives a claim, which deletes the guest row; that is why attribution lives on
  the booking. (`shared_list_guests.shared_list_id` exists too, with the same no-FK
  pattern, but it records where a *chain* started, for D2, D4 and D12.)
- A FK with `SET NULL` from `bookings` (which has `user_id CASCADE`) would be exactly
  the trap in `app/models/CLAUDE.md` ("SET NULL … in a table that also points at
  events"): user delete → `events.created_by_id` CASCADE → `shared_lists` CASCADE →
  SET NULL on `bookings` rows being cascade-deleted.
- A dangling id joins to nothing. A list is only ever hard-deleted together with its
  event.

### D6. The list code is short, random, stored in plain text, and rotated in place

- 12 characters from the prototype's alphabet
  `abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789` (54 symbols, no
  i/l/o/I/O/0/1).
  - That is about 69 bits, generated with `secrets.choice`.
  - The prototype's 8 characters give about 46 bits, which is too few against a
    distributed scan once lists number in the thousands.
- `String(16)` with a unique index, **stored in plain text**, like `EventInvitation.token`
  and `CalendarFeedToken.token`. Organisers must be able to copy the link again.
  Hashed tokens (docs/SECURITY.md:19-21) cannot be shown again. The link is meant to
  be public, so a DB dump exposing live codes is accepted and documented.
- Rotation replaces `code` on the same row (precedent: `crud/calendar_feed.py::regenerate_token`
  41-49). The old URL then shows the generic "not found" page.
- The alphabet has no `.`, which keeps `vite preview`'s `!extname(path)` fallback
  (vite.config.ts:34) working.

### D7. The guest manage token is HMAC-derived and never stored

- Format: `token = "<guest.id hex>.<b64url(HMAC-SHA256(K, guest.id || ':' || guest.manage_nonce))>"`,
  where `K = HMAC(SECRET_KEY, b"wirksam/guest-manage/v1")`.
- Every mail (confirmation, reminder, cancellation, time change, removal) can rebuild
  the link without storing a secret. A DB dump does not reveal the token.
- Revocation: set `manage_nonce = NULL`, which happens on erase, "Das war ich
  nicht", claim and the retention sweep.
- The sign-up response also returns this token to whoever submitted the form, for
  "Noch eine Schicht eintragen" and the undo. That is safe because the token only
  reaches the chain the submitter created, and erasing it cannot reset any quota:
  every quota counts the append-only `guest_activity_log` (D17), never
  `shared_list_guests`.
- The mails link to a second token over the same nonce, under a key of its own
  (`b"wirksam/guest-mail/v1"`, `guest_tokens.mail_token`). Both read, cancel, switch
  reminders and erase; only the mail's may say "Das war ich nicht", because that
  stops all mail to the address, and whoever typed the address into the form holds
  the response's token.
- Rotating `SECRET_KEY` invalidates every manage link (and every access token, as
  today). That is documented.
- The token travels in the **URL fragment** (`/guest-signup#<token>`) and in POST
  bodies. It never appears in a path or a query.
  - `RequestLoggingMiddleware` logs `request.url.path` (core/middleware.py:62,82).
  - nginx logs query strings.
  - A fragment is never sent to a server, never put in a Referer header, and is
    harmless to link scanners because the page only acts on a click.

### D8. Status: stored `live | paused | ended`, plus a derived `expired`

`ended` is terminal (the prototype says "Beenden lässt sich nicht rückgängig
machen"). "Expired" is never stored. It is derived on the event's clock (§4.1), so
moving shifts, changing the event zone, or `POST /events/{id}/shift-dates` cannot
leave a stale expiry behind.

### D9. Selection model: tasks plus excluded shifts (correction a)

- A list stores `shared_list_tasks` and `shared_list_excluded_shifts`. There is no day
  whitelist (the prototype's `days` / `offDays` are dropped).
- Day checkboxes are derived in the wizard (§7.4).
- Consequence, which the wizard and the detail dialog state: a shift added later to a
  listed task joins every list that contains the task, even on a day whose shifts
  were all excluded.
- Regenerating shifts gives new shift ids, so the generated shifts come in included,
  and the exclusion rows of deleted shifts cascade away.

### D10. Which tasks can be on a list

*Amended by [2026-11-12-shared-lists-guest-vouchers.md](2026-11-12-shared-lists-guest-vouchers.md).*

- **Team-gated tasks (`tasks.team_id`) never**, neither at creation nor at read time.
  `team_id` is admin-only precisely because "it decides who may book"
  (docs/PEOPLE_IN_CHARGE.md:62-68), and a guest can never be an approved team
  member.
- **Published tasks only**, checked at creation and again on every public read and
  write.
- **Voucher tasks are allowed. A shift that ends while a guest holds it earns
  nothing, ever** (open question Q3), and the wizard shows a hint.
  - Guests are **not** filtered out of `settle_earnings`: their bookings are settled
    like everyone's, with `amount = 0` (§4.12). Filtering them out would leave the
    booking unsettled, so a rate raised after the shift, followed by a claim, would
    pay it at the new rate, against "earned is earned" (docs/VOUCHERS.md:162-168).
  - Settled rows with `amount = 0` are already invisible to every voucher read
    (`_voucher_shifts` keeps `VoucherEarning.amount > 0`, vouchers.py:371), and the
    `derived` select skips guests, so a guest never shows up in a voucher view.
  - A claim settles first, then moves the booking together with its earning row
    (§4.17). Shifts that end after the claim earn like any account booking.
- Shifts that have started are never offered, whatever the task. This is stricter
  than members' `booking.shift_over`. The prototype says "Schichten, die schon
  angefangen haben, verschwinden".

### D11. The event must be published

- Creating or resuming a list on an event whose `status != "published"` fails with
  409 `shared_list.event_not_published`.
- If the event later becomes draft or archived, the list is effectively `expired`.
- Private events are allowed. The link is the capability, as with invitation links.
  The landing copy that says "only people you invite" must change (§9).

### D12. Who sees a guest

*Amended by [2026-11-12-shared-lists-guest-vouchers.md](2026-11-12-shared-lists-guest-vouchers.md).*

- The **name** shows wherever member names show (rosters for event members).
- **Email and phone** go only to event admins and the people in charge of *that task*.
  This is the same rule as for member contact data (`shifts.py:327-361`).
- **The public page shows first names only of guests who were told so when they
  signed up.** The consent is stored on the sign-up, never read from the list's
  current setting: `shared_list_guests.show_first_name` is set when the chain is
  created (§4.7 step 13), only if the form showed `show_names == 'first'` (the request
  says what it showed) and the list still says so, and a chain never leaves its list
  (D2). Member names are never shown publicly.
  - Changing `show_names` on a live list therefore affects new sign-ups only; the
    wizard says so (§7.4). Switching a list to `first` cannot publish a guest who
    signed up under "Niemand sieht, wer sich eingetragen hat".
  - A list shows names at all only while its own `show_names` is `first`, so
    switching it back to `none` hides everyone.
  - This fixes the prototype's privacy flaw: its "Dabei:" line included account
    holders who never agreed to appear on a public page, and guests from a list that
    promised "Niemand sieht, wer sich eingetragen hat".
- The fine print on the form changes to tell the truth (§7.5): a consenting guest's
  first name appears at that shift on **every** list with first names that includes
  it, not only on this one.

### D13. Guests get mail only, through one choke point, written from database fields

- `NotificationService.notify` (logic/notifications/service.py:79-95) gets a branch
  right after the `is_sandbox` skip and **before** the title and body are resolved:
  - for `recipient.is_list_guest`, it calls
    `guest_mail.deliver_notice(self.db, *, recipient, type_code, data)` for the
    types in `GUEST_MAIL_TYPES = {"booking.reminder", "booking.cancelled_by_admin",
    "shift.time_changed"}`;
  - it **always `continue`s**, so no in-app row, SSE or push is created.
- `deliver_notice` never sees the resolved title or body. The member texts carry
  organiser free text: `booking.cancelled_by_admin` appends "Grund: {reason}" from
  the `cancellation_reason` query parameter of shift, task and batch deletes
  (triggers.py:137-166, shifts.py:281), which people in charge can set too. They also
  point to "My Bookings" (locales/en.json:24), which guests do not have. Instead
  `guest_mail` renders its own en/de templates from database rows only (§4.11), with
  `data` used as a lookup key:
  - `booking.reminder`: `data["booking_id"]` → the booking, its shift, task and event;
  - `shift.time_changed`: `data["slot_id"]` → the guest's confirmed booking on that
    shift, with the **current** times;
  - `booking.cancelled_by_admin`: the guest's bookings with `status='cancelled'`,
    `shift_id IS NULL` (the shift is gone) and a snapshot date of today or later,
    that have no `cancelled` row in `guest_activity_log` yet. `data` names only the
    first booking of the batch (triggers.py:206), so the mail lists all of them from
    the snapshot columns (`cancelled_shift_*`, `cancelled_task_name`).
- Every existing trigger therefore reaches guests with no change at its call site:
  - shift, batch or task deleted (`cancel_bookings_for_shifts` →
    `dispatch_booking_cancelled_by_admin`);
  - shift moved (`shifts.py:246-268`);
  - reminder poller.
- Everything else (co-booked, task published, …) is dropped for guests.
- Every guest mail passes the ceilings of D17 first.
- `UNDELIVERABLE_SUBJECT_PREFIXES` (channels/base.py:12) gains `"listguest|"` as
  defence in depth.

### D14. Guest reminders are opt-in, by email, one day before

- The form checkbox "Erinnere mich am Tag vorher per Mail" is shown only when an
  email address is typed. It is checked by default.
  - The legal basis is performance of the requested sign-up, Art. 6(1)(b), not
    consent.
  - Every mail carries the manage link with an off switch.
- It creates one `BookingReminder` row: `offset_minutes=1440`, `channels=["email"]`,
  `user_id=<guest user>`, written with the new `crud_reminder.replace_for_booking`
  (§4.5a), never with a plain insert.
- `reschedule()` and `cancel_by_booking()` keep working unchanged.

### D15. Management tables

- Server-side `skip`/`limit` + `sort_by`/`sort_dir` + `q` + `status_filter`. The
  response has the `{items, total, skip, limit, counts}` shape (schemas/event.py:144-148
  and routes/users.py:155-172).
- Lists and tasks of **one event**:
  - The per-event aggregates are computed with a fixed number of SQL queries (no N+1).
  - The derived status and the issue (both need the event clock and cross-list
    coverage) are computed in Python over **all lists of the event**. Then the code
    filters, sorts and slices.
  - This is bounded by a hard cap of 200 lists per event (409 `shared_list.too_many`).
  - The prototype computed counts and issues over every list. Doing the same on the
    server keeps filter counts, the summary and "Zu tun" correct while paginating.
- Sign-ups are pure SQL pagination.
- The frontend uses a small kit (§7.2), not TanStack Table.
  - The repo pins `@tanstack/vue-table` 8.21.3, while the current shadcn-vue
    data-table guide is v9.
  - Phones need a separate card list anyway.
  - The tables have tens of rows.

### D16. Terminology

The existing event invitation links are labelled "Share links" / "Geteilte Links"
(`duties.json:356,365,375`). They are renamed to "Invitation links" /
"Einladungslinks", and the new feature is "Shared lists" / "Geteilte Listen"
(open question Q5).

### D17. Every guest sign-up and every guest mail is counted in an append-only log

Any account can create and publish an event (events.py:238-250, "Any signed-in user
may"), so event, task and shift names in a guest mail are chosen by whoever creates
the list, and the address is whatever the anonymous visitor typed. The invitation
precedent (logic/invitations.py:69-70, 3 per address and 200 per inviter a day)
only works because the inviter is signed in. Guest mail needs the same kind of
fence, and it must not live in a table that anybody can empty:

- `guest_activity_log` (§3.1) gets one row per guest sign-up and one per guest mail
  sent. It has **no foreign keys**: erasing a guest, claiming, rotating a list or
  deleting the event never removes a row, so none of them resets a quota. Rows are
  pruned after 7 days (§4.15).
- Addresses are stored only as `address_hash = hex(HMAC-SHA256(K_addr,
  normalised email))` with `K_addr = HMAC(SECRET_KEY, b"wirksam/guest-address/v1")`.
- Ceilings (all in `core/config.py`, all counted over the last 24 h). The
  per-address counts run under the advisory lock `guest-address:{address_hash}` and
  are exact; the per-list count runs under `shared-list-day:{list_id}`; the per-event
  and per-organiser counts are not serialised across addresses and may overshoot by
  the number of concurrent senders, which is fine for a coarse fence:
  - `GUEST_SIGNUPS_PER_ADDRESS_PER_DAY = 20` sign-ups per address (429);
  - `GUEST_SIGNUP_EVENTS_PER_ADDRESS_PER_DAY = 3` other events per address (429),
    the invitation level;
  - `GUEST_MAILS_PER_ADDRESS_PER_DAY = 10` mails of every kind per address;
  - `GUEST_MAILS_PER_EVENT_PER_DAY = 1000` and `GUEST_MAILS_PER_ORGANISER_PER_DAY =
    2000` mails, the organiser being `events.created_by_id` at send time;
  - `SHARED_LIST_SIGNUPS_PER_LIST_PER_DAY = 500` sign-ups per list (429).
  A mail over a ceiling is not sent; the log line names the kind and the event,
  never the address. Mails that organisers trigger (moving a shift a thousand times,
  deleting shifts) are capped by the same per-address ceiling, which is why there is
  no separate debounce.
- **"Das war ich nicht."** The manage page offers it, and every mail mentions it.
  It erases the guest (§4.9) and stores the address hash in
  `guest_mail_suppressions`. A suppressed address can still be typed into a form,
  but nothing is ever mailed to it again; the response says `mail_queued=false`,
  exactly as for a missing SMTP server, so this is no oracle.
- Only one confirmation per chain (the first sign-up); follow-ups are listed on the
  manage page that the first mail links to.
- Under `settings.TESTING` the ceilings are skipped (rows are still written), like
  `logic/invitations.py::_limits_apply`.

### D18. Event admins can stop people in charge from sharing

People in charge can create lists for their own tasks, which opens those tasks to
strangers; today nothing they can do reaches outside the event (inviting is
admin-only, events.py:1644). So:

- `events.managers_share_lists: bool`, NOT NULL, default `true` (the product owner
  asked for people in charge to share), admin-only like
  `managers_edit_voucher_shifts` (models/event.py:97-107, events.py:254-259
  `_NOT_NULL_SETTINGS`).
- When it is `false`, a person in charge who is not an event admin gets 403
  `shared_list.managers_disabled` on create, PATCH, resume and rotate. Pausing and
  ending stay allowed (stopping is always fine), and they keep reading their lists
  and sign-ups. `SharedListRow.access` stays `manager`; the refusal comes from the
  action argument of `require_shared_list_manager` (§4.13).
- `POST /events/{id}/shared-lists/pause-all` takes `{lock_managers: bool}`; with
  `true` it also sets the setting to `false`, so an emergency stop cannot be undone
  by a person in charge resuming their own list.
- The checks live inside the §4.13 gates, so grepping for them still finds every one.

---

## 3. Data model

All tables inherit `Base` (app/models/base.py:25-45). Every datetime is naive UTC,
`sa.DateTime`, never `DateTime(timezone=True)` (app/models/CLAUDE.md). Values are
stamped with `clock.utc_now()`.

Enums are `String(16)` with a named CHECK and a `Literal[...]` in the schemas; there
is no `sa.Enum`. CHECKs and server defaults are not detected by `alembic check`
(env.py:110-150), so they must be mirrored by hand in model and migration.

There is no `ondelete="SET NULL"` anywhere in the new tables.

### 3.1 New module `app/models/shared_list.py`

```python
ListStatus = Literal["live", "paused", "ended"]        # stored
EndsMode = Literal["last_shift", "date", "manual"]
AskMode = Literal["required", "optional", "off"]
ShowNames = Literal["none", "first"]
```

**`shared_lists`** (`SharedList`)

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| id, created_at, updated_at | Base | | | `ix_shared_lists_id` |
| event_id | Uuid FK `events.id` ON DELETE CASCADE | no | | covered by the composite index |
| code | String(16) | no | | `unique=True, index=True` → `ix_shared_lists_code` (unique) |
| title | String(120) | no | | |
| intro | Text | yes | NULL | max 1000 characters (schema) |
| share_note | String(120) | yes | NULL | "Wo teilst du den Link?"; organisers only |
| status | String(16) | no | `'live'` (server_default) | `ck_shared_lists_status` |
| paused_at, ended_at, rotated_at | DateTime | yes | NULL | |
| ends_mode | String(16) | no | `'last_shift'` | `ck_shared_lists_ends_mode` |
| ends_on | Date | yes | NULL | inclusive, event wall clock |
| ask_email | String(16) | no | `'required'` | `ck_shared_lists_ask_email` |
| ask_phone | String(16) | no | `'off'` | `ck_shared_lists_ask_phone` |
| show_names | String(16) | no | `'none'` | `ck_shared_lists_show_names` |
| max_per_person | Integer | yes | **NULL = unlimited (default)** | `ck_shared_lists_max_per_person` |
| claim_grants_membership | Boolean | no | `false` (server_default) | D4; only event admins set it to true |
| view_count | Integer | no | `0` | approximate |
| created_by_id | Uuid, **no FK** | yes | | snapshot pattern (TaskManager.added_by_id) |
| created_by_name | String | yes | | snapshot |

`__table_args__`:

- `CheckConstraint("status IN ('live','paused','ended')", name="ck_shared_lists_status")`
- `CheckConstraint("ends_mode IN ('last_shift','date','manual')", name="ck_shared_lists_ends_mode")`
- `CheckConstraint("(ends_mode = 'date') = (ends_on IS NOT NULL)", name="ck_shared_lists_ends_on")`
- `CheckConstraint("ask_email IN ('required','optional','off')", name="ck_shared_lists_ask_email")`
- the same check for `ask_phone`, named `ck_shared_lists_ask_phone`
- `CheckConstraint("show_names IN ('none','first')", name="ck_shared_lists_show_names")`
- `CheckConstraint("max_per_person IS NULL OR max_per_person BETWEEN 1 AND 50", name="ck_shared_lists_max_per_person")`
- `Index("ix_shared_lists_event_id_status", "event_id", "status")`

Why `created_by_id` has no FK: a CASCADE would delete the list and its attribution
when the creator deletes their account. A SET NULL would hit the trap in
models/CLAUDE.md.

There is no ORM `Relationship` from `Event`. Event deletion goes through the ORM, and
a relationship without `passive_deletes` would load the rows first.

**`shared_list_tasks`** (`SharedListTask`)

- `shared_list_id`: Uuid FK `shared_lists.id` CASCADE, NOT NULL.
- `task_id`: Uuid FK `tasks.id` CASCADE, NOT NULL, `index=True`.
- `position`: Integer NOT NULL, default 0. It is the order in the share message.
- `UniqueConstraint("shared_list_id", "task_id", name="uq_shared_list_task")`.
- Its index serves the lookups by `shared_list_id`.

**`shared_list_excluded_shifts`** (`SharedListExcludedShift`)

- `shared_list_id`: FK CASCADE, NOT NULL.
- `shift_id`: Uuid FK `shifts.id` CASCADE, NOT NULL, `index=True`.
- `UniqueConstraint("shared_list_id", "shift_id", name="uq_shared_list_excluded_shift")`.

**`shared_list_guests`** (`SharedListGuest`), one row per guest user

- `user_id`: Uuid FK `users.id` CASCADE, NOT NULL, `unique=True, index=True`.
- `event_id`: Uuid FK `events.id` CASCADE, NOT NULL, `index=True`. The event of the
  list at the first sign-up. It is **not** used for retention (§4.15), because a
  moved task takes the guest's bookings to another event.
- `shared_list_id`: Uuid, **no FK** (D5 pattern), NOT NULL, `index=True`. The list the
  chain started on (D2); decides the claim (D4).
- `email`: String(254) NULL. It is normalised and **never** copied to `users.email`.
- `show_first_name`: Boolean NOT NULL, `server_default=sa.false()`. The consent of
  D12, copied from the list at the first sign-up and never changed afterwards.
- `manage_nonce`: String(32) NULL. NULL means every manage link is dead.
- `last_signup_at`: DateTime NOT NULL.
- `erased_at`: DateTime NULL.
- `__table_args__`: `Index("ix_shared_list_guests_email_lower", sa.text("lower(email)"),
  postgresql_where=sa.text("email IS NOT NULL"))`. It is non-unique, because the same
  address may sign up through several chains, and it must be declared here, like
  `ix_users_email_lower`.
- Both FKs CASCADE, so deleting the event removes the contact address and the manage
  link at once. The guest `users` row and its bookings stay (tasks survive an event
  delete as orphans) and are handled by the sweep (§4.15).

**`guest_activity_log`** (`GuestActivityLog`), append-only, D17

- `kind`: String(16) NOT NULL, `ck_guest_activity_log_kind`:
  `kind IN ('signup','confirmation','reminder','cancelled','moved','removed')`.
  Every kind except `signup` is a mail.
- `address_hash`: String(64) NULL (no address given).
- `event_id`, `shared_list_id`, `booking_id`, `organiser_id`: Uuid NULL, **no FKs**, so
  no delete anywhere can remove a row and reset a quota.
- Indexes: `ix_guest_activity_log_address_created` on `(address_hash, created_at)`
  `WHERE address_hash IS NOT NULL`; `ix_guest_activity_log_event_created` on
  `(event_id, created_at)`; `ix_guest_activity_log_list_created` on
  `(shared_list_id, created_at)`; `ix_guest_activity_log_organiser_created` on
  `(organiser_id, created_at)`; `ix_guest_activity_log_booking_id` on `booking_id`
  (the "already told about this cancellation" lookup of D13).
- Pruned after 7 days by the sweep (§4.15). It holds no address in clear text.

**`guest_mail_suppressions`** (`GuestMailSuppression`)

- `address_hash`: String(64) NOT NULL, `unique=True, index=True` →
  `ix_guest_mail_suppressions_address_hash` (unique).
- Never pruned: it records a person's wish not to be mailed. No clear-text address.

### 3.2 Changes to existing models

**`app/models/user.py`**: add `is_list_guest: bool`, `sa.Boolean`, NOT NULL,
`server_default=sa.false()`, `index=True` → `ix_users_is_list_guest`. Mirror the
`is_sandbox` field at user.py:59-69 and extend the class docstring (user.py:10-26):
"`listguest|` marks sign-up-list guests, which no channel contacts. Their mail goes
through `logic/shared_lists/guest_mail.py`."

A guest user is created with exactly these values:

- `subject=f"listguest|{uuid4().hex}"`
- `is_list_guest=True`
- `email=None`, `password_hash=None`
- `name=<normalised>`, `phone_number=<normalised or None>`, `preferred_language=<'en'|'de'>`
- `default_reminder_offsets=[]`
- `notify_email=notify_push=notify_telegram=False`
- `roles=[]`, `approval_status="approved"`, `is_active=True`

**`app/models/booking.py`**: add `shared_list_id: uuid.UUID | None`, `sa.Uuid`,
nullable, `index=True` → `ix_bookings_shared_list_id`, **no ForeignKey**. Add a
comment citing D5.

**`app/models/event.py`**: add `managers_share_lists: bool`, `sa.Boolean`, NOT NULL,
`server_default=sa.text("true")`, next to `managers_edit_voucher_shifts`
(event.py:97-107), with a description in the same style (D18).

**`app/models/__init__.py`**: import the six new models. Without the imports,
`env.py` cannot see them and autogenerate proposes drops.

### 3.3 Migration

File `app/alembic/versions/2026MMDD_NNNN_shared_lists.py`. The revision id is assigned
by `env.py::_next_revision_id`. `down_revision` is the head at the time of writing
(today `20261104_0004`). Re-check it against `origin/dev` before merging.

- **Docstring**: why each table exists, D1/D5/D6, and the FK rationale. Follow
  `20261030_0001_add_task_managers.py`.
- **Upgrade**, in this order:
  1. `users.is_list_guest` + `ix_users_is_list_guest`;
  2. `bookings.shared_list_id` + `ix_bookings_shared_list_id`;
  3. `events.managers_share_lists` (server default `true`, so existing events keep
     the product owner's default);
  4. `shared_lists` (all CHECKs, `ix_shared_lists_id`, `ix_shared_lists_code` unique,
     `ix_shared_lists_event_id_status`);
  5. `shared_list_tasks` (`ix_shared_list_tasks_id`, `ix_shared_list_tasks_task_id`,
     `uq_shared_list_task`);
  6. `shared_list_excluded_shifts` (`ix_…_id`, `ix_…_shift_id`, `uq_…`);
  7. `shared_list_guests` (`ix_…_id`, `ix_shared_list_guests_user_id` unique,
     `ix_shared_list_guests_event_id`, `ix_shared_list_guests_shared_list_id`,
     `ix_shared_list_guests_email_lower`);
  8. `guest_activity_log` (`ix_…_id`, the CHECK, the five indexes of §3.1);
  9. `guest_mail_suppressions` (`ix_…_id`, `ix_guest_mail_suppressions_address_hash`
     unique).
- **Downgrade**: the reverse order, dropping indexes before their tables, then the
  three columns.
- **Backfill**: none.
- **Verify the round trip**: `alembic upgrade head`, `alembic downgrade -1`,
  `alembic upgrade head`, `alembic check` ("No new upgrade operations detected").

---

## 4. Business rules

### 4.1 Status and expiry, on the event's clock

`logic/shared_lists/offer.py` (WP1):

```python
EffectiveStatus = Literal["live", "paused", "expired", "ended"]

def starts_at(date: dt.date, start: dt.time | None) -> dt.datetime:
    # The booking "started" rule (bookings._refuse_if_shift_started, 400-419):
    # an untimed shift starts at 00:00. Deliberately NOT crud/shift.py:81-105
    # upcoming_condition, which treats an untimed shift as upcoming all day.
    return dt.datetime.combine(date, start or dt.time())

def effective_status(sl, *, event, last_start, now_wall) -> EffectiveStatus:
    if sl.status == "ended": return "ended"
    if sl.status == "paused": return "paused"
    if event.status != "published": return "expired"
    if sl.ends_mode == "date" and now_wall.date() > sl.ends_on: return "expired"
    if sl.ends_mode == "last_shift" and (last_start is None or last_start <= now_wall):
        return "expired"
    return "live"      # manual: live even with nothing left to offer
```

- `now_wall = clock.wall_clock_now(event.timezone)`. Always call it through the
  module attribute, so tests can patch `app.logic.clock.wall_clock_now`.
- One list belongs to one event, so it has one zone. Every management endpoint is
  per event, so one `now_wall` serves the whole request.
- `last_start` is the maximum `starts_at` over the list's **included** shifts:
  - the task is linked to the list;
  - `task.event_id == list.event_id`;
  - `task.status == "published"`;
  - `task.team_id IS NULL`;
  - the shift is not excluded.
- SQL twin: `func.max(Shift.date + func.coalesce(Shift.start_time, sa.time(0)))`.
  In Postgres, date + time is a timestamp.
- `closes_at`, for display:
  - `last_shift`: `last_start`;
  - `date`: the end of `ends_on`;
  - `manual`: None.
- `expires_soon`: `effective == "live"`, `ends_mode == "date"`, and
  `0 <= (ends_on - now_wall.date()).days <= 3`.

### 4.2 Ends modes and their validation

- `last_shift` (default): the list stays open until the last included shift starts.
- `date`: the list stays open through `ends_on`, **inclusively**, in the event zone.
  - On create or edit: `ends_on >= now_wall.date()`, and
    `ends_on <= date of the last included shift`.
  - Otherwise 422 `shared_list.ends_on_invalid` with the extension
    `{last_shift_date}`.
  - If shifts move later and the stored `ends_on` falls out of range, that is
    harmless. Started shifts vanish anyway.
- `manual`: open until somebody ends it. Started shifts still vanish.
- `POST /events/{id}/shift-dates` (events.py:436-500) moves `ends_on` by the same
  delta, through `crud_shared_list.shift_ends_on(event_id, delta)` (WP2 adds the call
  after step 4, "Shift shifts").
- A zone change (events.py:340-355) needs nothing, because expiry is derived.

### 4.3 Transitions

There is one function, `logic/shared_lists/manage.py::transition(session, sl, action, *, event, now_utc, now_wall)`
(WP2). It runs under `crud_shared_list.get_for_update` (`SELECT … FOR UPDATE`).

| Action | From | Result | Refusals |
|---|---|---|---|
| pause | effective `live` | `status=paused`, `paused_at=now` | `paused`: no-op 200. `expired`: 409 `shared_list.not_live`. `ended`: 409 `shared_list.ended` |
| resume | `paused` or effective `expired` | `status=live`, `paused_at=None`. If the list was expired by date or last_shift: `ends_mode="last_shift"`, `ends_on=None`. Then re-derive | `live`: no-op. `ended`: 409. Still expired after re-derivation: 409 `shared_list.nothing_to_offer`. Event not published: 409 `shared_list.event_not_published` |
| end | anything except `ended` | `status=ended`, `ended_at=now` (terminal) | `ended`: no-op |
| rotate | anything except `ended` | new `code`, `rotated_at=now` | 409 `shared_list.ended` |
| edit (PATCH) | anything except `ended` | fields overwritten, `code` kept | 409 `shared_list.ended` |

This fixes prototype flaw 2: bulk resume and single resume now share the code that
clears `paused_at` and `ends_on`.

Ending, pausing and editing **never touch bookings**. "Wer eingetragen ist, bleibt
eingetragen."

### 4.4 Which shifts a list offers

`offer.list_shifts(session, sl, *, now_wall, include_started=False) -> list[OfferedShift]`
returns the shifts with all of these properties:

- the shift's task is in `shared_list_tasks`;
- `Task.event_id == SharedList.event_id`. This is defence in depth for moved tasks.
- `Task.status == "published"`;
- `Task.team_id IS NULL`;
- the shift is not in `shared_list_excluded_shifts`;
- `starts_at > now_wall`, unless `include_started`.

Each `OfferedShift` carries `confirmed` (one GROUP BY, the `tasks/feed.py:75-84`
pattern) and `free = max(0, max_bookings - confirmed)`. The clamp is needed because
`max_bookings` can be lowered below the number of bookings (schemas/shift.py:19,36
have no `ge`).

The ordering is `(date, start_time NULLS FIRST, task name)`, the prototype's `byTime`.

The public page and the sign-up both use only this function.

### 4.5 Capacity and race safety

*Amended by [2026-11-12-shared-lists-guest-vouchers.md](2026-11-12-shared-lists-guest-vouchers.md).*

New module `app/logic/booking_capacity.py` (WP1):

```python
async def lock_shifts(session, shift_ids: Iterable[uuid.UUID]) -> None:
    for sid in sorted(set(shift_ids)):
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"shift-capacity:{sid}"},
        )
```

- It is a transaction-scoped advisory lock (precedents: `logic/invitations.py:86-107`,
  `crud/voucher.py:237-256`).
- It is not `FOR UPDATE` on `shifts`, which would also block the `FOR KEY SHARE` that
  every booking insert takes for its FK.
- It must be taken **before** counting by every path that adds a confirmed booking:
  - guest sign-up (WP3);
  - **member `create_booking` (WP4)**. This fixes the existing race at
    bookings.py:198-202, where two members can take the last place.

Lock order, which avoids cycles. Every path that touches a guest row locks it
**before** any shift lock, and every multi-shift path takes its shift locks once,
sorted, through one `lock_shifts` call:

| Path | Locks, in order |
|---|---|
| Guest sign-up | event row `FOR KEY SHARE` → list row `FOR KEY SHARE` → chain's guest row `FOR UPDATE` (chains only) → `guest-address:{hash}` (also serialises the per-person count by address) → `shared-list-day:{list_id}` → shift lock |
| Member booking | membership `FOR KEY SHARE` (`_lock_membership`) → shift lock |
| Claim | guest rows `FOR UPDATE` (sorted by id) → `crud_membership.lock_member_ids` → `lock_shifts(all shift ids, sorted)` |
| Guest manage | guest row `FOR UPDATE` (no shift locks; cancelling only frees places) |
| Organiser removal | guest rows `FOR UPDATE`, one statement in id order → `guest-address:{hash}` per mail, in hash order (no shift locks) |
| Patch / pause / resume / end / rotate, one list or a batch | event row `FOR SHARE` → list rows `FOR UPDATE`, in id order (no shift locks) |
| Pause-all | event row `FOR NO KEY UPDATE` → list rows `FOR UPDATE`, in id order |
| Deleting the event (existing) | event row `FOR UPDATE` → list rows by CASCADE |
| Guest mail (background) | `guest-address:{hash}` only, in its own transaction |

- The sign-up takes `FOR KEY SHARE` on the list row, not `FOR SHARE`. `FOR KEY SHARE`
  still conflicts with the transitions' `FOR UPDATE`, so a pause waits for in-flight
  sign-ups, and once it has committed no sign-up that read "live" can complete. It
  does **not** conflict with the `FOR NO KEY UPDATE` that the public GET's
  `view_count` increment takes (§4.8), so a crowd opening a hot list never queues
  behind sign-ups.
- The concurrency tests patch the limits switch on (`settings.TESTING` → the ceilings
  of D17 apply), so they exercise the production lock order, not a shortened one.

Double submit on the same shift: insert inside `session.begin_nested()` and turn an
`IntegrityError` on `uq_booking_shift_user` into a 409. Today it is an uncaught 500
(WP4 applies the same to `create_booking`, with 409 `booking.already_exists`).

### 4.5a Reminders on a booking that already had some

`booking_reminders` has `UniqueConstraint(booking_id, offset_minutes,
name="uq_reminder_booking_offset")` (models/booking_reminder.py:21-31), and
`cancel_by_booking` only sets `status='cancelled'` (crud/booking_reminder.py:175-190),
so the row stays. Any path that cancels reminders and later writes them again for
the same booking id collides and answers 500:

- today already: book, `DELETE /bookings/{id}`, book again. `create_booking`
  reactivates the same row (bookings.py:212-218) and then calls
  `create_from_defaults` (257-267) for offsets whose cancelled rows still exist.
  `test_rebook_cancelled_shift` (tests/api/routes/test_bookings_extended.py:126-160)
  misses it because it seeds the cancelled booking without reminders;
- the guest reminder toggle off → on (§4.9);
- a chain re-signing a shift it undid (§4.7 step 14);
- the claim, where the guest's 1440/email row meets the account's defaults
  `[15 push, 1440 email]` (models/user.py:189-198).

So WP1 adds one helper to `crud/booking_reminder.py`, and every one of those paths
uses it instead of `create_reminder` / `create_from_defaults`:

```python
async def replace_for_booking(
    self, db, *, booking_id, user_id, shift_id,
    entries: Sequence[ReminderOffsetEntry], slot_start: dt.datetime, zone: str | None,
) -> list[BookingReminder]:
    # DELETE the booking's rows whose status is not 'sent', then INSERT one row per
    # entry (remind_at/status via _fires_at). A 'sent' row for an offset is kept and
    # that offset is skipped, so a reminder that went out is never sent twice.
```

`entries=[]` just deletes the pending ones. The guest reminder is
`[ReminderOffsetEntry(offset_minutes=1440, channels=["email"])]`.

### 4.6 `max_per_person`

- NULL means unlimited, and that is **the default**. The wizard's "so viele, wie frei
  sind" is the prototype's value 0, mapped to NULL.
- With an email address: under the lock `shared-list-email:{list_id}:{address_hash}`,
  count confirmed bookings with `shared_list_id = list.id` whose guest row has
  `lower(email) = email`. If the count is `>= max`, answer 409
  `shared_list.max_per_person` with `{max}`. Erasing a guest lowers this count, which
  is fine: it limits places held, not mail (D17 limits mail).
- Without an email address but with a `guest_token`: count the chain's confirmed
  bookings on this list.
- Without either, nothing can be counted. The wizard states this ("Gezählt über die
  E-Mail-Adresse").
- Wizard options: `null`, then 1 up to `min(3, included shift count)`. A chosen value
  is clamped when the options shrink.
- The sign-up response carries `remaining: int | None`: None when unlimited, otherwise
  `max - count`, counted by email or by chain.

### 4.7 The sign-up algorithm

`POST /public/shared-lists/{code}/signups` → `logic/shared_lists/signup.py::sign_up(...)` (WP3).
The steps run in this order:

1. If `settings.SHARED_LISTS_ENABLED` is off: 404 `shared_list.disabled`.
2. Rate limits: `shared_list_signup_limiter.check(f"{ip}|{code}")` and
   `shared_list_signup_ip_limiter.check(ip)` (§5).
3. If `settings.turnstile_enabled` and not
   `await verify_turnstile(body.turnstile_token, expected_action="shared-list-signup")`:
   403 `auth.captcha_failed`.
4. Read the list by code without a lock, lock its event `FOR KEY SHARE`
   (`crud_event.lock`), then `crud_shared_list.get_by_code(code, lock="key_share")`
   (`SELECT … FOR KEY SHARE`, §4.5). The event comes first because deleting it takes
   the event row before the list rows its CASCADE reaches. Unknown code: 404
   `shared_list.not_found`.
5. Load the event and derive the status:
   - paused → 409 `shared_list.paused`;
   - expired or ended → 409 `shared_list.closed`.
6. Validate the fields against the list:
   - `ask_email=required` and no email → 422 `shared_list.email_required`;
   - `ask_phone=required` and no phone → 422 `shared_list.phone_required`;
   - with `off`, the value is dropped.
   - Format errors are the normal pydantic 422 from the schema.
7. The shift must be in `offer.list_shifts(..., include_started=True)`, otherwise 404
   `shared_list.shift_not_offered`. If it has started: 409 `shared_list.shift_started`.
8. `guest_token` given: `guest_tokens.resolve()` must return a non-erased guest whose
   `shared_list_id` is this list (D2), locked `FOR UPDATE`; otherwise 403
   `shared_list.guest_token_invalid`. The stored name, email and phone win over the
   body.
9. Address admission, with an email address (`logic/shared_lists/guest_quota.py::
   admit_signup`, D17):
   - take the lock `guest-address:{address_hash}`;
   - `signup` rows for the hash in the last 24 h `>= GUEST_SIGNUPS_PER_ADDRESS_PER_DAY`
     (20), or distinct `event_id`s among them other than this event `>=
     GUEST_SIGNUP_EVENTS_PER_ADDRESS_PER_DAY` (3): 429
     `shared_list.too_many_for_address`;
   - a suppressed address is admitted, but step 16 will not mail it.
   - The counts are skipped under `settings.TESTING`, like
     `logic/invitations.py::_limits_apply`.
10. Daily list cap:
    - take the lock `shared-list-day:{list_id}`;
    - `signup` rows with that `shared_list_id` in the last 24 h `>=
      SHARED_LIST_SIGNUPS_PER_LIST_PER_DAY` (500): 429 `shared_list.daily_limit`.
      Counted in the log, so erasing or undoing sign-ups cannot reset it; it bounds
      the churn of new `users` rows.
    - Off under TESTING.
11. `max_per_person` (§4.6).
12. `lock_shifts([shift.id])`, then:
    - same email on the shift (a confirmed booking of any guest with that email) →
      409 `shared_list.already_signed_up`;
    - chain already **confirmed** on the shift → 409 `shared_list.already_signed_up`;
    - `find_conflicting_booking(user_id=<chain user>)` → 409 `booking.time_conflict`
      (reuses the existing extensions);
    - `get_confirmed_count >= max_bookings` → 409 `booking.slot_full`.
13. New chain: create the guest user (§3.2) and the `SharedListGuest` row with
    `event_id`, `shared_list_id = list.id`, the normalised email,
    `show_first_name = (body.show_names == "first" and list.show_names == "first")`,
    `manage_nonce =
    secrets.token_hex(16)`, `last_signup_at = now`. A chain only updates
    `last_signup_at`.
14. The booking:
    - the chain has a **cancelled** row on this shift (it undid that sign-up):
      reactivate it (`status="confirmed"`, `shared_list_id=list.id`, clear
      `cancellation_reason`), as `create_booking` does (bookings.py:212-218);
    - otherwise insert `Booking(shift_id, user_id=<guest>, status="confirmed",
      shared_list_id=list.id)` inside a savepoint (§4.5).
15. Reminder: if `remind` and an email is present, `crud_reminder.replace_for_booking`
    with the 1440/email entry (§4.5a); otherwise `replace_for_booking(entries=[])`,
    which clears what a reactivated row still had.
16. Log and mail (D17), still under the address lock:
    - append a `signup` row (`address_hash` or NULL, `event_id`, `shared_list_id`,
      `booking_id`);
    - first sign-up of a chain with an email: `guest_quota.reserve_mail(kind=
      "confirmation")`, which appends a `confirmation` row and returns False when the
      address is suppressed, over a mail ceiling, or `settings.emails_configured` is
      off. If True, a background task sends `guest_mail.send_signup_confirmation(...)`
      after the commit (`get_db` commits before the response).
    - There is **no** `dispatch_booking_confirmed` and no `dispatch_booking_cobooked`.
17. Return `PublicSignupResult` (§6.3) with `mail_queued` = the result of the
    reservation (False for follow-ups, which the first mail's link covers).

### 4.8 What the public page reveals

`GET /public/shared-lists/{code}` returns the list title and intro, the event name,
dates and timezone, and the list's ask and show settings.

When effective `live`, it also returns the offered shifts grouped by day:

- task name, location, times, `capacity`, `free`, `full`;
- only while this list's `show_names` is `"first"`: `names` and `others_count`.
  `names` holds the first names of confirmed bookings on that shift whose user is a
  list guest with `shared_list_guests.show_first_name = true` and `erased_at IS NULL`
  (D12), whatever list they came through. `others_count` is the confirmed count minus
  `len(names)`.

It **never** returns:

- full names, email addresses, phone numbers, user ids;
- task descriptions, manager names;
- other lists, `share_note`, `created_by_name`, `view_count`.

When the list is paused or closed, `days` is `[]`.

For an unknown or rotated code, the response is 404 `shared_list.not_found`, and
`shared_list_miss_limiter` is checked as an enumeration speed bump (§5).

The response sets `Cache-Control: no-store`.

The title and intro are organiser text shown to strangers on a WirkSam page, so the
frontend renders them as plain text interpolation with `whitespace-pre-line`: no
`v-html`, no `renderMarkdown` (lib/markdown.ts linkifies and is meant only for
`LocationDescription.vue`), no linkify (§7.5).

`view_count` is incremented with an atomic `UPDATE … SET view_count = view_count + 1`,
only when the list is effectively `live`, as the **last statement** of the request,
so its row lock is held only until the commit that follows (`get_db` commits before
the response). It never conflicts with a sign-up's `FOR KEY SHARE` (§4.5). The
organiser preview never counts (§6.2).

### 4.9 Guest self-service (the manage link)

All of these are bodies to `/public/guest-signups/*` (§6.3). The token is resolved
with a constant-time compare, and the guest row is locked `FOR UPDATE`. Any failure
is 404 `guest_signup.not_found` (no distinction).

- **Read**: the guest's name and email, and every booking (confirmed and cancelled)
  with its task, event, times, place, `can_cancel` and `reminder_on`. The event is
  read per booking (shift → task → event), because a moved task takes a booking to
  another event.
- **Cancel one booking**: allowed until the shift is over, the same rule as members
  (`_refuse_if_booked_shift_over`, bookings.py:448-457, 409 `booking.shift_over`).
  - `status="cancelled"`, then `crud_reminder.cancel_by_booking`.
  - No mail to the guest (they did it), and nothing to organisers (same as members).
- **Reminders on or off**: `replace_for_booking` (§4.5a) on every future confirmed
  booking, with the 1440/email entry for on and `[]` for off, so toggling twice
  never collides. Without an email address: 409 `guest_signup.no_email`.
- **Erase my data** (`logic/shared_lists/erase.py::erase_guest`, shared with §4.10,
  the "Das war ich nicht" action and the superadmin endpoint):
  - **deletes** the guest's bookings whose shift is not over, and every cancelled
    booking (their reminders cascade). Nothing about them is worth keeping, and
    deleting frees places at once;
  - anonymises: `users.name=NULL`, `users.phone_number=NULL`, `guest.email=NULL`,
    `guest.manage_nonce=NULL`, `guest.erased_at=now`;
  - keeps confirmed bookings of shifts that are over, anonymous, so fill rates and
    hours stay correct; if none remain, deletes the guest `users` row at once;
  - never touches `guest_activity_log`, so erasing cannot reset a quota (D17).
  - The frontend shows erased rows as "Gast (gelöscht)".
- **"Das war ich nicht"**: `erase_guest`, plus the address hash goes into
  `guest_mail_suppressions` (D17) if the guest had an email address. 204. Only with
  the token from a mail (D7); the sign-up's is 403 `guest_signup.mail_link_required`.
  Only the operator lifts a suppression (`/list-guests/mail-suppressions/lift`).

A guest without an email address uses the same endpoints. Their only key is the
manage link that the done page shows them to keep (§7.5); organisers can erase them
on request (§4.10, `erase`).

### 4.10 Organisers removing guest sign-ups

`POST /shared-lists/{list_id}/signups/remove` (WP3), body
`SharedListSignupRemoveRequest` (§6.2). One endpoint serves the single "Austragen"
row action, a selection, and the clean-up of a wave of fake sign-ups:

- **Selector**, exactly one of (else 422 `shared_list.remove_selector`):
  - `booking_ids` (1..100);
  - `created_since: datetime` (naive UTC): every confirmed guest sign-up through
    this list created at or after that moment, at most 500 per call. The UI offers it
    as "Diese und alle neueren austragen" on a sign-up row.
- `notify: bool = True`. Off for spam clean-up, so the typed addresses are not mailed a
  second time.
- `erase: bool = False`: also run `erase_guest` (§4.9) for every guest touched.
  **Event admins only** (403 `shared_list.forbidden`): it is how organisers honour a
  guest who asks them to delete their data, which matters most for guests without an
  email address, who have no manage link in a mailbox.
- The caller must see the list (§4.13). Per booking, refused rows go to `skipped`
  with their code, never failing the batch:
  - `booking.shared_list_id != list_id` → `shared_list.signup_not_found`;
  - `task_access(user, session, task)` is None → `shared_list.forbidden`;
  - the booking user is no longer `is_list_guest` (claimed) →
    `shared_list.signup_not_guest`;
  - the shift is over → `booking.shift_over` (an ended booking would need
    `settle_earnings` first; refusing keeps "earned is earned" trivially true).
    With `erase`, ended bookings are not removed but anonymised with their guest.
- The guest rows of every selected booking `FOR UPDATE` in one statement, in id order;
  each removed booking `status="cancelled"`, and the reminders of all of them
  cancelled in one statement (`cancel_by_bookings`), so the clean-up of 500 costs no
  more statements than one. With `notify` and an email, one `removed` mail per guest
  (listing their removed shifts) in the background, through the D17 reservation,
  reserved in the order of the address hashes: two removals may share addresses.
- Response `SharedListSignupRemoveResult`.

This is the only per-booking organiser cancel in the app. Member bookings stay out of
scope.

### 4.11 Guest mails

All of them live in `logic/shared_lists/guest_mail.py` (WP3) and go through
`send_action_mail` (logic/auth/emails.py:132-198):

- every mail first passes `guest_quota.reserve_mail(session, *, address, kind,
  event_id, booking_id)` (D17), which takes `guest-address:{hash}`, refuses a
  suppressed address or one over a ceiling, and otherwise appends the log row: one
  per mail, however many shifts it names, since the ceilings count mails;
- a cancellation mail names exactly the bookings in the notice's `booking_ids`, which
  `dispatch_booking_cancelled_by_admin` fills with the person's bookings of that action
  on shifts not over yet, and names the event from the notice's scope (a moved task
  took its bookings to another event);
- gated on `settings.emails_configured` **before** calling `send_action_mail`. That
  function logs the action URL when SMTP is missing (emails.py:157-172), which is
  acceptable for one-time auth tokens but not for a manage token that reads, cancels
  and erases until retention. So without SMTP a guest mail is not reserved, not
  sent, and only "guest mail not sent: SMTP not configured ({kind})" is logged; the
  sign-up answers `mail_queued=false` and the done page shows the manage link
  instead (§7.5). Locally the mailcatcher counts as configured;
- `action_url` is the manage link `f"{settings.FRONTEND_HOST}/guest-signup#{token}"`;
  every mail says that the same page has "Das war ich nicht";
- written in `users.preferred_language` of the guest;
- every interpolated value is escaped.

**No organiser free text** (the rule in invitation_emails.py:14-18): event name, task
name, date, times and place only, read from the database. The list title and intro,
the `cancellation_reason`, the resolved notification title and body, and the member
texts in `logic/notifications/locales/*.json` are never used. Templates are guest
templates of their own, in en and de.

| Function | Kind in the log | When |
|---|---|---|
| `send_signup_confirmation` | `confirmation` | the first sign-up of a chain with an email address |
| `deliver_notice(session, *, recipient, type_code, data)` | `reminder` / `cancelled` / `moved` | the NotificationService branch (D13) |
| `send_removed` | `removed` | §4.10 with `notify` |

### 4.12 Existing behaviour for guest bookings (WP4 unless noted)

| Area | Behaviour | Change |
|---|---|---|
| Capacity, `uq_booking_shift_user`, overlap check, rosters, print | work unchanged | none |
| `api/deps.py` (`_current_user` 214-259, `_get_user_from_query_token` 269-…) | defence: no guest may ever use a token | `if user.is_list_guest: raise_problem(403, code="auth.guest_account")` **unconditionally**, right after the user is loaded, on both the `X-Test-User-Email` path and the token path of `_current_user`, and in `_get_user_from_query_token`. Not in `_refuse_unusable`: that runs only when `require_active` (deps.py:233-234, 254-255), and `AnyUser` (`require_active=False`) backs `GET` and `DELETE /users/me` |
| `crud/user.py::search` (85) | admin user list and counts | add `col(User.is_list_guest).is_(False)` to `q_clauses` |
| `GET /shifts/{id}/bookings` (shifts.py:327-361) | email for guests comes from `shared_list_guests` | `ShiftBookingEntry.is_guest: bool = False`, `via_list_title: str \| None` (manager rows only). On `show` rows, guest email via `crud_shared_list_guest.contact_emails(user_ids)` |
| `confirmed_bookers` (crud/booking.py:341-368) | names on tiles | `ShiftBooker.is_guest` |
| `GET /tasks/{id}/bookings` (tasks/crud.py:330-352) | print views | `TaskBookingEntry.is_guest` |
| Task moved to another event (tasks/crud.py:255-266) | lists of the old event must drop it; guest bookings move with the task | `await crud_shared_list.detach_task_from_lists(session, task_id=db_task.id)` next to `detach_task`. The bookings stay as they are; retention follows them (§4.15) |
| `logic/vouchers.py::settle_earnings` (217-324) | a shift that ends while a guest holds it earns nothing, frozen (D10) | **no filter**: join `User` and write `amount = case((User.is_list_guest, 0), else_=Task.vouchers_per_shift)`. The candidate filter `vouchers_per_shift > 0` stays, so guest rows on paying tasks are frozen at 0 |
| the `derived` select in `_voucher_shifts` (374-397) | an unsettled guest booking must not show as earning or upcoming | join `User`, `User.is_list_guest IS FALSE`. Settled 0-rows are already hidden by `amount > 0` (vouchers.py:371) |
| `logic/work_hours.py::event_hours` (216-248) | guests appear in the "former" loop with role None | `VolunteerHours.is_guest` from `user.is_list_guest`. The frontend tags them. Hours count, which is the truth |
| `routes/reporting.py::export` (77-163) | email NULL for guests | outer join `SharedListGuest` on `user_id`, `coalesce(User.email, SharedListGuest.email)`, new column `booked_via` (list title or empty) |
| `_volunteer_counts` / `_top_volunteers` | each guest user is one volunteer | none (correct as is) |
| `create_booking` (bookings.py:134-269) | race and double-submit 500 | `lock_shifts` before the count, savepoint + 409 (§4.5) |
| `create_booking` rebooking a cancelled row (212-218 then 257-267) | **existing bug**: `create_from_defaults` collides with the cancelled reminders on `uq_reminder_booking_offset` → 500 | use `crud_reminder.replace_for_booking` with `user.default_reminder_offsets` (§4.5a) |
| `PATCH /bookings/{id}` to cancelled (286-312) | **existing bug**: reminders keep firing | call `crud_reminder.cancel_by_booking` |
| `dispatch_booking_cobooked` | lists guest user ids | none: `notify` drops guests (D13) |
| `POST /testing/reset` (testing.py:63-75) | E2E guests | also delete list-guest users that have no `shared_list_guests` row (their test event was deleted with its test owner) |
| Notifications, `channels/base.py` | | **WP3** (D13) |
| `UserProfile.claimable_guest_signups` | | **WP3** (D4) |

Also unaffected: `crud_membership.list_members`, because guests are never members.
That keeps their data out of `GET /events/{id}/members` (events.py:1405-1426, which
shows emails to every member). It also keeps them out of `dispatch_task_published`
and the team pickers.

### 4.13 People in charge: scoping

New gates in `app/logic/permissions.py` (WP1). They are the only checks, so grepping
for them finds every one:

```python
SharedListAccess = Literal["admin", "manager", "viewer"]
ManageAction = Literal["edit", "pause", "resume", "end", "rotate"]

async def shared_list_scope(user, session, event: Event) -> SharedListScope
    # 1. sandbox first: event.is_sandbox and event.created_by_id != user.id → 404 event.not_found
    #    (get_event_role reports the superadmin as owner of every event, permissions.py:120-135;
    #    require_event_visible checks the sandbox before the role for this reason, :170-174)
    # 2. role None → 404 event.not_found
    # 3. dataclass: role, is_admin: bool,
    #    managed_task_ids: frozenset[UUID] (crud_task_manager.task_ids_for_user ∩ tasks of event),
    #    managers_share_lists: bool (event setting, D18)
    # 4. not is_admin and managed_task_ids is EMPTY → 403 shared_list.forbidden. An empty set
    #    means "nothing", never "unrestricted" (the event_scope trap in CLAUDE.md).

async def shared_list_access(user, session, sl) -> SharedListAccess | None
    # same sandbox test on sl's event first; role None → None; admin+ (incl. superadmin) → "admin";
    # current task set T = linked tasks with task.event_id == sl.event_id;
    # T non-empty and T ⊆ managed → "manager"; T ∩ managed non-empty → "viewer"; else None

async def require_shared_list_visible(user, session, sl) -> SharedListAccess   # None → 404 shared_list.not_found
async def require_shared_list_manager(user, session, sl, action: ManageAction) -> SharedListAccess
    # viewer → 403 shared_list.forbidden;
    # "manager", action in (edit, resume, rotate), event.managers_share_lists false → 403 shared_list.managers_disabled
async def require_shared_list_tasks(user, session, event, task_ids) -> TaskAccess
    # sandbox → 404; role None → 404 event.not_found; admin → "admin";
    # member: managers_share_lists false → 403 shared_list.managers_disabled;
    # every id must be managed → else 403 shared_list.tasks_forbidden {task_ids: [not managed]}
async def require_claim_flag_allowed(user, session, event, requested: bool | None) -> None
    # requested True and caller not admin+ → 403 shared_list.claim_admin_only (D4)
```

Every filter on `managed_task_ids` is written as an explicit branch, `if
scope.is_admin: <no filter> else: task_id IN managed_task_ids`, never `if
scope.managed_task_ids:`.

- **Create**: only with tasks the caller manages (`require_shared_list_tasks`), and
  `claim_grants_membership=true` only for event admins (`require_claim_flag_allowed`).
- **Manage** (edit, pause, resume, end, rotate, bulk): the caller is an event admin,
  or manages **every** task currently on the list. This is evaluated on every call
  against the *current* task set, because grants disappear when a person leaves, is
  removed, or the task moves. While `managers_share_lists` is off, a person in charge
  may only pause and end (D18).
- **See**: event admins see every list. A person in charge sees lists that touch at
  least one managed task, read-only when they do not manage all of them.
  - The lock note reads: "In dieser Liste stecken auch Aufgaben, für die andere
    verantwortlich sind. Ändern können sie deshalb nur die Organisator:innen."
- **Sign-ups seen by a viewer or manager**: only rows on tasks they manage.
  - Rows on other tasks are omitted, and `hidden_count` reports how many.
  - Contact data follows D12.
  - This fixes prototype flaw 6.
- **"Alle pausieren"** is for event admins only (`require_event_role(minimum="admin")`),
  and with `lock_managers` also switches `managers_share_lists` off (D18).
- **A plain member** (no managed task) gets 403 `shared_list.forbidden` from every
  management endpoint, through `shared_list_scope` step 4.
- A list whose creator lost access stays visible and manageable for event admins.
  `created_by_name` is a snapshot.
- A list with an empty current task set can be managed by admins only, and is
  effectively `expired` (last_shift) or empty.
- The coverage computations (stranded or unlisted places) use **all** lists of the
  event, whoever the viewer is. A shift covered by somebody else's live list is not
  stranded (prototype `liveShiftIds`, which is correct).
- Navigation signal: `EventRead.managed_task_count: int` (schemas/event.py:108-131
  pattern; members only, else 0). It is filled in `decorate_events` (events.py:93-156)
  through a new `crud_task_manager.count_by_event_for_user(session, user_id, event_ids)`
  (WP2).

### 4.14 Deletion and lifecycle cascades

| Event | Effect |
|---|---|
| Event deleted (ORM, owner only, events.py:1275; also via `events.created_by_id` CASCADE and sandbox purge) | `shared_lists` → tasks / excluded rows CASCADE. `shared_list_guests` CASCADE (the email address and the manage link are gone at once). Tasks survive as orphans (tasks.event_id SET NULL) with their bookings, so the guest `users` rows stay; the sweep anonymises them by their own shift dates and deletes them once no booking is left (§4.15). `guest_activity_log` keeps its rows (no FK) |
| Task deleted (tasks/crud.py:358-401) | `shared_list_tasks` CASCADE. Guest bookings are cancelled by `cancel_bookings_for_shifts` → guest mail through D13 |
| Task moved | link rows deleted (§4.12). The guest bookings move with the task and keep working (manage link, mails, reminders); retention follows their shift dates, not the guest's event (§4.15). They no longer appear under the old list's sign-ups, since the task left it. If the source event is deleted later, those guests lose their address and manage link with it, and their bookings in the target event stay until the sweep finds them over (accepted, documented in docs/SHARED_LISTS.md) |
| Task gets `team_id`, is unpublished, or archived | it drops out at read time. The detail dialog shows `offered=false` with a reason |
| Shift deleted or regenerated away | exclusion rows CASCADE. Bookings cancelled with the snapshot → guest mail |
| Shift moved (shifts.py:237-270) | reminders `reschedule`, guest mail `shift.time_changed` |
| `POST /events/{id}/shift-dates` | `ends_on` shifted (§4.2) |
| Event zone change | nothing (derived) |
| Guest user deleted (claim, erase with nothing left, sweep, admin `DELETE /users/{id}`) | `shared_list_guests`, bookings, reminders, voucher earnings CASCADE (the claim re-points earnings first, §4.17) |
| List creator deleted | nothing (no FK) |

Regression tests to extend:

- `tests/api/routes/test_event_members.py::TestUserDeletionCascades`: delete the
  creator of an event that has a list and guest sign-ups.
- An event delete that has lists, guests and bookings: no FK violation, guest users
  and bookings survive, `guest_activity_log` rows survive.

### 4.15 Retention sweep

`logic/shared_lists/retention.py::sweep_guest_data(session, *, today_utc, retention_days)` (WP3):

Retention is decided per guest **user**, from that user's own bookings, never from
`shared_list_guests.event_id`: a moved task takes bookings to another event, and an
event delete leaves bookings on orphan tasks.

`last_date(u) = max(coalesce(Shift.date, Booking.cancelled_shift_date))` over all of
`u`'s bookings, or `last_signup_at::date` (or `users.created_at::date` without a guest
row) when there are none. A guest is **due** when `last_date + retention_days <
today_utc`. Day granularity makes the event zone irrelevant for a 30-day rule.

1. **Anonymise** due guests that still have a `shared_list_guests` row and are not
   erased: delete their cancelled bookings, then the anonymising part of §4.9 (no
   shift of theirs can still be ahead).
2. **Anonymise due orphans**: `is_list_guest` users without a `shared_list_guests`
   row (their event was deleted): delete their cancelled bookings, `users.name=NULL`,
   `users.phone_number=NULL`. A guest user is **never** deleted while it still has
   bookings, so a confirmed booking in a moved task's new event survives its source
   event.
3. Delete list-guest users with `name IS NULL` and **no** bookings left.
4. Delete `guest_activity_log` rows older than 7 days.

- `GUEST_DATA_RETENTION_DAYS` (config, default 30; open question Q2).
- It is called from `reminder_poller.py` every `_GUEST_SWEEP_EVERY_N_CYCLES = 120`
  (about 1 h), under the poller's advisory lock (`_ADVISORY_LOCK_KEY`), like
  `_UNFILLED_EVERY_N_CYCLES`. There is no other scheduler.
- The privacy policy text promises exactly this rule (§9).

### 4.16 Sandbox

> **Changed after the plan:** a demo shares lists after all, so the sandbox can
> show the feature. `guest_quota.reserve_mail` refuses every guest mail about a
> demo event instead, the public pages say it is a demo, and `purge_sandbox`
> deletes the lists, the guest users and their log rows. See
> [`SHARED_LISTS.md`](../SHARED_LISTS.md#in-a-demo). The first two bullets
> below describe the original design.

- Creating a list on a sandbox event is refused with
  `refuse_if_sandbox(session, event_id, code="sandbox.shared_lists_disabled",
  detail="Shared lists cannot be published from a demo event")` (logic/sandbox/guards.py:15-40).
  The sandbox guest is `owner`, so it would pass every role gate.
- So no guest ever exists in a sandbox. `purge_sandbox` needs no step. Its event
  delete cascades `shared_lists` and `shared_list_guests` anyway.
- The **read** endpoints matter too: `/overview`, `/tasks`, `/candidates` and
  `/candidate-shifts` read a demo's task names, people in charge and fill levels.
  `get_event_role` reports the superadmin as `owner` of every event
  (permissions.py:120-135), so every event-scoped shared-list route and the gates
  `shared_list_scope`, `shared_list_access` and `require_shared_list_tasks` test
  `event.is_sandbox and event.created_by_id != user.id` → 404 `event.not_found`
  **before** the role, as `require_event_visible` does (:170-174).
- Add rows to the invisibility checklist in docs/SANDBOX.md (:223-262) for every
  shared-list endpoint, and to "What is deliberately not built" (:288).

### 4.17 Claim algorithm

*Amended by [2026-11-12-shared-lists-guest-vouchers.md](2026-11-12-shared-lists-guest-vouchers.md).*

`logic/shared_lists/claim.py::claim(session, user, guest_ids)` (WP3):

1. Require `user.email_verified` and `user.email`, else 403
   `guest_claim.email_unverified`.
2. For each guest id, sorted: `SELECT … FOR UPDATE` on the guest row, and keep it only
   if it is **claimable** (D4): `lower(email) == lower(user.email)`, `erased_at IS
   NULL`, the event is not a sandbox, and its list has `claim_grants_membership =
   true`. Every other id is reported in `not_found`, without saying why.
3. Collect the shift ids of every **confirmed** booking of the kept guests and call
   `lock_shifts(sorted ids)` **once** (§4.5), so two claims over overlapping shifts
   cannot deadlock.
4. `vouchers.settle_earnings(session, now=clock.wall_clock_now(zone),
   shift_ids=<those shift ids>)` per event, **before** anything moves: a shift that
   ended while a guest held it is frozen at 0 (D10).
5. Membership: `crud_membership.lock_member_ids` (crud/event_membership.py:30-56);
   if there is none, create `role="member"`, the same upsert `POST
   /invitations/{token}/accept` performs (routes/invitations.py:189-…).
6. For each confirmed guest booking:
   - the user has no row on that shift: `booking.user_id = user.id`;
   - the user's row is `confirmed`: leave the guest booking alone (it cascades with
     the guest user in step 9) and count it in `skipped_duplicates`;
   - the user's row is `cancelled`: **delete the user's cancelled row**, then move the
     guest booking. Moving keeps the guest booking's id, so its `shared_list_id`,
     its voucher earning row and its history stay together; reactivating the
     user's row instead would orphan the earning row.
   Cancelled guest bookings are not moved; they cascade with the guest user.
7. `UPDATE voucher_earnings SET user_id = :user WHERE booking_id IN (:moved)`.
   `voucher_earnings.user_id` is `ON DELETE CASCADE` (models/voucher.py:148-151), so
   without this the frozen 0-rows would vanish with the guest user and the next
   read would derive the booking at today's rate.
8. Reminders: for the moved bookings whose shift is ahead,
   `crud_reminder.replace_for_booking(entries=user.default_reminder_offsets, …)`
   (§4.5a); for the rest, `entries=[]`. The guest's 1440/email row never collides.
9. Delete the guest `users` row. `shared_list_guests`, the guest's remaining bookings
   and reminders CASCADE, and the manage links die with the row.
10. Return `GuestClaimResult`; the frontend selects `event_ids[0]` afterwards (§7.5).

Overlaps with the account's other bookings are not checked: both bookings existed
already, and refusing would leave the person with neither. The claim page shows
every moved shift.

---

## 5. Abuse and privacy

**Rate limits.** New buckets in `app/core/rate_limit.py` (WP3), each with a comment
naming its key, as at rate_limit.py:156-198:

```python
# 120 per 10 minutes, keyed by IP: opening list pages. A venue behind one NAT
# (club Wi-Fi, a tablet at the stand) must survive a crowd opening the link.
shared_list_view_limiter = RateLimiter(limit=120, window_seconds=600, code="shared_list.rate_limited")
# 20 per 10 minutes, keyed by IP, checked ONLY when a code is unknown.
shared_list_miss_limiter = RateLimiter(limit=20, window_seconds=600, code="shared_list.rate_limited")
# 120 per hour, keyed by "<ip>|<code>"; and 240 per hour keyed by IP. Sized for a
# tablet at the stand or one venue NAT signing up a queue of people on one list
# (about 2 a minute). Abuse is fenced by Turnstile and the DB-counted ceilings
# of D17, not by these.
shared_list_signup_limiter = RateLimiter(limit=120, window_seconds=3600, code="shared_list.rate_limited")
shared_list_signup_ip_limiter = RateLimiter(limit=240, window_seconds=3600, code="shared_list.rate_limited")
# 30 per 10 minutes, keyed by IP: every /public/guest-signups/* call.
guest_manage_limiter = RateLimiter(limit=30, window_seconds=600, code="guest_signup.rate_limited")
```

These are per worker (four workers make them up to 4x looser), they reset on restart,
and they are no-ops under TESTING. The real fences are the DB-counted ceilings of D17
(§4.7 steps 9, 10 and 16; every guest mail) and the 200-lists-per-event cap. The key
is always `client_ip(request)` (rate_limit.py:140-153).

**Turnstile.**

- Extend `verify_turnstile(token, *, expected_action: str | None = None)`
  (core/turnstile.py:58). When `expected_action` is given, a body whose `action`
  differs is a failure. Today a token solved on the register widget would be
  accepted. Existing callers are unchanged.
- The sign-up passes `"shared-list-signup"`.
- It stays optional, because self-hosted deployments without Cloudflare must keep the
  feature, and the mail ceilings of D17 do not depend on it. Outside
  `ENVIRONMENT=local`, a model validator in `core/config.py` emits
  `warnings.warn("SHARED_LISTS_ENABLED without TURNSTILE_SECRET_KEY: …")` at boot, in
  the style of `_check_default_secret` (config.py:343-352), and docs/deployment.md
  recommends it.
- Import it by name in `public_shared_lists.py` so tests can patch
  `app.api.routes.public_shared_lists.verify_turnstile` (the test_auth.py:520-535
  pattern).
- The `turnstile_token` field is optional in the schema (schemas/auth.py:115-128
  pattern).

**Token entropy.**

- List codes: about 69 bits (D6).
- Manage tokens: an HMAC-SHA256 tag (256 bits) over a 128-bit nonce (D7).

**No enumeration.**

- Unknown, rotated and disabled codes give the same 404 body, except for the
  `disabled` code.
- The manage endpoints answer 404 for every token failure.
- The claim GET answers only for the signed-in, verified account's own address.
- The duplicate-email 409 is scoped to one shift and is behind the rate limits.
  That is an accepted residual risk.
- A suppressed address answers exactly like a missing SMTP server
  (`mail_queued=false`).

**Not indexed by search engines.**

- nginx (`frontend/nginx/default.conf`):
  `location ^~ /l/ { add_header X-Robots-Tag "noindex, nofollow" always; add_header Referrer-Policy "same-origin" always; try_files /spa.html =404; }`,
  and the same for `location = /guest-signup`.
- The route meta `noindex` makes `installPageHead` add `<meta name="robots"
  content="noindex, nofollow">`. That meta is the part E2E can assert, because CI
  uses `vite preview`, not nginx.
- robots.txt (scripts/prerender.mjs:461-472) gets `Disallow: /guest-signup`, but
  **not** `/l/`. A disallowed URL is never fetched, so its noindex would never be
  seen, while the URL itself can still be listed.
- The routes are **not** in `PUBLIC_PAGES` (src/lib/seo.ts), so they are not
  prerendered, not in the sitemap, and not in llms.txt.

**Kill switch.**

- `SHARED_LISTS_ENABLED: bool = True` in `core/config.py` (next to `SANDBOX_ENABLED`,
  config.py:278). When off, every shared-list endpoint answers 404
  `shared_list.disabled`.
- Frontend: `AppConfig.SHARED_LISTS_ENABLED`, the default in `useAppConfig.ts`, the
  line in `docker-entrypoint.sh` (l.3-18), read with `isSwitchOn()`.
- It is **not** added to the prerender `TOGGLES`. The landing copy is written to be
  true for the hosted default, and docs/self-hosting.md says so.
- `REGISTRATION_MODE` does not gate guests, because no account is created. This is
  documented next to the switch.

**GDPR**: see §9 for the wording changes, and the data minimisation choices:

- no IP address is stored;
- addresses in `guest_activity_log` and `guest_mail_suppressions` only as keyed
  hashes; the log is pruned after 7 days (Art. 6(1)(f), abuse protection);
- the guest page writes nothing to storage itself: the guest token lives in
  component memory, and it is stripped from the address bar with
  `history.replaceState` once read (§7.5). The shared footer's `LanguageSwitch`
  (`localStorage 'locale'`, LanguageSwitch.vue:61) and `AppearanceMenu`
  (vueuse `useColorMode`, AppearanceMenu.vue:16) store a choice only when the visitor
  changes it; the privacy text says exactly that;
- retention (§4.15), based on each guest's own shifts;
- self-service erase and "Das war ich nicht" (§4.9);
- organiser erase on request (§4.10) and the superadmin lookup, export and erase
  (§6.2), so a request to the operator can be honoured for guests with or without
  an email address;
- the public first-name rule, with the consent stored on the sign-up (D12);
- the manage link is never written to a log (§4.11).

---

## 6. API

### Conventions

- Errors: `raise_problem(status, code=…, detail=…, extensions=…)` (core/errors.py:222-235).
  Never `CRUDBase.get(raise_404_error=True)` in new public routes, because it has no
  code.
- The operation id is `f"{tag}-{route.name}"`. Function names are listed below and
  must stay stable.
- Declare `response_model=` and the return annotation.
- Side effects go through `BackgroundTasks`, with the dispatcher imported by name in
  the route module.

Router registration in `app/api/api.py` (WP1, with stub modules):

```python
api_router.include_router(shared_lists.router)         # WP2, tags=["shared-lists"]
api_router.include_router(shared_list_guests.router)   # WP3, tags=["shared-list-guests"]
api_router.include_router(public_shared_lists.router)  # WP3, tags=["public-shared-lists"]
api_router.include_router(guest_claims.router)         # WP3, tags=["guest-claims"]
```

No new path lives under `/users/…`, because the catch-all `GET /users/{user_id}`
shadows literals there (api.py comment).

The common query params of the paginated endpoints are `skip: int = Query(0, ge=0)`,
`limit: int = Query(20, ge=1, le=100)`, and `q: str | None = Query(None, max_length=100)`.

- `q` is matched with ILIKE, with `%` and `_` escaped through a new helper
  `app/crud/search.py::like_pattern(q)` (WP1). The existing event and task searches do
  not escape, and that is left alone.
- The sort tiebreaker is always `id`.

### 6.1 Management: `app/api/routes/shared_lists.py` (WP2), schemas in `app/schemas/shared_list.py`

Every route checks the kill switch first. Event-scoped routes load the event
(`crud_event.get`, 404 `event.not_found`) and then call `shared_list_scope(user,
session, event)` (or `require_shared_list_tasks`), which tests the sandbox **before**
the role (§4.16), answers 404 for no role and 403 `shared_list.forbidden` for a member
who manages nothing (§4.13). `refuse_if_sandbox` additionally guards create.

| Method and path | Function | Gate | Request → response |
|---|---|---|---|
| GET `/events/{event_id}/shared-lists` | `list_shared_lists` | `shared_list_scope` | query: `status_filter: Literal["active","todo","live","paused","ended"]="active"`, `q`, `sort_by: Literal["status","created_at","title","signups","free","closes"]="status"`, `sort_dir: Literal["asc","desc"] \| None` (per-key default: status asc, created_at desc, title asc, signups desc, free desc, closes asc, with nulls last), skip, limit → `SharedListListResponse` |
| GET `/events/{event_id}/shared-lists/overview` | `get_shared_lists_overview` | `shared_list_scope` | → `SharedListOverview` |
| GET `/events/{event_id}/shared-lists/tasks` | `list_shared_list_tasks` | `shared_list_scope` | `status_filter: Literal["all","todo"]="all"`, `q`, `sort_by: Literal["name","free","unlisted_free"]="name"`, `sort_dir`, skip, limit → `SharedListTaskListResponse` |
| GET `/events/{event_id}/shared-lists/candidates` | `list_shared_list_candidates` | `shared_list_scope` | `q`, skip, `limit≤50` → `SharedListCandidateListResponse` |
| GET `/events/{event_id}/shared-lists/candidate-shifts` | `list_shared_list_candidate_shifts` | `require_shared_list_tasks` | `task_id: list[UUID]` (1..50, else 422) → `list[SharedListCandidateShift]` (not started only) |
| POST `/events/{event_id}/shared-lists` | `create_shared_list` | `refuse_if_sandbox` + `require_shared_list_tasks` + `require_claim_flag_allowed` | `SharedListCreate` → 201 `SharedListDetail` |
| POST `/events/{event_id}/shared-lists/bulk` | `bulk_update_shared_lists` | per row `require_shared_list_manager(action)` | `SharedListBulkRequest` → `SharedListBulkResult` (partial success, the events.py:1700-1775 precedent) |
| POST `/events/{event_id}/shared-lists/pause-all` | `pause_all_shared_lists` | `require_event_role(minimum="admin")` after the sandbox test | `SharedListPauseAllRequest {lock_managers: bool = False}` → `SharedListBulkResult` |
| GET `/shared-lists/{list_id}` | `get_shared_list` | `require_shared_list_visible` | → `SharedListDetail` |
| PATCH `/shared-lists/{list_id}` | `update_shared_list` | `require_shared_list_manager("edit")` + `require_shared_list_tasks` (for new task ids) + `require_claim_flag_allowed` | `SharedListUpdate` → `SharedListDetail` |
| POST `/shared-lists/{list_id}/pause` | `pause_shared_list` | `require_shared_list_manager("pause")` | → `SharedListDetail` |
| POST `/shared-lists/{list_id}/resume` | `resume_shared_list` | `require_shared_list_manager("resume")` | → `SharedListDetail` |
| POST `/shared-lists/{list_id}/end` | `end_shared_list` | `require_shared_list_manager("end")` | → `SharedListDetail` |
| POST `/shared-lists/{list_id}/rotate` | `rotate_shared_list` | `require_shared_list_manager("rotate")` | → `SharedListDetail` |

`managers_share_lists` (D18) is read and written through the existing `GET/PATCH
/events/{event_id}` (`EventRead`/`EventUpdate`, admin-only like the other
`_NOT_NULL_SETTINGS`), not through a new route.

Schemas (`app/schemas/shared_list.py`):

```python
EffectiveStatus = Literal["live", "paused", "expired", "ended"]
SharedListAccess = Literal["admin", "manager", "viewer"]

class SharedListTaskRef(BaseModel): id: UUID; name: str

class SharedListIssue(BaseModel):
    kind: Literal["stranded", "expires_soon"]
    free: int                         # stranded: free places in no live list; expires_soon: all free
    task_names: list[str]             # de-duplicated, ordered as on the list
    days_left: int | None = None      # expires_soon only (0 = today)

class SharedListRow(BaseModel):
    id: UUID; code: str; title: str; share_note: str | None
    status: Literal["live","paused","ended"]; effective_status: EffectiveStatus
    ends_mode: Literal["last_shift","date","manual"]; ends_on: date | None
    closes_at: datetime | None        # event wall clock, naive
    expires_soon: bool; is_full: bool
    created_at: datetime; created_by_name: str | None
    tasks: list[SharedListTaskRef]
    only_days: list[date] | None      # non-null iff some date of the list's tasks is fully excluded
    excluded_shift_count: int
    capacity: int; free: int          # over included, not-started shifts
    signup_count: int                 # confirmed bookings with this shared_list_id
    guest_count: int                  # ... whose user is still a list guest
    view_count: int
    issue: SharedListIssue | None     # only when access in (admin, manager) and not ended
    access: SharedListAccess

class SharedListCounts(BaseModel): active: int; todo: int; live: int; paused: int; ended: int
class SharedListListResponse(BaseModel):
    items: list[SharedListRow]; total: int; skip: int; limit: int
    counts: SharedListCounts          # over every visible list, ignoring q (prototype)
    ended_matching: int               # ended lists matching q; for "N beendete ... ausgeblendet"

class SharedListSummary(BaseModel): live_lists: int; signups: int; guests: int; free_in_live: int
class UnsharedNotice(BaseModel): task_count: int; free: int; task_names: list[str]  # first 2
class SharedListOverview(BaseModel):
    summary: SharedListSummary; unshared: UnsharedNotice
    can_create: bool                  # admin, or managers_share_lists and >=1 shareable managed task
    can_pause_all: bool               # admin and summary.live_lists > 0
    is_admin: bool                    # shows the D18 switch and the claim option
    managers_share_lists: bool        # D18
    event_timezone: str

class SharedListChip(BaseModel): id: UUID; title: str; effective_status: EffectiveStatus
class TeamRef(BaseModel): id: UUID; name: str
class SharedListTaskRow(BaseModel):
    id: UUID; name: str; location: str | None; manager_names: list[str]
    shift_count: int; dates: list[date]   # not-started shifts only
    capacity: int; free: int
    team: TeamRef | None              # team-locked → never shareable
    lists: list[SharedListChip]       # non-ended visible lists containing it
    ended_list_count: int
    stranded_free: int                # free, not-started, in no live list
    unlisted_free: int                # stranded and also in no paused/expired list
    can_share: bool
class SharedListTaskCounts(BaseModel): all: int; todo: int
class SharedListTaskListResponse(BaseModel):
    items: list[SharedListTaskRow]; total: int; skip: int; limit: int; counts: SharedListTaskCounts

class SharedListCandidate(BaseModel):
    id: UUID; name: str; location: str | None; manager_names: list[str]
    shift_count: int; dates: list[date]; capacity: int; free: int
    team: TeamRef | None; earns_vouchers: bool
class SharedListCandidateListResponse(BaseModel):
    items: list[SharedListCandidate]; total: int; skip: int; limit: int
    locked_count: int; locked_names: list[str]   # team-locked, first 3, for the hint without q
    # team-locked rows appear in items only when q is non-empty (prototype)

class SharedListCandidateShift(BaseModel):
    id: UUID; task_id: UUID; date: date; start_time: time | None; end_time: time | None
    capacity: int; free: int

class SharedListCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)          # stripped
    intro: str | None = Field(None, max_length=1000)
    share_note: str | None = Field(None, max_length=120)
    task_ids: list[UUID] = Field(min_length=1, max_length=50)  # order = position
    excluded_shift_ids: list[UUID] = Field(default_factory=list, max_length=2000)
    ask_email: Literal["required","optional","off"] = "required"
    ask_phone: Literal["required","optional","off"] = "off"
    show_names: Literal["none","first"] = "none"
    max_per_person: int | None = Field(None, ge=1, le=50)      # None = unlimited (default)
    ends_mode: Literal["last_shift","date","manual"] = "last_shift"
    ends_on: date | None = None
    claim_grants_membership: bool = False                      # D4; true only for event admins
class SharedListUpdate(BaseModel): ...every field above optional; model_dump(exclude_unset=True)
    # show_names changes apply to new sign-ups only (D12)

class SharedListDetailTask(BaseModel):
    id: UUID; name: str; offered: bool
    not_offered_reason: Literal["team_locked","not_published","moved"] | None
    shift_count: int; capacity: int; free: int; only_days: list[date] | None
class SharedListDetail(SharedListRow):
    intro: str | None; ask_email: ...; ask_phone: ...; show_names: ...; max_per_person: int | None
    claim_grants_membership: bool
    rotated_at: datetime | None; paused_at: datetime | None; ended_at: datetime | None
    task_ids: list[UUID]; excluded_shift_ids: list[UUID]
    detail_tasks: list[SharedListDetailTask]
    event: SharedListEventRef          # id, name, start_date, end_date, timezone

class SharedListBulkRequest(BaseModel):
    action: Literal["pause","resume","end"]; list_ids: list[UUID] = Field(min_length=1, max_length=100)
class SharedListBulkSkip(BaseModel): id: UUID; code: str   # error code, e.g. "shared_list.ended"
class SharedListBulkResult(BaseModel): changed: list[UUID]; skipped: list[SharedListBulkSkip]
class SharedListPauseAllRequest(BaseModel): lock_managers: bool = False   # D18
```

Rules for create and update, all in `logic/shared_lists/manage.py::validate_selection`:

- every task is in the event, else 422 `shared_list.task_not_in_event` `{task_ids}`;
- published, else 422 `shared_list.task_not_published` `{task_ids}`;
- not team-locked, else 422 `shared_list.task_team_locked` `{task_ids}`;
- excluded ids are **filtered by `Shift.task_id ∈ task_ids`**, and unknown or foreign
  ids are silently dropped (fixes prototype flaw 15);
- at least one included, not-started shift, else 422 `shared_list.no_shifts`;
- at least one free place, else 422 `shared_list.no_free_places`;
- `ends_on` per §4.2;
- event published, else 409 `shared_list.event_not_published`;
- at most 200 lists per event, else 409 `shared_list.too_many` `{max}`;
- the code is generated with up to 5 retries on a unique violation;
- `created_by_id` and `created_by_name` come from the current user;
- `claim_grants_membership=true` only from an event admin (`require_claim_flag_allowed`,
  D4); a PATCH that leaves the field out keeps it.

Bulk:

- takes `FOR UPDATE` on every row in id order;
- checks `require_shared_list_manager(user, session, sl, action)` and applies
  `transition` per row;
- records refusals in `skipped`, never failing the batch;
- unknown or invisible ids → `shared_list.not_found`.

Aggregate queries for the lists, tasks and overview endpoints live in
`app/crud/shared_list_overview.py` (WP2), a fixed number of queries per request:

1. lists of the event with their task ids;
2. excluded ids;
3. included, not-started shifts of every listed task, with `confirmed` per shift
   (GROUP BY);
4. per-list confirmed and guest sign-up counts (`bookings.shared_list_id`, joined to
   `users.is_list_guest`);
5. for the tasks tab: the published tasks of the event that have not-started shifts,
   with managers (`crud_task_manager.managers_for_tasks`) and teams.

The Python pass then computes, per list:

- included shifts;
- `last_start`;
- the effective status;
- `free` and `capacity`;
- the set of shifts in any effective-live list;
- stranded and unlisted places;
- the issue (only for lists the viewer may manage);
- the filter counts.

Finally it filters by viewer scope and `status_filter`, matches `q` (casefold
substring over title, share_note, created_by_name and task names), sorts, and slices.

### 6.2 Guest data for organisers and the operator: `app/api/routes/shared_list_guests.py` (WP3), schemas in `app/schemas/shared_list_guest.py`

| Method and path | Function | Gate | Request → response |
|---|---|---|---|
| GET `/shared-lists/{list_id}/signups` | `list_shared_list_signups` | `require_shared_list_visible` | `sort_by: Literal["created_at","name","shift_start"]="created_at"`, `sort_dir` (default desc for created_at, asc otherwise), `q` (name, and email on rows the viewer may see in full), skip, limit → `SharedListSignupListResponse` |
| POST `/shared-lists/{list_id}/signups/remove` | `remove_shared_list_signups` | §4.10 | `SharedListSignupRemoveRequest` → `SharedListSignupRemoveResult` |
| GET `/shared-lists/{list_id}/preview` | `preview_shared_list` | `require_shared_list_visible` | → `PublicSharedList` (no view count; same builder as the public GET) |
| GET `/list-guests` | `search_list_guests` | `CurrentSuperuser` | `q` (required, 3..100: exact normalised email, or ILIKE on name or phone), skip, limit → `ListGuestAdminListResponse` |
| GET `/list-guests/{guest_user_id}` | `export_list_guest` | `CurrentSuperuser` | → `ListGuestExport` (Art. 15 export: everything stored about the guest) |
| POST `/list-guests/{guest_user_id}/erase` | `erase_list_guest` | `CurrentSuperuser` | → 204, `erase_guest` (§4.9) |
| POST `/list-guests/mail-suppressions/lift` | `lift_mail_suppression` | `CurrentSuperuser` | `{email}` → 204, or 404 `guest_signup.not_suppressed`: mail the address again after "Das war ich nicht" |

The `/list-guests` routes are how the operator answers a data-subject request sent to
`LEGAL_EMAIL` (§9). Guests are absent from the admin user search (§4.12) and their
address is not in `users.email`, so without them the operator could not find a guest.
v1 ships no UI for them; docs/SHARED_LISTS.md shows the calls. They live under
`/list-guests`, not `/users/…`, because of the `GET /users/{user_id}` catch-all.

```python
class SharedListSignup(BaseModel):
    booking_id: UUID; name: str | None; is_guest: bool; erased: bool
    email: str | None; phone: str | None           # only when caller manages the booking's task
    task_id: UUID; task_name: str; shift_id: UUID
    shift_date: date; start_time: time | None; end_time: time | None
    created_at: datetime; possible_duplicate: bool; can_remove: bool
class SharedListSignupListResponse(BaseModel):
    items: list[SharedListSignup]; total: int; skip: int; limit: int
    hidden_count: int        # confirmed sign-ups on tasks the caller does not manage
    can_erase: bool          # caller is an event admin (§4.10 erase)

class SharedListSignupRemoveRequest(BaseModel):
    booking_ids: list[UUID] | None = Field(None, min_length=1, max_length=100)
    created_since: datetime | None = None          # naive UTC; exactly one selector
    notify: bool = True
    erase: bool = False                            # event admins only
class SharedListSignupRemoveResult(BaseModel):
    removed: list[UUID]; erased_guests: int; skipped: list[SharedListSignupSkip]
class SharedListSignupSkip(BaseModel): id: UUID; code: str   # same shape as WP2's SharedListBulkSkip

class ListGuestAdminRow(BaseModel):
    guest_user_id: UUID; name: str | None; email: str | None; phone: str | None
    event_id: UUID | None; event_name: str | None; booking_count: int
    last_signup_at: datetime | None; erased: bool
class ListGuestAdminListResponse(BaseModel):
    items: list[ListGuestAdminRow]; total: int; skip: int; limit: int
class ListGuestExport(ListGuestAdminRow):
    preferred_language: str; show_first_name: bool
    bookings: list[GuestSignupBooking]             # §6.3
```

The query covers confirmed bookings with `shared_list_id = list_id`, joined to
`users` and outer-joined to `shared_list_guests`, `shifts` and `tasks`, restricted to
the managed task ids for viewers and managers. It is plain SQL ORDER BY / OFFSET /
LIMIT, with `shift_start` meaning `Shift.date, Shift.start_time NULLS FIRST`.
`possible_duplicate` is a window `count(*) OVER (PARTITION BY shift_id,
lower(users.name)) > 1` over guest rows.

### 6.3 Public and guest: `app/api/routes/public_shared_lists.py` (WP3), schemas in `app/schemas/public_shared_list.py`

No identity dependency is used. Only `DBDep` and `Request`.

| Method and path | Function | Notes |
|---|---|---|
| GET `/public/shared-lists/{code}` | `get_public_shared_list` | `shared_list_view_limiter(ip)`; miss → `shared_list_miss_limiter(ip)` then 404 |
| POST `/public/shared-lists/{code}/signups` | `sign_up_on_shared_list` | §4.7; 201 |

Only these two answer `shared_list.disabled` while the kill switch is off. The
`/guest-signups/*` routes stay up, as `/list-guests` does: the guests already signed
up still get mail about their shifts, and every mail links here.
| POST `/public/guest-signups/manage` | `read_guest_signups` | body `{token}` |
| POST `/public/guest-signups/cancel` | `cancel_guest_signup` | body `{token, booking_id}` → `GuestSignupManage` |
| POST `/public/guest-signups/reminders` | `set_guest_reminders` | body `{token, enabled}` → `GuestSignupManage` |
| POST `/public/guest-signups/erase` | `erase_guest_data` | body `{token}` → 204 |
| POST `/public/guest-signups/not-me` | `reject_guest_signup` | body `{token}` → 204; erase + suppress (§4.9, D17). Only the token from a mail (`guest_tokens.mail_token`, a key of its own): the sign-up's `guest_token` is 403 `guest_signup.mail_link_required`, since whoever typed an address holds it |

```python
class PublicShift(BaseModel):
    id: UUID; task_id: UUID; task_name: str; location: str | None
    start_time: time | None; end_time: time | None
    capacity: int; free: int; full: bool
    names: list[str] = []; others_count: int = 0     # only when show_names == "first"
class PublicDay(BaseModel): date: date; shifts: list[PublicShift]
class PublicEventRef(BaseModel): name: str; start_date: date; end_date: date; timezone: str
class PublicSharedList(BaseModel):
    code: str; title: str; intro: str | None         # plain text; never rendered as HTML
    status: Literal["live", "paused", "closed"]      # expired + ended → closed
    event: PublicEventRef
    ask_email: AskMode; ask_phone: AskMode; show_names: ShowNames; max_per_person: int | None
    claimable: bool                                  # claim_grants_membership; drives the upsell
    days: list[PublicDay]                            # [] unless live

class PublicSignupRequest(BaseModel):
    shift_id: UUID
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=30)
    remind: bool = False
    language: Literal["en", "de"] = "de"
    show_names: ShowNames    # what the form showed; named only if "first" and the list still says so
    guest_token: str | None = Field(None, max_length=128)
    turnstile_token: str | None = None
class PublicSignupResult(BaseModel):
    booking_id: UUID; guest_id: UUID; guest_token: str
    shift: PublicShift; date: date
    email: str | None
    mail_queued: bool        # False for follow-ups, suppressed or capped addresses, no SMTP
    show_manage_link: bool   # first sign-up of a chain and not mail_queued: the done page shows the link (§7.5)
    remaining: int | None

class GuestSignupBooking(BaseModel):
    booking_id: UUID; status: Literal["confirmed","cancelled"]
    event_name: str | None   # per booking: a moved task takes it to another event
    task_name: str; date: date; start_time: time | None; end_time: time | None
    location: str | None; can_cancel: bool; reminder_on: bool
class GuestSignupManage(BaseModel):
    name: str | None; email: str | None; event: PublicEventRef   # the list's event
    bookings: list[GuestSignupBooking]; can_set_reminders: bool
    can_reject: bool         # opened with a mail's token: offer "Das war ich nicht"
```

### 6.4 Claim: `app/api/routes/guest_claims.py` (WP3), tag `guest-claims`

| Method and path | Function | Gate | Response |
|---|---|---|---|
| GET `/guest-claims` | `list_guest_claims` | `CurrentUser` + verified | `GuestClaimList {items: [{guest_id, event: {id, name}, bookings: list[GuestSignupBooking]}]}`, claimable guests only (D4) |
| POST `/guest-claims` | `claim_guest_signups` | `CurrentUser` + verified | body `{guest_ids: list[UUID] (1..50)}` → `GuestClaimResult {claimed_bookings: int, skipped_duplicates: int, event_ids: list[UUID], not_found: list[UUID]}` |

Plus `UserProfile.claimable_guest_signups: int = 0` (schemas/users.py:32, filled in
`build_user_profile`), counting claimable guests only.

### 6.5 Error codes (complete list; WP5 adds every one to `src/locales/{en,de}/errorCodes.json`)

| Code | Status | Extensions |
|---|---|---|
| `shared_list.not_found` | 404 | |
| `shared_list.disabled` | 404 | |
| `shared_list.forbidden` | 403 | |
| `shared_list.tasks_forbidden` | 403 | `task_ids` |
| `shared_list.task_team_locked` | 422 | `task_ids` |
| `shared_list.task_not_published` | 422 | `task_ids` |
| `shared_list.task_not_in_event` | 422 | `task_ids` |
| `shared_list.no_shifts` | 422 | |
| `shared_list.no_free_places` | 422 | |
| `shared_list.ends_on_invalid` | 422 | `last_shift_date` |
| `shared_list.event_not_published` | 409 | |
| `shared_list.too_many` | 409 | `max` |
| `shared_list.ended` | 409 | |
| `shared_list.not_live` | 409 | |
| `shared_list.nothing_to_offer` | 409 | |
| `shared_list.paused` | 409 | |
| `shared_list.closed` | 409 | |
| `shared_list.shift_not_offered` | 404 | |
| `shared_list.shift_started` | 409 | |
| `shared_list.already_signed_up` | 409 | |
| `shared_list.max_per_person` | 409 | `max` |
| `shared_list.email_required` | 422 | |
| `shared_list.phone_required` | 422 | |
| `shared_list.guest_token_invalid` | 403 | |
| `shared_list.too_many_for_address` | 429 | |
| `shared_list.daily_limit` | 429 | |
| `shared_list.rate_limited` | 429 | `Retry-After` header |
| `shared_list.signup_not_found` | 404 | (also a `skipped` code in §4.10) |
| `shared_list.signup_not_guest` | 409 | (also a `skipped` code in §4.10) |
| `shared_list.remove_selector` | 422 | |
| `shared_list.managers_disabled` | 403 | |
| `shared_list.claim_admin_only` | 403 | |
| `guest_signup.not_found` | 404 | |
| `guest_signup.no_email` | 409 | |
| `guest_signup.mail_link_required` | 403 | |
| `guest_signup.not_suppressed` | 404 | |
| `guest_signup.rate_limited` | 429 | |
| `guest_claim.email_unverified` | 403 | |
| `auth.guest_account` | 403 | |
| `sandbox.shared_lists_disabled` | 403 | |

Reused codes: `booking.slot_full`, `booking.time_conflict`, `booking.shift_over`,
`auth.captcha_failed` (already translated), `event.not_found`.

The public form maps `booking.slot_full` to "Diese Schicht ist gerade voll geworden.
Such dir bitte eine andere aus." in `guestSignup.json`, instead of the generic member
text.

---

## 7. Frontend

### 7.1 Routes (WP5 owns `src/router/routes.ts`, `src/router/index.ts`)

```ts
// postauth-layout children (no requiresEventManager: people in charge use it; the
// view checks canManageEvent(id) || event.managed_task_count > 0, task-edit precedent)
{ path: 'shared-lists/:eventId?', name: 'shared-lists',
  component: () => import('@/views/shared-lists/SharedListsView.vue'),
  meta: { routerViewKey: 'shared-lists',
          breadcrumbs: [{ title: 'Shared lists', titleKey: 'navigation.sidebar.items.sharedLists' }] } },
{ path: 'shared-lists/:eventId/new', name: 'shared-list-create',
  component: () => import('@/views/shared-lists/SharedListWizardView.vue'), meta: { … } },
{ path: 'shared-lists/:eventId/:listId/edit', name: 'shared-list-edit',
  component: () => import('@/views/shared-lists/SharedListWizardView.vue'), meta: { … } },
// the claim page (D4): reachable without a selected event, which a fresh account lacks
{ path: 'guest-claims', name: 'guest-claims',
  component: () => import('@/views/guest/GuestClaimsView.vue'),
  meta: { breadcrumbs: [{ title: 'Sign-ups without an account', titleKey: 'navigation.breadcrumbs.guestClaims' }] } },

// top level, before the catch-all; parents unnamed, not under preauth-layout
// (that would add /de/l/:code, the sign-in header, and URL-rewriting language switches)
{ path: '/l', component: () => import('@/layout/GuestLayout.vue'),
  children: [{ path: ':code', name: 'shared-list-public',
    component: () => import('@/views/guest/SharedListPublicView.vue'),
    meta: { noindex: true, titleKey: 'guestSignup.page.title' } }] },
{ path: '/guest-signup', component: () => import('@/layout/GuestLayout.vue'),
  children: [{ path: '', name: 'guest-signup-manage',
    component: () => import('@/views/guest/GuestSignupManageView.vue'),
    meta: { noindex: true, titleKey: 'guestSignup.manage.title' } }] },
```

The management page keeps its state in the query:
`?tab=links|tasks|preview&filter=&q=&sort=&dir=&page=&list=<id>`. `list` opens the
detail dialog. The fixed `routerViewKey` stops a remount on every query change.

The wizard reads:

- `?from=<listId>` for "Neu teilen" (duplicate);
- `?tasks=<id,id>` for preselected tasks from the Aufgaben tab.

`router/index.ts`:

- Add `'shared-lists'`, `'shared-list-create'`, `'shared-list-edit'`,
  `'shared-list-public'`, `'guest-signup-manage'` and `'guest-claims'` to
  `SELECTED_EVENT_EXEMPT_ROUTES` (l.47-81). The management routes are exempt so
  sign-ups stay readable after the event, like `my-vouchers`. `guest-claims` is
  exempt because the guard sends an account without a selected event to
  `select-event?mode=onboarding` (l.164-173), and a fresh account that comes from the
  guest upsell has none until the claim gives it one.
- Exempt the two guest routes from the suspended/pending redirect (l.138-148) through
  a new `GUEST_ROUTES` set. A link from a group chat must open whatever state the
  visitor's own account is in.
- Do not add any of them to `SIGNED_IN_REDIRECT_ROUTES`.
- Declare `noindex?: boolean` and `titleKey?: string` in `RouteMeta`
  (routes.ts:12-32), and also declare the already-used `routerViewKey`.

`src/lib/page-head.ts` (WP5):

- `applyHead` sets `document.title = i18n.t(route.meta.titleKey)` when it is present,
  so it survives the locale watcher (l.68-71).
- It adds or removes `<meta name="robots" content="noindex, nofollow">` per
  `route.meta.noindex`.
- Covered by `src/lib/__tests__/page-head.spec.ts` (coverage gate).

### 7.2 Shared table kit (WP5; reused by WP6, WP7, and later by any list view)

`src/components/data-table/`:

- `ListPagination.vue`
  - Props `page`, `total`, `pageSize`; emits `update:page`.
  - Wraps the reka `Pagination*` parts. Every visible label is translated through slots
    (`common.pagination.first/previous/next/last/morePages`), because
    `ui/pagination/Pagination{First,Previous,Next,Last}.vue` and
    `PaginationEllipsis.vue` hard-code English. Do **not** hand-edit `components/ui`.
  - WP5 also replaces the three copy-pasted blocks in `views/admin/UsersView.vue:398-434`
    and `views/admin/AdminEventsView.vue:346-380,454-490`.
- `SortableHead.vue`
  - Props `label`, `sortKey`, `activeKey`, `dir`, `defaultDir`; emits `sort(key)`.
  - Renders a `<button>` inside `TableHead` with an arrow icon, and puts `aria-sort`
    (`ascending | descending | none`) on the `<th>`.
- `SelectionBar.vue`
  - A sticky `role="region"` with an aria-label ("Auswahl"), the "{n} ausgewählt"
    count, a default slot for actions, and "Abwählen".
  - `fixed inset-x-4 bottom-20 md:bottom-4 z-40`, so it clears `MobileBottomNav`
    (FAB precedent `bottom-24 md:bottom-6`).
  - Optional inline confirm slot with `role="alert"`.
- `FilterChips.vue`
  - `role="group"`, `aria-label`, buttons with `aria-pressed`, a count span, and
    variant `warning` for "Zu tun".
  - The precedent `UsersView.vue:355-366` lacks `aria-pressed`.
  - It scrolls sideways on phones.
- `SearchField.vue`: a search icon, `Input type="search"`, a clear button
  (`aria-label=common.actions.reset`), `h-11 sm:h-9`; emits a debounced value (300 ms).
- `FillBar.vue`: `role="progressbar"`, `aria-valuenow/min/max`, `aria-valuetext`
  ("{free} von {cap} frei"). Classes follow `ReportingTaskFillRates.vue:43-47,78-83`
  (full, partial or short).

Composables, each with a spec, because the coverage gate applies:

- `src/composables/useTableQuery.ts` syncs `page/sort/dir/q/filter` with
  `route.query` through `router.replace` (the TasksView.vue:101-123 pattern). It
  resets `page` to 1 on filter, search or sort changes, and exposes `params` for the
  API.
- `src/composables/useRowSelection.ts` keeps an immutable `Set<string>`, toggles,
  computes `headerState: boolean | 'indeterminate'` for the current page's selectable
  ids, and **clears itself whenever the page, filter, search or sort changes**. That
  fixes prototype flaw 4. The precedent is EventCloneView.vue:269-295.

`src/lib/shared-lists.ts` (WP5, with a spec):

- `sharedListUrl(code, origin = window.location.origin)`;
- `effectiveStatusBadge(status)`, giving variant and i18n key: live is `default` with
  a pulsing dot (static under `motion-reduce`), paused is `warning`, expired and
  ended are `outline`;
- `fillLevel(free, cap)`;
- `askedFieldKeys(askEmail, askPhone)`;
- `endsSummary(detail)`, giving an i18n key and params;
- `relativeSignupTime(createdAt, now)`, giving "gerade eben / heute / gestern / vor N
  Tagen", with `parseServerDate` for the naive UTC value.

`src/composables/useAuthenticatedClient.ts`: add `/shared-lists` to
`SIDEBAR_IGNORED_PATH` (l.9-15). Otherwise every pause refetches the sidebar
(`/events/{id}/shared-lists` matches the `/(…|events)/` rule).

`frontend/e2e/helpers/api.ts` (WP5) gets three helpers:

- `createSharedList(email, eventId, body)`;
- `publicSignup(code, body)`, an anonymous `serverApiRaw`;
- `getSharedList(email, id)`.

### 7.3 Management page (WP6): `src/views/shared-lists/SharedListsView.vue`

- **Header**:
  - title, and the prototype's lede;
  - a primary "Liste teilen" button. It is disabled with a `HintTooltip` when
    `overview.can_create` is false, and navigates to `shared-list-create`.
- **Tabs**: `Tabs` with `?tab=` sync (EventSettingsView.vue:49-75 pattern).
  - "Links" carries a count of non-ended visible lists in a badge.
  - The other tabs are "Aufgaben" and "So sehen es Helfende".
- **Phone versus desktop**: **one** DOM branch through `useMediaQuery('(min-width:
  768px)')`, the same line as `RESPONSIVE_DIALOG_MOBILE_QUERY`. Do not use CSS
  `hidden sm:block` pairs, which duplicate `data-testid`.

Components in `src/components/shared-lists/`:

- `SharedListSummaryBar.vue`: the four figures from `overview.summary`.
- `UnsharedTasksNotice.vue`: the prototype text with "und N weitere", and a CTA that
  sets `tab=tasks&filter=todo` and clears `q`.
- **Links tab**:
  - `FilterChips` (Aktiv default, Zu tun, Offen, Pausiert, Beendet; counts from
    `counts`) and a `SearchField` ("Titel, Gruppe, Aufgabe…").
  - "Alle pausieren", only when `overview.can_pause_all`, with an inline confirm using
    the prototype text and a checkbox "Verantwortliche können die Listen nicht wieder
    öffnen" (`lock_managers`, D18), then `pause-all`.
  - For event admins (`overview.is_admin`), a `Switch` "Verantwortliche dürfen Listen
    für ihre Aufgaben teilen" bound to `managers_share_lists`, saved with `PATCH
    /events/{id}` (`SharedListManagersSwitch.vue`). When it is off, people in charge
    see a short note instead of "Liste teilen".
  - `SharedListsTable.vue` (desktop) has these columns:
    - [checkbox];
    - Status (sortable `status`);
    - Liste (sortable `title`): title, pills "läuft … ab" or "alles besetzt", the meta
      "{share_note || Nicht angegeben, wo geteilt} · von {created_by_name}", task chips
      and the "nur …" day chip;
    - Plätze (sortable `free`, `FillBar`);
    - Eingetragen (sortable `signups`);
    - Offen bis (sortable `closes`);
    - actions.
  - Rows with an issue get a warning border and render `SharedListIssueStrip.vue`
    below, with the CTA "Fortsetzen", "Wieder öffnen" or "Verlängern". "Verlängern"
    is a PATCH with `ends_mode=last_shift, ends_on=null`.
  - `SharedListsCardList.vue` (phone): the same data as cards. A ⋯ `DropdownMenu`
    replaces the icon buttons (`useMenuAction`; user memory: real mobile patterns), and
    a "Sortieren" select replaces the headers.
  - `SharedListRowActions.vue`: copy link (disabled when ended), pause or resume
    (disabled when `access !== 'admin' && access !== 'manager'`), and details. Icon
    buttons sit in `HintTooltip` with their own `aria-label`.
  - Copying follows `EventInvitations.vue:59-61,129-142`: `navigator.clipboard`, then
    a toast and a check icon for 2 s. On failure, `toast.info(url)`.
  - The checkbox is disabled for ended rows and for rows without manage access.
    Header tri-state comes from `useRowSelection`.
  - `SelectionBar` actions: Pausieren (enabled if any selected row is live), Fortsetzen
    (any paused or expired), Beenden (an inline danger confirm with **singular and
    plural** text, fixing flaw 3). Each calls `bulk` and toasts `changed.length`. If
    any rows were skipped, a warning toast lists the count.
  - Empty states (prototype 4.6), plus the "{n} beendete Listen sind ausgeblendet ·
    Anzeigen" line from `ended_matching`.
  - `ListPagination` at 20 per page.
- **Aufgaben tab**:
  - `FilterChips` (Alle, Zu tun) and `SearchField` ("Aufgabe, Ort, Person…").
  - `SharedListTasksTable.vue` and `SharedListTasksCardList.vue` with the columns:
    - [checkbox, disabled when `!can_share`];
    - Aufgabe (sortable `name`): name, "{n} Schichten · {days} · {location}",
      "Verantwortlich: …", and the team-lock sentence;
    - Plätze (sortable `free`);
    - Geteilt in (sortable `unlisted_free`): `TaskSharedInCell.vue` renders chips
      (status dot, opens the detail), "In keiner Liste", "· {n} beendet", or the
      warning "{n} freie Plätze in keiner offenen Liste" with "Teilen". Team-locked
      tasks show "Nur übers Team".
  - Day text: `formatDaySpan` when the dates are contiguous, otherwise weekday
    abbreviations. It is not tied to three-day events (flaw 10).
  - `SelectionBar`: "{n} Aufgaben · {free} Plätze frei", then "Teilen" or "Als eine
    Liste teilen", which goes to `shared-list-create?tasks=…`.
- **Vorschau tab**:
  - a `Select` of visible lists, the facts list (prototype §6), and
    `components/guest/PublicListPreview.vue` (owned by WP8, read-only, fed by
    `GET /shared-lists/{id}/preview`);
  - "Link öffnen" opens `/l/<code>` in a new tab;
  - the copy says that sign-ups through the real link are real and can be removed in
    the detail dialog.
- **Detail dialog** `SharedListDetailDialog.vue` (`ResponsiveDialog`; the
  `EventVouchers.vue:417-483` pattern: clear, open, load):
  - Header: status pill, title, and "{share_note} · erstellt von {name} am {date}".
  - The lock note when `access === 'viewer'`.
  - When not ended:
    - the link box with copy, a QR toggle (`aria-expanded`), and preview (switches to
      the Vorschau tab with this list);
    - `SharedListQrCode.vue`, which uses `components/print/QrCode.vue` on a white tile
      (`VoucherCodeDialog.vue:281-292`) with a "PNG speichern" button (`QRCode.toDataURL`
      plus `<a download>`).
  - Key figures: eingetragen, ohne Konto, Plätze frei, geöffnet {view_count}×.
  - "Was in der Liste steht": `detail_tasks`, with a warning line for tasks that are
    not offered.
  - **Sign-ups**: `SharedListSignupsTable.vue` / card list.
    - Sortable (`created_at` default desc, `name`, `shift_start`), searchable,
      paginated at 10 per page, using `useTableQuery` with a `signups` prefix.
    - Shows the "ohne Konto" tag and the "möglicherweise doppelt" tag.
    - The contact line appears when the API returns it.
    - Removal goes through `POST …/signups/remove` (§4.10) in every form, from one
      `SharedListRemoveSignupsDialog.vue` (`ResponsiveDialog`) that states what will
      happen and has a "Per Mail Bescheid geben" checkbox (`notify`, on by default)
      and, when `can_erase`, "Auch die Daten dieser Person löschen" (`erase`):
      - the row action "Austragen" (one booking);
      - row checkboxes with `useRowSelection` and a `SelectionBar` "Austragen";
      - the row menu item "Diese und alle neueren austragen" (`created_since` = the
        row's `created_at`), for cleaning up a wave of fake sign-ups.
      The toast reports `removed.length`, and a warning toast the `skipped` count.
    - The `hidden_count` line reads "{n} weitere bei Aufgaben anderer Verantwortlicher".
  - The settings summary uses `lib/shared-lists.ts` helpers.
  - Footer when access is admin or manager:
    - when ended: "Neu teilen", which goes to `shared-list-create?from=<id>`;
    - otherwise: Pausieren or Fortsetzen / Wieder öffnen, Bearbeiten, Neuer Link, and
      Beenden.
    - "Neuer Link" opens `confirm` with the prototype text plus "Gedruckte QR-Codes
      führen dann auch nicht mehr hierher."
    - "Beenden" opens `confirmDestructive`.
  - Any `DropdownMenuItem` that opens a dialog uses `useMenuAction()`
    (`menu.after(...)`, `@close-auto-focus="menu.onCloseAutoFocus"`; frontend/CLAUDE.md).
- **Store** `src/stores/sharedLists.ts` (spec required):
  - actions `fetchOverview`, `fetchLists(params)`, `fetchTasks(params)`,
    `fetchDetail(id)`, `pause/resume/end/rotate(id)`, `bulk(action, ids)`,
    `pauseAll(eventId, lockManagers)`, `setManagersShareLists(eventId, value)`,
    `fetchSignups(id, params)`, `removeSignups(id, body)`, `fetchPreview(id)`;
  - it holds the last page per tab and the open detail;
  - it uses `useAuthenticatedClient` (mocked in the spec).
- **"ohne Konto" in existing views** (WP6 owns these edits):
  - `components/tasks/ShiftRoster.vue` (74-117), `ShiftBookingsTable.vue` (40-95),
    `ShiftDetailDialog.vue`, `views/bookings/BookingDetailView.vue` (co-bookers card,
    522) and `components/events/EventHours.vue` show a small `Badge variant="outline"`
    from `is_guest`;
  - an erased guest name renders as `sharedLists.guest.erased`.

### 7.4 Wizard (WP7): `src/views/shared-lists/SharedListWizardView.vue`

Modelled on `views/events/EventCloneView.vue`:

- the `sections` tuple, `visitedSections`, a `sectionValid` map, `isStepReachable`,
  and `stepBlockedReason`;
- `focusStepHeading()` on every step change (`CardTitle tabindex="-1"`,
  `data-testid="wizard-step-heading"`);
- `<Stepper :linear="false">`, with titles hidden below `sm`;
- the footer: Back, a translated `role="status" aria-live="polite"` "Schritt x von y",
  and Next or submit.

Steps:

- Create: Aufgaben → Einstellungen → Teilen.
- Edit: Aufgaben → Einstellungen. Every step is reachable on edit.

Behaviour:

- Blockers are shown only after the user has interacted or pressed Next. This fixes
  flaw 13. Next stays disabled and points at the reason with `aria-describedby`.
- **Unsaved-changes guard**: `onBeforeRouteLeave` with `useDialog().confirm` while the
  draft is dirty and not yet saved. It is new to the app.
- Access: the view redirects (with a toast) unless
  `authStore.canManageEvent(eventId) || selectedEvent.managed_task_count > 0`. The
  server enforces the same.

**Step 1, "Was in die Liste kommt"** (`components/shared-lists/wizard/`):

- `WizardTaskPicker.vue`:
  - `SearchField` with server search (`/candidates?q=`) and "Mehr laden" (limit 50);
  - picked chips ("{n} ausgewählt:", each with an × labelled "{name} abwählen");
  - candidate rows showing "{free} von {cap} Plätzen frei · {days}";
  - team-locked rows appear only while searching, disabled, with "Nur für das Team
    „{team}“, geht nicht ohne Konto";
  - without a search, the locked hint from `locked_count` and `locked_names`;
  - a voucher hint on `earns_vouchers` rows ("Wer sich ohne Konto einträgt, bekommt
    keine Marken");
  - per selected task with more than one shift, "Einzelne Schichten abwählen"
    (`aria-expanded`) lists **all** not-started shifts of the task grouped by day, not
    only those on checked days. This fixes the prototype's `draftDayShifts`.
- `WizardDayCards.vue`: one card per date that has shifts of the selected tasks. Each
  card has a tri-state `Checkbox` and the label "{Sa 6.12.}" with "{n von m Schichten}
  · {free} frei", or "alles voll" in warning colour.
- The summary line, and the hint that later shifts of a listed task join automatically
  (D9).
- Data: `/candidate-shifts?task_id=…` for the selected tasks, refetched on selection
  change and cached per task id.

**`src/lib/shared-list-selection.ts`** (WP7, pure, with a spec, covering the PO
correction (a) exactly):

```ts
type DayState = 'checked' | 'indeterminate' | 'unchecked' | 'empty'
shiftsByDay(shifts, selectedTaskIds): Map<string /*YYYY-MM-DD*/, Shift[]>
dayState(dayShifts, excluded: ReadonlySet<string>): DayState   // empty → disabled "keine Schicht"
toggleDay(dayShifts, excluded): Set<string>   // checked → exclude all; unchecked|indeterminate → include all
addTask(excluded, taskShiftIds): Set<string>  // a new task starts fully included (clears stale ids)
pruneExcluded(excluded, selectedTaskIds, shiftsById): string[]   // by shift.task_id, on save
includedShifts(shifts, selectedTaskIds, excluded): Shift[]
taskProblem(taskShifts, excluded): 'none' | 'no_included' | 'all_full'   // merged blocker (a)
step1Blockers(...): BlockerKey[]   // no_task | no_included_shift | task_no_included:{name} | no_free_place
onlyDays(shifts, selectedTaskIds, excluded): string[] | null
maxPerOptions(includedCount): (number | null)[]   // [null, 1, …, min(3, n)]
clampMaxPer(value, options): number | null
autoTitle(taskNames, eventName, t): string        // 0 → '', 1 → "{name}: Wer hilft mit?", 2 → "{a} und {b}", ≥3 → "Hilf mit: {event}"
```

**Step 2, "Wie die Liste aussieht"** (`WizardSettingsStep.vue`; vee-validate with a
hand-written zod schema. Do not use the generated zod schemas with `.default()`; see
RegisterView.vue around l.150-170):

- Überschrift (required). It is auto-filled by `autoTitle` until the user types in
  it. "Touched" is set only on a real edit.
- "Ein paar Sätze dazu": empty by default, with a placeholder. There is no hard-coded
  event text (flaw 10).
- "Wo teilst du den Link?" (optional), with the hint "Sehen nur ihr. …".
- Was müssen Helfende angeben:
  - Name "immer";
  - E-Mail as a `ToggleGroup` of Pflicht | Freiwillig. `off` stays possible in the
    API and is not offered in the UI;
  - Telefon as Nicht fragen | Freiwillig | Pflicht;
  - the warning when the email is optional.
- Was sehen andere: a `RadioGroup` of "Nur, wie viele Plätze frei sind" (default) or
  "Auch die Vornamen", with the prototype's helper texts plus "Nur Vornamen von
  Leuten, die beim Eintragen gesehen haben, dass ihr Vorname hier steht." (D12). On
  edit, when the value changes, the hint "Gilt für alle, die sich ab jetzt eintragen.
  Wer schon eingetragen ist, bleibt, wie es beim Eintragen hieß."
- **Only for event admins** (`overview.is_admin`): a `Checkbox` "Wer sich hier
  einträgt, kann mit einem Konto später der Veranstaltung beitreten"
  (`claim_grants_membership`, default off, D4), with the hint "Mitglieder sehen alle
  veröffentlichten Aufgaben und die Mitgliederliste mit E-Mail-Adressen." People in
  charge never see it, and the API refuses it from them.
- **Schichten pro Person: default "so viele, wie frei sind" (`null`)**, then
  "höchstens 1…3", with the hint "Gezählt über die E-Mail-Adresse. Die Liste hat {n}
  Schichten."
- Wie lange bleibt die Liste offen:
  - "Bis die letzte Schicht beginnt" (default), showing the computed date and time;
  - "Bis zu einem Tag", with a `DatePicker` whose min is today on the event clock
    (`wallClockIn(zone)`) and whose max is the last included shift's date. Its default
    is that last date (no hard-coded `'2026-11-30'`);
  - "Bis jemand sie beendet".

**Submit.**

- Create: POST. On success go to step 3.
- Edit: PATCH. On success toast "Gespeichert. Der Link bleibt derselbe.", then go to
  `shared-lists?list=<id>`.
- Duplicate (`?from=`): prefill from `GET /shared-lists/{id}`, with the title counted
  as typed and the create mode active.

**Step 3, "Teilen"** (`WizardShareStep.vue`, create only):

- the success box;
- the link box with "Link kopieren";
- an editable "Text für die Gruppe" `Textarea` built by
  `src/lib/shared-list-share-message.ts` (WP7, with a spec). It is gender-neutral,
  with no "Für den {event}": "Hallo zusammen! Für „{event}“ ({dates}) suchen wir noch
  Leute." It lists per task when there are at most 8 open shifts, and summarises per
  task otherwise (prototype §9);
- "Text kopieren", the QR code, and Vorschau or Fertig.

**API composable** `src/composables/useSharedListWizardApi.ts` (WP7, spec required):
`fetchCandidates`, `fetchCandidateShifts`, `fetchDetail`, `create`, `update`.

### 7.5 Public page and guest pages (WP8)

`src/layout/GuestLayout.vue`:

- a minimal header with the WirkSam wordmark and no navigation;
- `main` with `mx-auto w-full max-w-2xl px-4 py-6`, `data-testid="main-content"`;
- `components/auth/AuthShellFooter.vue` reused as-is, which gives the privacy, terms,
  impressum and changelog links plus `LanguageSwitch` and `AppearanceMenu`;
- no `CookieNotice`: the page itself stores nothing, and the footer stores the
  language or appearance only when the visitor changes it (§5), which needs no
  consent.

`src/views/guest/SharedListPublicView.vue`:

- **States**: loading (skeleton), not found, paused, closed, list, form, done.
- It uses the anonymous client from `@/client/client.gen`
  (`client.get/post<…, unknown, true>({ url, throwOnError: true })`, the
  `stores/sandbox.ts:97` pattern), never `useAuthenticatedClient`.
- **Not found** (unknown or rotated code): "Diesen Link gibt es nicht (mehr). Frag bei
  denen nach, die ihn geteilt haben."
- **Paused** and **closed** use the prototype texts.
- **List**:
  - the hero is "{event name} · {formatDaySpan(event dates)}", then the h1 title
    (`data-testid="page-heading"`), then the intro. Title and intro are organiser
    text on a page strangers trust: plain `{{ }}` interpolation, the intro in a
    `<p class="whitespace-pre-line">`; **no** `v-html`, `renderMarkdown` or linkify
    (lib/markdown.ts:3-15 is for `LocationDescription.vue` only). A component spec
    asserts that a URL and `<b>` in the intro render as literal text;
  - `EventZoneHint` with `event.timezone`;
  - `components/guest/PublicShiftList.vue` shows the days with long headings
    (`formatDateLabel`) and shift cards:
    - task name, then "{formatTimeRange} · {location}";
    - "Dabei: {names}{ und {n} weitere}";
    - "{n} frei" or "voll";
    - "Eintragen", disabled and faded when full;
  - empty: "In dieser Liste gibt es keine Schichten mehr."
  - Use `formatDateLabel`/`formatDaySpan`, **never** `formatDate`, which renders the
    previous day west of UTC.
- **Form**, `components/guest/GuestSignupForm.vue`:
  - Zurück, then the shift summary, then the fields in this order:
    - name (`autocomplete="name"`);
    - email, unless `off`, with the "freiwillig" tag;
    - phone, unless `off`;
  - the reminder checkbox, shown only when an email is typed, checked by default;
  - `TurnstileWidget` with `action="shared-list-signup"`, only when
    `TURNSTILE_SITE_KEY` is set. Submit is disabled while the challenge is unsolved,
    the widget resets after **any** failed submit, and the token is omitted when empty
    (RegisterView.vue:97,238-239,252-258,401-407);
  - validation order and messages per prototype §7, with `focusFirstInvalid`;
  - the fine print, made true (D12): "Deinen Namen sehen die Helfenden dieser
    Veranstaltung bei der Schicht. E-Mail und Telefon sehen nur die Verantwortlichen
    dieser Aufgabe und die Organisator:innen.", plus, when `show_names='first'`,
    "Dein Vorname steht bei dieser Schicht auf geteilten Listen, die Vornamen
    zeigen.", plus a link to the privacy page;
  - `language` sent as the current locale.
- **Done**, `components/guest/GuestSignupDone.vue`:
  - the prototype texts; with `mail_queued`, "Wir haben dir eine Mail an {email}
    geschickt. Über den Link darin kannst du dich austragen.";
  - with `show_manage_link` (no email, or the mail could not be sent): the manage link
    `/guest-signup#<token>` in a copy box, "Speichere diesen Link. Nur damit kannst du
    dich später wieder austragen.";
  - "Noch eine Schicht eintragen" when `remaining !== 0`. It keeps the fields and
    sends `guest_token`;
  - "Eintragung zurücknehmen", which calls `/public/guest-signups/cancel` with the
    in-memory token. This is an undo for mistakes;
  - **"Fertig – nächste Person"**, and an idle timeout of 2 minutes on the done step,
    both of which clear every field, the token and the shown email, and return to the
    list. A tablet at the stand must not hand the next person the previous guest's
    address or undo button (`useIdle(120_000)` from `@vueuse/core`);
  - only when `list.claimable`: the upsell box "Öfter dabei?" with "Konto anlegen",
    linking to `/register?email=<email>`, and the line "Danach kannst du diese
    Eintragung in dein Konto übernehmen." WP8 adds `?email=` prefill to
    `views/auth/RegisterView.vue`. Without `claimable` there is no upsell, because an
    account would not show these shifts;
  - for a **signed-in visitor**, a banner "Angemeldet als {name}. Du trägst dich hier
    ohne Konto ein." and name and email prefilled. After a sign-up on a `claimable`
    list with `profile.email_verified` and the same address, an "In mein Konto
    übernehmen" button calls `POST /guest-claims` with `guest_id`.
- `SELECTED_EVENT_EXEMPT_ROUTES` and the noindex meta come from WP5. Language follows
  storage, then the browser (`i18n.ts` l.55-80). `LanguageSwitch` switches in place
  because the route is not localized.

`src/views/guest/GuestSignupManageView.vue`:

- reads `location.hash.slice(1)` once, keeps it in component state, and immediately
  calls `history.replaceState(history.state, '', location.pathname)` so the token
  leaves the address bar, the history entry and anything a shared screen shows; then
  POSTs it to `/manage`;
- lists the bookings, each with "Austragen" (`confirmDestructive`);
- has a reminder `Switch` and "Meine Daten löschen" (`confirmDestructive`, explaining
  what remains: anonymous past shifts);
- has "Das war ich nicht" (`confirmDestructive`: "Wir löschen die Eintragung und
  schreiben dieser Adresse nie wieder.") → `/not-me`;
- shows the not-found state for a bad token.

Stores, with specs:

- `src/stores/guestSignup.ts`: `load(code)`, `signUp(body)`, `undo()`, `reset()` (the
  "nächste Person" clear), `manage(token)`, `cancel`, `setReminders`, `erase`,
  `notMe`.
- `src/stores/guestClaim.ts`: `load()`, `claim(guestIds)`.

`components/guest/PublicListPreview.vue`: the `PublicShiftList` inside a framed card,
read-only, with the buttons replaced by the hint. It is used by WP6's Vorschau tab.

Claim UI. The main path is: guest → "Konto anlegen" → register → verify → sign in.
That account has no membership and no `selected_event_id`, and `home` is not exempt
from the selected-event guard (router/index.ts:47-81, 164-173), so it lands on
`select-event?mode=onboarding`. Someone who claims within the retention window
after an event lands on `mode=expired`. The claim must work from there:

- `components/guest/GuestClaimBanner.vue` shows when
  `authStore.profile.claimable_guest_signups > 0` and links to `/app/guest-claims`. It
  is mounted in `views/HomeView.vue` **and** in `views/events/SelectEventView.vue`
  (both modes).
- `src/views/guest/GuestClaimsView.vue` (route `guest-claims`, exempt, §7.1) lists the
  sign-ups per event (`GET /guest-claims`) with checkboxes and "Übernehmen", saying
  "Du wirst damit Mitglied der Veranstaltung." On success it refreshes the profile,
  selects `event_ids[0]` (`PUT /users/me/selected-event`, now allowed because the
  claim made a membership) and navigates to `home` with a toast.

Infrastructure (WP8):

- `frontend/nginx/default.conf` locations (§5);
- the `Disallow: /guest-signup` line in `frontend/scripts/prerender.mjs:461-472`.

### 7.6 Navigation (WP5)

- `components/navigation/AppSidebar.vue`, `navMain` (l.202-288), placed next to Teams.
  - The rule is `isSwitchOn(SHARED_LISTS_ENABLED) && selectedEvent &&
    !selectedEvent.is_sandbox && (selectedEvent.can_manage ||
    selectedEvent.managed_task_count > 0)`.
  - It is not in `navManager`, because `isManager` excludes people who are only in
    charge.
  - The label is `navigation.sidebar.items.sharedLists`, and the testid
    `sidebar-link-shared-lists` comes from `NavMain`.
- The same rule goes into `components/navigation/MobileBottomNav.vue` `moreGroups`
  (l.67-125).
- Specs `navigation/__tests__/AppSidebar*.spec.ts`, `MobileBottomNav.spec.ts` and
  `NavMain.spec.ts` are updated.
- `useAppConfig.ts`: `SHARED_LISTS_ENABLED` in `AppConfig` and `DEFAULTS`.
- `docker-entrypoint.sh`: `SHARED_LISTS_ENABLED: '${SHARED_LISTS_ENABLED:-true}'`.

### 7.7 i18n layout

Each namespace has a single owner. en and de must have the same keys. German uses
"du" (the Terms and Privacy pages keep "Sie"), says "Organisator:in" and never "admin"
(`wording.spec.ts`), and avoids jargon. Escape `@`, `|` and `{` (locales/CLAUDE.md),
and use plurals as `t(key, {count}, count)`.

| File | Owner | Top-level keys |
|---|---|---|
| `navigation.json` (edit) | WP5 | `sidebar.items.sharedLists`, `breadcrumbs.guestClaims` |
| `common.json` (edit) | WP5 | `pagination.{first,previous,next,last,morePages,pageOf}`, `sort.{label,ascending,descending,sortBy}`, `selection.{count,clear,region}` |
| `errorCodes.json` (edit) | WP5 | every code in §6.5 |
| `sharedLists.json` (new) | WP6 | `page`, `tabs`, `summary`, `notice`, `filters`, `search`, `table.columns`, `sort`, `bulk`, `issues`, `rows`, `empty`, `status.{live,paused,expired,ended}`, `tasks`, `preview`, `detail`, `signups`, `remove.{title,notify,erase,since,result}`, `managersSwitch`, `pauseAll.lockManagers`, `settings`, `guest.{tag,erased,possibleDuplicate}`, `actions`, `confirm`, `toasts` |
| `sharedListWizard.json` (new) | WP7 | `title`, `steps`, `picker`, `days`, `shiftsToggle`, `blockers`, `settings.{title,intro,shareNote,ask,showNames,showNamesChanged,claim,maxPer,ends}`, `share`, `shareMessage`, `autoTitle`, `leaveGuard`, `toasts` |
| `guestSignup.json` (new) | WP8 | `page`, `layout`, `list`, `form`, `validation`, `done.{mailSent,keepLink,nextPerson,undo,another}`, `upsell`, `signedIn`, `states.{notFound,paused,closed,empty}`, `manage.{notMe,erase,reminders}`, `claim`, `preview`, `privacyNote` |
| `preauth.json`, `duties.json` (edits) | WP8 | §9 |

---

## 8. Tests

### 8.1 Backend

Conventions:

- Files go in `backend/tests/api/routes/test_<x>.py` and `backend/tests/logic/test_<x>.py`.
- Run one pytest at a time, because the test database is shared (memory note).
- Pin the clock with `clock_before_fixture_shifts` (tests/fixtures/clock.py:59) or
  `set_wall_clock` (l.48).
- Anonymous endpoints use `unauthenticated_client` (tests/fixtures/client.py:129-190).
- Concurrency tests use real committed transactions, as
  `tests/logic/test_invitation_concurrency.py` does.
- The fixtures `test_shared_list`, `make_shared_list(...)` and `make_list_guest(...)`
  go in a new `tests/fixtures/shared_lists.py`, registered in `tests/conftest.py`
  (WP1).

**WP1** (`tests/logic/test_shared_list_offer.py`, `tests/logic/test_shared_list_access.py`,
`tests/crud/test_shared_list.py`, `tests/crud/test_booking_reminder_replace.py`,
`tests/migrations/`):

- `starts_at` for an untimed shift is 00:00.
- `effective_status`:
  - every branch;
  - `ends_on` is inclusive on the event's date in a non-Berlin zone (for example
    `America/New_York` when UTC is already the next day);
  - an event that is not published gives `expired`;
  - `last_shift` with no shifts gives `expired`;
  - `manual` with no shifts gives `live`.
- `list_shifts` excludes:
  - excluded shifts;
  - team tasks;
  - draft tasks;
  - tasks moved to another event;
  - started shifts.
- `free` is clamped when `max_bookings` is lowered.
- `shared_list_access`: admin, manager (all tasks), viewer (some), None (none, or not
  a member), a stale `task_managers` row after leaving gives None, and the superadmin
  gives admin.
- `shared_list_scope`: a member with **zero** managed tasks gets 403
  `shared_list.forbidden` (never an unrestricted scope); a sandbox event gives 404 to
  the superadmin (`test_sandbox` fixture + `as_admin`).
- `require_shared_list_manager`: with `managers_share_lists=false`, a manager gets 403
  `shared_list.managers_disabled` for edit, resume and rotate, and passes for pause and
  end; an admin always passes. `require_claim_flag_allowed` refuses `true` from a
  manager.
- `require_shared_list_tasks` returns 403 with the unmanaged ids, and 404 for a
  non-member.
- `replace_for_booking`: a booking with a cancelled 1440 row gets a new pending 1440
  row without an `IntegrityError`; a `sent` row is kept and its offset skipped;
  `entries=[]` deletes only the non-sent rows.
- Code generation uses the alphabet and length 12. The retry on collision is tested by
  monkeypatching `secrets.choice`.
- Migration round trip, plus `TestUserDeletionCascades`:
  - delete a list creator who owns the event, with guests and bookings;
  - delete an event with lists, guests and bookings: no FK violation, the guest users
    and their bookings survive, the `guest_activity_log` rows survive.
- `lock_shifts`: two concurrent transactions serialise. That is a committed-transaction
  test.

**WP2** (`test_shared_lists.py`, `test_shared_lists_overview.py`):

- **Create**:
  - happy path as admin;
  - happy path as a person in charge with their own tasks;
  - 403 with a foreign task;
  - 422 for a team task, a draft task, and a task from another event;
  - excluded ids of unselected tasks are dropped;
  - `no_shifts`, `no_free_places`;
  - each `ends_on_invalid` bound;
  - 409 when the event is not published;
  - 409 `too_many` at 200;
  - 403 on a sandbox event;
  - 404 when the switch is off;
  - `claim_grants_membership=true`: 201 for an admin, 403 `shared_list.claim_admin_only`
    for a person in charge; a person in charge's PATCH without the field keeps an
    admin's `true`;
  - 403 `shared_list.managers_disabled` for a person in charge when the event setting
    is off.
- **Transitions**: the full matrix of §4.3, including resume of an expired-by-date list
  (`ends_mode` becomes last_shift), resume with nothing to offer, and actions after
  `ended`.
- **Bulk**: partial success with mixed statuses and permissions. Pause-all is admin
  only, and `lock_managers=true` switches `managers_share_lists` off so a person in
  charge's resume then gets 403.
- **Event setting**: `PATCH /events/{id}` with `managers_share_lists` (admin only,
  `null` keeps it, as `_NOT_NULL_SETTINGS`).
- **Lists endpoint**:
  - each filter count, ignoring q;
  - `ended_matching`;
  - every sort key in both directions, with a stable id tiebreak across pages;
  - pagination totals;
  - q matches a task name;
  - viewer scoping (a mixed list is visible but `issue=None`, `access=viewer`);
  - a plain member gets 403 `shared_list.forbidden` on the lists, overview, tasks and
    candidates endpoints.
- **Sandbox**: the superadmin (`as_admin`) gets 404 on the lists, overview, tasks,
  candidates and candidate-shifts endpoints of a `test_sandbox` event.
- **Issues**:
  - a paused list whose shift is covered by another live list has no issue;
  - an uncovered one has `stranded`;
  - a date list with 2 days left and free places has `expires_soon`;
  - with 0 free, no issue.
- **Tasks tab**:
  - `stranded_free` versus `unlisted_free`;
  - team-locked `can_share=false`;
  - a person in charge sees only managed tasks;
  - sorting.
- **Candidates**: team-locked tasks hidden without q, shown with q, and
  `locked_count`. **Candidate shifts**: more than 50 ids gives 422, and started
  shifts are omitted.
- **Lifecycle**:
  - `shift-dates` moves `ends_on`;
  - task delete and shift delete cascade the rows.
  - The moved-task test is WP4's, next to the code that detaches the task.
- `EventRead.managed_task_count`.

**WP3** (`test_public_shared_lists.py`, `test_shared_list_signups.py`,
`test_list_guests_admin.py`, `test_guest_claims.py`,
`tests/logic/test_shared_list_signup_concurrency.py`, `tests/logic/test_guest_mail.py`,
`tests/logic/test_guest_quota.py`, `tests/logic/test_shared_list_retention.py`,
`tests/core/test_turnstile.py` additions, `tests/core/test_rate_limit.py` additions):

- **Public GET**:
  - payload contents (no PII, no `share_note`), `claimable`;
  - paused or closed give `days=[]`;
  - the `names` rule (D12): a member booking is never named; a guest who signed up
    while the list said `none` is still not named after the list is switched to
    `first`; a guest who consented is named on another `first` list with that shift
    and on no `none` list; an erased guest is never named;
  - started shifts are hidden;
  - `view_count` increments only while live;
  - the preview does not count;
  - unknown and rotated codes give 404, and the miss limiter returns 429 after 20 with
    `TESTING` patched off.
- **Sign-up**:
  - every refusal in §4.7, in order;
  - `ask_*` required, optional and off;
  - normalisation;
  - duplicate email on the same shift through another list gives 409;
  - chain continuation with `guest_token` reuses the user, a token from another list
    gives 403 `shared_list.guest_token_invalid`, and an overlapping shift gives
    `booking.time_conflict`;
  - undo then sign the same shift again through the chain: 201, the cancelled row is
    reactivated, no `IntegrityError`, the reminder exists once;
  - `max_per_person` by email, by chain, and with no limit;
  - with `TESTING` off: 20 sign-ups per address, 3 other events per address, 500 per
    list; and **erasing the guest does not reset any of them**;
  - Turnstile on, off, and with a wrong action (patch
    `app.api.routes.public_shared_lists.verify_turnstile`);
  - the reminder row only with an email and `remind`;
  - one confirmation per chain: the first sign-up queues it, a follow-up does not;
  - a suppressed address and SMTP off both give `mail_queued=false`,
    `show_manage_link=true`, and the same response shape;
  - guest user and guest row fields exactly as in §3.1/§3.2 (`shared_list_id`,
    `show_first_name` copied from the list).
- **Concurrency** (committed transactions, with the limits switch patched on so the
  production lock order runs): N parallel sign-ups for the last place give exactly
  one success. A pause racing a sign-up never leaves a booking committed after the
  pause; the test pauses through `crud_shared_list.get_for_update` plus a direct status
  write (WP1 code), not WP2's `transition`. Two claims over overlapping shifts do not
  deadlock.
- **Manage**:
  - a bad token gives 404;
  - cancel until the shift is over;
  - reminders off, on, off, on: no `IntegrityError`, one pending row at the end; 409
    without an email;
  - erase deletes future and cancelled bookings, anonymises, kills the token, keeps
    past confirmed bookings, and deletes the user when nothing is left;
  - not-me does the same and suppresses the address: the next sign-up with it gets
    no mail.
- **Organiser removal** (`/signups/remove`): §4.10 gates and every `skipped` code; a
  claimed booking is skipped `signup_not_guest`; reminders cancelled; `notify=false`
  sends nothing; `created_since` removes exactly the later sign-ups and caps at 500;
  `erase` is 403 for a person in charge and erases for an admin.
- **Superadmin guest data**: search by email, name and phone; export contains every
  stored field; erase; 403 for an event admin.
- **Signups endpoint**:
  - sort, search and pagination;
  - viewer `hidden_count`;
  - contact data only on managed tasks;
  - `possible_duplicate`; `can_erase` only for event admins.
- **NotificationService guest branch and guest mail**:
  - `booking.cancelled_by_admin`, `shift.time_changed` and `booking.reminder` reach
    `guest_mail.deliver_notice` with `data`, never with a title or body;
  - delete a shift with `cancellation_reason="<script>X"`: the guest mail contains
    neither the text nor any escaped form of it, and does not mention "My Bookings";
  - a task delete that cancels three of a guest's bookings sends one mail listing all
    three; a second notify for the same bookings sends nothing;
  - a moved shift's mail shows the new time;
  - over `GUEST_MAILS_PER_ADDRESS_PER_DAY` (limits on), further mails of any kind are
    not sent, and the log line holds no address;
  - SMTP off: nothing sent, and no log line contains the manage token;
  - any other type writes nothing; no `Notification` row is created for a guest.
- **Claim**:
  - unverified gives 403;
  - another address is not found;
  - a guest from a list without `claim_grants_membership` is not found and not
    counted in `claimable_guest_signups`;
  - the move keeps the booking id;
  - duplicate shift → the guest booking cascades away, counted in `skipped_duplicates`;
  - the user's cancelled row on that shift is deleted and the guest booking moved;
  - a guest booking with `remind=true` meets account defaults `[15 push, 1440 email]`:
    no `IntegrityError`, the defaults are the pending reminders;
  - vouchers: a guest's shift ends, the rate goes 0 → 5, then the claim: the earning
    stays 0 and belongs to the account; a shift ending after the claim earns 5;
  - membership created on a private event (the admin allowed it on the list);
  - guest user deleted;
  - a sandbox event is skipped;
  - `claimable_guest_signups` in `GET /users/me`.
- **Retention**:
  - anonymised once the guest's **last shift date** + N has passed, not the event's
    end date;
  - a task moved to a later event, then the source event deleted, then the sweep:
    the booking in the target event survives, and the guest user is not deleted;
  - due orphans are anonymised, never deleted while they have bookings;
  - anonymised guests with no bookings left are deleted;
  - `guest_activity_log` rows older than 7 days are pruned.
- **Manage token**: the round trip, tampering, and nonce reset.

**WP4** (extend the existing files):

- `test_bookings.py`:
  - concurrent member bookings on the last place give one 201 and one 409 (committed
    transactions);
  - a double submit gives 409, not 500;
  - book with default reminders, cancel through `DELETE`, book again: 201, no
    `IntegrityError`, one pending row per default offset (the existing bug, §4.5a);
  - PATCH to cancelled cancels the reminders.
- `test_shifts.py`: guest rows carry `is_guest`; the guest email is shown only to
  managers.
- `test_tasks.py`: `TaskBookingEntry.is_guest`. A moved task loses its list links
  (checked through `crud_shared_list.task_ids`, WP1 code, so the test does not wait
  for WP2's endpoints); its guest bookings stay confirmed.
- `tests/logic/test_vouchers.py`: `settle_earnings` with an ended guest booking on a
  voucher task writes one row with `amount=0`; a later rate change does not alter it;
  the guest does not appear in `_voucher_shifts`.
- `test_work_hours.py`: guest hours are listed with `is_guest`.
- `test_reporting.py`: the CSV shows the guest email and `booked_via`.
- `test_users.py`: the admin search excludes list guests.
- `tests/api/routes/test_auth.py`: an access token minted (with `make_access_token`)
  for a list-guest user gets 403 `auth.guest_account` on `GET /users/me` and
  `DELETE /users/me` (both `AnyUser`), on a `CurrentUser` route, on the
  `X-Test-User-Email` path, and on an SSE route through `QueryTokenUser`.

### 8.2 Frontend unit tests (vitest; the 90 % per-file gate applies to every new `src/lib`, `src/composables`, `src/stores` file)

- **WP5**:
  - `lib/__tests__/shared-lists.spec.ts`;
  - `lib/__tests__/page-head.spec.ts` (titleKey, noindex add and remove, locale
    change);
  - `composables/__tests__/useTableQuery.spec.ts`;
  - `composables/__tests__/useRowSelection.spec.ts` (clears on change, tri-state,
    non-selectable rows);
  - component specs (jsdom) for `ListPagination`, `SortableHead` (`aria-sort`, emits),
    `FilterChips` (`aria-pressed`) and `SelectionBar`;
  - updated sidebar and mobile nav specs (visible for a person in charge, hidden in
    sandbox or when the switch is off).
- **WP6**:
  - `stores/__tests__/sharedLists.spec.ts`;
  - component specs for `SharedListsTable` (sort header clicks emit query, checkbox
    disabled for ended), `SharedListIssueStrip`, `TaskSharedInCell`,
    `SharedListDetailDialog` (footer per access, confirm flows; the
    `EventInvitations.spec.ts` mocking pattern), `SharedListRemoveSignupsDialog`
    (`notify` default on, `erase` only with `can_erase`, the `created_since` body) and
    `SharedListManagersSwitch` (admin only).
- **WP7**:
  - `lib/__tests__/shared-list-selection.spec.ts`, every rule of correction (a):
    - day toggle from each state;
    - adding a task clears stale ids;
    - pruning by `task_id`;
    - the merged blocker;
    - `onlyDays`;
    - the `maxPer` default `null` and clamping;
  - `lib/__tests__/shared-list-share-message.spec.ts`;
  - `composables/__tests__/useSharedListWizardApi.spec.ts`;
  - a view spec for the step gating, focus on the step heading, the leave guard, the
    claim checkbox only for admins, and the `show_names` change hint on edit.
- **WP8**:
  - `stores/__tests__/guestSignup.spec.ts`;
  - `stores/__tests__/guestClaim.spec.ts`;
  - `GuestSignupForm` spec: validation order, the reminder checkbox only with an
    email, Turnstile reset on failure, and the token omitted when empty;
  - `SharedListPublicView` spec: a URL and `<b>` in the intro render as literal text;
  - `GuestSignupDone` spec: "nächste Person" and the 2-minute idle timeout clear the
    fields, the token and the email; the manage link shows only with
    `show_manage_link`; the upsell only with `claimable`;
  - `GuestSignupManageView` spec: the fragment is read and removed with
    `history.replaceState`;
  - `GuestClaimBanner` spec (mounted from both HomeView and SelectEventView).

### 8.3 E2E (Playwright; read `frontend/e2e/CLAUDE.md`)

- Never mutate `adminUser`, `memberUser` or `workerEvent`. Seed a per-test event with
  `serverApi`.
- Wait with `waitForResponse`, not `toPass`.
- Locally run `pnpm --prefix frontend exec playwright test --reporter=list`.
- The guest flow must not depend on cookies. CI is cross-site (fake-session.ts:11-15).

The specs:

- **WP8** adds the project `{ name: 'guest', use: devices['Desktop Chrome'],
  dependencies: ['test-reset'], testMatch: '**/tests/guest/**/*.spec.ts' }` to
  `playwright.config.ts`. It is not `public`, which has no reset dependency.
  - `tests/guest/shared-list-signup.spec.ts`, following the register.spec.ts:100-140
    pattern: `test.use({ storageState: { cookies: [], origins: [] } })`, then
    `pinBrowserPreferences(page)`. Cases:
    - sign up with an email address;
    - see "Du bist eingetragen";
    - sign up for another shift through the chain;
    - undo;
    - not found, paused and closed states;
    - the full-shift message (fill the shift via the API between load and submit);
    - the noindex meta is present;
    - the German variant (`localStorage.locale='de'`);
    - "Fertig – nächste Person" empties the form;
    - a sign-up without an email shows the manage link.
  - `tests/guest/guest-manage.spec.ts`: open `/guest-signup#<token>` using the token
    from the API sign-up response; the URL no longer carries the fragment; cancel,
    erase; "Das war ich nicht".
  - `tests/a11y/guest-pages.spec.ts`: `expectNoA11yViolations` on the list, form, done
    and manage pages.
  - `tests/mobile/shared-list-public.spec.ts`.
  - `tests/authenticated/guest-claim.spec.ts`: a freshly registered, verified user
    with **no** events (so the guard puts them on `select-event?mode=onboarding`) sees
    the banner there, opens `/app/guest-claims`, claims a seeded guest sign-up from a
    list with `claim_grants_membership=true`, and lands on `home` with that event
    selected. A sign-up from a list without the flag is not offered.
- **WP6**:
  - `tests/authenticated/shared-lists-manage.spec.ts` (`adminPage`; seed 25 lists via
    `createSharedList`):
    - the sidebar link and page heading;
    - filter chip counts;
    - sort by title in both directions;
    - page 2;
    - the selection clears on page change;
    - bulk pause, then resume, then end with confirm;
    - detail copy link, rotate (the old code gives 404 via `publicSignup`), end;
    - a sign-up via the API appears in the detail and can be removed, with and
      without "Per Mail Bescheid geben";
    - "Diese und alle neueren austragen" removes the later sign-ups;
    - the Aufgaben tab "Zu tun".
  - `tests/multi-user/shared-lists-people-in-charge.spec.ts`:
    - a person in charge creates a list with their task;
    - sees a mixed list read-only with the lock note;
    - a plain member gets 403 `shared_list.forbidden` from the API and has no sidebar
      link;
    - after the admin switches "Verantwortliche dürfen Listen teilen" off, the person
      in charge cannot resume or create.
  - Add the management route to `tests/a11y/admin-routes.spec.ts`.
  - `tests/mobile/shared-lists.spec.ts` (card list, ⋯ menu, detail as a drawer).
- **WP7**: `tests/authenticated/shared-list-wizard.spec.ts`:
  - pick two tasks, uncheck a day, and see one shift re-included individually make the
    day indeterminate;
  - the `maxPer` default reads "so viele, wie frei sind";
  - publish and land on the share step with link, text and QR;
  - edit keeps the code;
  - duplicate an ended list.
- **COVERAGE.md**: only WP8 commits `frontend/e2e/COVERAGE.md`, regenerated once all
  specs are in (`pnpm --prefix frontend generate-e2e-coverage`). Other packages may
  run it locally but must not commit it. This works with CI because every package's
  PR targets the integration branch `feat/shared-lists`, and the CI workflows,
  including the COVERAGE.md diff check, run only on pull requests into `main` and
  `dev` (.github/workflows/lint-frontend.yml:10-17, 55-61). The one PR
  `feat/shared-lists → dev` runs them after WP8 has merged (§10).

---

## 9. Docs, changelog, privacy and landing claims

Owners in brackets. Every user-facing change needs en and de, and German uses "du"
(legal pages "Sie").

- **Privacy** `src/views/preauth/PrivacyView.vue` + `preauth.privacy.*` (L:638-702)
  [WP8]. Every bullet is a hard-coded `<li>`, so new items need template edits. Add a
  section "Eintragen ohne Konto" / "Signing up without an account":
  - the data collected (name; email and phone if the list asks for them; the shift);
  - purposes (the sign-up, confirmation and cancellation link, an optional reminder,
    the people in charge contacting you);
  - who is responsible: one sentence naming the operator (the controller of the
    platform) and saying that the organisers decide what a list asks for and use the
    contact data for their event. The exact controller/processor wording is part of
    open question Q4 and is checked before release;
  - legal basis Art. 6(1)(b) for the sign-up and reminder, and 6(1)(f) for abuse
    protection (Turnstile/Cloudflare when enabled, and a non-reversible checksum of
    the email address kept for 7 days to limit how often an address is mailed, D17);
  - who sees what (D12: the first name on shared lists only if the list said so when
    you signed up);
  - retention ("{N} Tage nach deiner letzten Schicht anonymisiert", §4.15), with the
    same number as `GUEST_DATA_RETENTION_DAYS`;
  - erasure: through the link in the mail or the link shown after signing up, "Das
    war ich nicht" for sign-ups someone else made, by asking the organisers, or by a
    request to LEGAL_EMAIL, which the operator answers with the `/list-guests` tools
    (§6.2);
  - on the device: "nichts, außer deiner Sprach- oder Darstellungswahl, wenn du sie
    änderst".
  - Also fix `dataCollected.intro` (:652, "When you create an account…"), mention
    Cloudflare Turnstile under third parties (:696), and update `lastUpdated` (:663).
- **Terms**: unchanged in v1 (Q4). `changes.description` (L:833) commits the operator
  to emailing every account holder four weeks before a change. The guest page carries
  its own notice instead.
- **Landing** (`preauth.landing.*`) [WP8]:
  - `faq.items.account.answer` (L:337) becomes "No. On a shared list, helpers sign up
    with just a name. A free account is for people who help more often: all their
    shifts in one place and reminders on their phone." (It must not promise that
    guest sign-ups move into an account; that depends on the list, D4.)
  - `faq.items.data.answer` (:353) and `about.cards.data/gdpr` (:285, :293) add guest
    sign-ups.
  - `about.cards.private` (:297) and `faq.items.visibility` (:377) add "…unless you
    share a list; then anyone with that link sees the shifts on it, nothing else."
  - `audience.volunteer.points.0` (:325) and `audience.organiser.points.1` (:315)
    mention the lists.
  - `features.rows.bookings.description` (:437): organisers can now remove people who
    signed up without an account.
  - `hero.subtitle` (:542), `faq.items.what.answer` (:381) and
    `seo.landing.description` (:801): "reminders for everyone with an account".
  - `journey.volunteer.*` (:572-575).
  - A new `features.more.items.sharedLists` **plus** its entry in the `extras` array at
    `components/landing/LandingFeatures.vue:41-51` (with an icon), or llms.txt and the
    page disagree.
- **Comparison** [WP8]:
  - `tools.wirksam.cells.account` (:111) becomes "Not to sign up via a shared list;
    free account for more".
  - `goodFit` (:118), `lessSuited` (:119) and `summary` (:121).
  - `table.asOf` (:31) moves to "November 2026".
  - `e2e/tests/public/content-pages.spec.ts:17,25-27` asserts 'October 2026', so it
    must change.
- **Club festival** (`useCases.clubFestival.*`) [WP8]: rewrite
  `faq.items.account.answer` (:877, which today sends readers to competitors), and
  mention lists in `helperList` (:889), `hero.lede` (:906), `steps.items.invite`
  (:945), `cancellations` (:881) and `reminders` (:955).
- **Feature docs** (`frontend/src/docs/{en,de}/`) [WP8]:
  - New `feature/shared-lists.md` with `##` sections and a "## Frequently asked
    questions" / "## Häufige Fragen" section, a `DOC_PAGES` entry
    (`src/lib/content-pages.ts:158-177`, `{kind:'feature', slug:'shared-lists',
    key:'featureSharedLists'}`), `DOC_GROUPS` `feature.people` (:192-206), and the
    keys `preauth.docs.pages.featureSharedLists.name` and
    `preauth.seo.featureSharedLists.{title,description}`. `docs-content.spec.ts:243-305`
    enforces the structure.
  - Edits:
    - `feature/booking.md` (:7, :33, the FAQ :85-87 "Can I book for someone else?",
      :97-99 who sees what, :41-45 cancelling);
    - `feature/members.md` (:3, :56, the FAQ :87-89 "Does everyone need an account?",
      the :44-50 rename);
    - `feature/vouchers.md:63`;
    - `feature/hours-and-reports.md` (:29, :45, :70: guest email in the CSV);
    - `feature/teams.md` (:7, :19: team tasks cannot be on lists);
    - `feature/people-in-charge.md` (:3, :17);
    - `feature/shift-planning.md:15`;
    - `feature/self-hosting.md` (:68-80, :96: the `SHARED_LISTS_ENABLED`,
      `GUEST_DATA_RETENTION_DAYS` and `REGISTRATION_MODE` caveat);
    - `guide/first-event.md` (:11, :49-58);
    - `guide/volunteer-start.md` (:3, :9-16: the "signed up without an account" path).
- **Terminology** [WP8]: `duties.json:356,365,375` "Share links" becomes "Invitation
  links" / "Einladungslinks", with `members.md` and `first-event.md` to match (Q5).
- **Changelog** [WP8]:
  - `frontend/src/changelog/{en,de}/2026-11-XX_v0.29.0.md` with front matter `title`,
    `version: 0.29.0`, `date`.
  - A hero section "Sign-up lists without an account" (on by default for every
    organiser, so it qualifies), describing the defaults: email required, phone not
    asked, names hidden, as many shifts per person as are free, open until the last
    shift starts.
  - Hand-made images in `src/changelog/images/{en,de}/`.
  - "Also new": organisers can remove guest sign-ups (one, a selection, or everything
    after a given sign-up), sortable and paginated tables in user and event
    administration, translated pagination labels, and a fix for booking a shift again
    after cancelling it when reminders are on.
  - Check with `pnpm --prefix frontend generate-changelog`.
- **README.md** [WP8]: :25-26 and :64 get a feature bullet for shared lists.
- **Developer docs** [WP4, written after WP2 and WP3 merged]:
  - New `docs/SHARED_LISTS.md`: the model, D1-D18, the gates, the lock order, the
    table of places where guests are excluded or tagged (§4.12, mirroring the
    docs/SANDBOX.md table), `guest_activity_log` and its ceilings, retention by
    the guest's own shifts, the manage token, the claim permission, the moved-task
    caveat of §4.14, and the `/list-guests` calls for data-subject requests.
  - `CLAUDE.md`: a paragraph after "Getting into an event" (:193-198) naming the gates
    `shared_list_scope`, `require_shared_list_manager`, `require_shared_list_visible`,
    `require_shared_list_tasks` and `require_claim_flag_allowed`, the `is_list_guest`
    rule ("exclude or tag list guests wherever users are listed"), the rule "every
    guest mail goes through `guest_quota.reserve_mail`", the rule "write reminders for
    a booking that may have had some with `crud_reminder.replace_for_booking`", and
    the env vars in the Environment section.
  - `docs/SANDBOX.md` (rows), `docs/AUTH.md`:
    - the subject prefix `listguest|` in the data model (:198-230);
    - the new rate limits (:231-264);
    - Turnstile `expected_action` (:265-315);
    - "only endpoint that turns an anonymous caller into a row" is no longer true.
  - `docs/VOUCHERS.md` (:265-291: a shift that ends while a guest holds it is settled
    at 0; the claim settles first and re-points the earning rows).
  - `docs/PEOPLE_IN_CHARGE.md` (:122-150: guest rows and the list management rights).
  - `docs/SECURITY.md`: plaintext list codes and HMAC manage tokens.
  - A one-line "Superseded by 2026-11-10-shared-lists.md" header in
    `docs/plans/2026-04-18-public-guest-booking.md`.
- **Env** [WP1]: `.env.example` and `docs/deployment.md:147-169` get
  `SHARED_LISTS_ENABLED=true`, `GUEST_DATA_RETENTION_DAYS=30` and the D17 ceilings
  (commented, with their defaults), and deployment.md recommends Turnstile when the
  lists are on (the boot warning of §5).

---

## 10. Work breakdown

**Ownership rule.** A file is edited by exactly one package. One exception is
sanctioned: a **stub handoff**. WP1 and WP5 create placeholder files (a one-line
router, a `<template><div /></template>` SFC with the props listed here), and after
they merge only the named owner edits those files. Cross-package *imports* of a file
whose path and props this plan fixes are allowed. *Edits* are not.

Generated artefacts have one owner each: `frontend/src/client/**` is WP5,
`frontend/e2e/COVERAGE.md` is WP8.

Parallel packages never import each other's new code: WP2, WP3 and WP4a depend only
on WP1 and existing code, and WP6, WP7 and WP8 only on WP5 and the generated client.
That is why the §6.2 schemas live in WP3's own `app/schemas/shared_list_guest.py`
instead of reusing WP2's `SharedListBulkSkip`, and why each test that needs another
package's code is placed with that package (§8.1).

**Branches and CI.** Every package's PR targets the integration branch
`feat/shared-lists`. The CI workflows run only on pull requests into `main` and `dev`
(.github/workflows/*.yml), so each package runs the gates below locally before its PR
is merged, and the single PR `feat/shared-lists → dev`, opened after WP8 has merged,
runs the full CI, including the COVERAGE.md diff check.

Order (WP4 is delivered as two PRs, WP4a code and WP4b docs):

```
WP1 ──┬── WP2 ───┐
      ├── WP3 ───┼──┬── WP4b (docs)
      └── WP4a ──┘  └── WP5 (client regen + shell + kit) ──┬── WP6
                                                           ├── WP7
                                                           └── WP8 (merges last: COVERAGE.md, changelog)
```

WP5 starts once WP2, WP3 and WP4a have merged (the client is generated from all of
their endpoints). WP4b runs alongside WP5-WP8; its files (`docs/*.md`, `CLAUDE.md`)
overlap with nobody's.

### Verification commands (repo root; never `cd x && y`)

```bash
docker compose up db -d                         # without -f (port lives in the override)
just lint-backend                               # ruff check app, ruff format --check app, basedpyright app
uv run --directory backend basedpyright         # equivalent standalone; never pass "."
just check-migrations                           # alembic upgrade head && alembic check
uv run --directory backend pytest tests/api/routes/test_shared_lists.py -v   # one at a time
just test-backend                               # full suite with coverage
just generate-client                            # WP5 only
pnpm --prefix frontend exec eslint .
just check-locales
pnpm --prefix frontend type-check
pnpm --prefix frontend type-check:unit
pnpm --prefix frontend test:unit:coverage       # the gate, not test:unit
pnpm --prefix frontend build-only
pnpm --prefix frontend exec playwright test --project=<p> --reporter=list
pnpm --prefix frontend generate-e2e-coverage    # WP8 commits the result
```

### WP1. Backend foundation (first; it blocks all others)

**Owns (new):**

- `app/models/shared_list.py` (the six models of §3.1, including `GuestActivityLog`
  and `GuestMailSuppression`)
- the migration `app/alembic/versions/*_shared_lists.py`
- `app/crud/shared_list.py`: `create`, `get`, `get_for_update`, `get_by_code(code,
  lock)` (`lock` in `None | "key_share" | "update"`), `generate_code`, `set_tasks`,
  `set_excluded`, `task_ids`, `excluded_ids`, `detach_task_from_lists`,
  `shift_ends_on`
- `app/crud/shared_list_guest.py`: `create`, `get_by_user_id`, `get_for_update`,
  `contact_emails(user_ids)`
- `app/crud/search.py` (`like_pattern`)
- `app/logic/booking_capacity.py`
- `app/logic/shared_lists/__init__.py`
- `app/logic/shared_lists/offer.py`
- `app/logic/shared_lists/normalize.py`
- stubs, handed off afterwards: `app/api/routes/shared_lists.py` → WP2;
  `shared_list_guests.py`, `public_shared_lists.py`, `guest_claims.py` → WP3
- `tests/fixtures/shared_lists.py`, plus the WP1 tests of §8.1

**Owns (edits):**

- `app/models/user.py`, `app/models/booking.py`, `app/models/event.py`
  (`managers_share_lists`), `app/models/__init__.py`
- `app/crud/booking_reminder.py` (`replace_for_booking`, §4.5a; used by WP3 and WP4a)
- `app/core/config.py` (`SHARED_LISTS_ENABLED`, `GUEST_DATA_RETENTION_DAYS=30`,
  `GUEST_SIGNUPS_PER_ADDRESS_PER_DAY=20`, `GUEST_SIGNUP_EVENTS_PER_ADDRESS_PER_DAY=3`,
  `GUEST_MAILS_PER_ADDRESS_PER_DAY=10`, `GUEST_MAILS_PER_EVENT_PER_DAY=1000`,
  `GUEST_MAILS_PER_ORGANISER_PER_DAY=2000`, `SHARED_LIST_SIGNUPS_PER_LIST_PER_DAY=500`,
  `SHARED_LISTS_PER_EVENT=200`, and the Turnstile boot-warning validator of §5)
- `app/logic/permissions.py` (the §4.13 gates, including the sandbox test, the
  empty-scope 403, `managers_share_lists` and `require_claim_flag_allowed`)
- `app/api/api.py`
- `tests/conftest.py`
- `.env.example`, `docs/deployment.md`

**Accepted when:**

- `just check-migrations` is clean;
- the round trip `upgrade`, `downgrade -1`, `upgrade` works;
- basedpyright reports zero errors;
- the WP1 tests and the full `just test-backend` are green;
- the stubs import and register, and the OpenAPI schema is unchanged, because the
  stubs have no routes yet.

### WP2. Management API (after WP1, in parallel with WP3 and WP4)

**Owns:**

- `app/api/routes/shared_lists.py` (after the handoff)
- `app/schemas/shared_list.py`
- `app/crud/shared_list_overview.py`
- `app/logic/shared_lists/manage.py` (`transition`, `validate_selection`, bulk)
- edits to `app/api/routes/events.py` (shift-dates `ends_on`; `decorate_events`
  `managed_task_count`; `managers_share_lists` in `_NOT_NULL_SETTINGS`),
  `app/schemas/event.py` (`managed_task_count`; `managers_share_lists` in `EventRead`
  and `EventUpdate`) and `app/crud/task_manager.py` (`count_by_event_for_user`)
- tests `tests/api/routes/test_shared_lists*.py`, `tests/logic/test_shared_list_manage.py`

**Accepted when:**

- every WP2 case in §8.1 passes;
- `uv run --directory backend basedpyright` is clean;
- the OpenAPI at `/docs` shows the endpoints of §6.1 with the function names listed;
- no N+1: a test asserts the number of statements for the lists endpoint with 20 lists
  (an SQLAlchemy `before_cursor_execute` counter) is constant.

### WP3. Public sign-up, guest lifecycle, claim, retention (after WP1)

**Owns:**

- `app/api/routes/shared_list_guests.py`, `public_shared_lists.py` and `guest_claims.py`
  (after the handoff)
- `app/schemas/public_shared_list.py` (§6.3, §6.4) and `app/schemas/shared_list_guest.py`
  (§6.2, with its own `SharedListSignupSkip {id, code}`)
- `app/logic/shared_lists/signup.py`, `guest_tokens.py` (manage token and address
  hash), `guest_quota.py` (`admit_signup`, `reserve_mail`, suppression), `guest_mail.py`,
  `erase.py`, `removal.py`, `claim.py`, `retention.py`, `signups_query.py`
- edits to:
  - `app/core/rate_limit.py`, `app/core/turnstile.py`
  - `app/logic/notifications/service.py` (guest branch)
  - `app/logic/notifications/channels/base.py` (prefix)
  - `app/logic/notifications/reminder_poller.py` (sweep hook)
  - `app/logic/auth/service.py` (`build_user_profile`)
  - `app/schemas/users.py` (`claimable_guest_signups`)
- the WP3 tests of §8.1

**Accepted when:**

- every WP3 case passes, including the concurrency tests run three times in a row;
- mails render in en and de, checked against the mailcatcher with
  `just dev local` + `http://localhost:1080`;
- basedpyright is clean.

### WP4. Hardening of existing code (WP4a, after WP1) + developer docs (WP4b, after WP2, WP3 and WP4a)

**Owns (edits):**

- `app/api/deps.py` (the unconditional guest refusal)
- `app/crud/user.py`
- `app/api/routes/bookings.py` (lock, savepoint, `replace_for_booking` on rebooking,
  PATCH cancel), `app/api/routes/shifts.py`, `app/api/routes/tasks/crud.py`,
  `app/api/routes/reporting.py`, `app/api/routes/testing.py`
- `app/schemas/booking.py`, `app/schemas/shift.py`, `app/schemas/work_hours.py`
  (`VolunteerHours`, l.39)
- `app/crud/booking.py`
- `app/logic/vouchers.py` (guests settled at 0, not filtered), `app/logic/work_hours.py`
- tests: extensions of the existing files listed in §8.1
- WP4b docs: `docs/SHARED_LISTS.md` (new), `CLAUDE.md`, `docs/SANDBOX.md`,
  `docs/AUTH.md`, `docs/VOUCHERS.md`, `docs/PEOPLE_IN_CHARGE.md`, `docs/SECURITY.md`,
  `docs/plans/2026-04-18-public-guest-booking.md` (one header line)

**Accepted when:**

- every WP4 case passes;
- the existing booking and voucher suites stay green (`tests/api/routes/test_booking*.py`,
  `test_voucher*.py`, `tests/logic/test_voucher*.py`);
- basedpyright is clean;
- the docs describe the merged code. Every function name cited in them exists, which
  is checked with `rg`.

### WP5. Frontend shell and table kit (after WP2, WP3 and WP4a have merged)

**Owns:**

- the regenerated `frontend/src/client/**` (`just generate-client`)
- `src/router/routes.ts`, `src/router/index.ts`, `src/lib/page-head.ts` (+ spec)
- `src/components/navigation/AppSidebar.vue`, `MobileBottomNav.vue` (+ specs)
- `src/components/data-table/*` (new) and their specs
- `src/composables/useTableQuery.ts`, `useRowSelection.ts` (+ specs)
- `src/lib/shared-lists.ts` (+ spec)
- `src/composables/useAuthenticatedClient.ts`, `useAppConfig.ts`
- `frontend/docker-entrypoint.sh`
- `src/locales/{en,de}/navigation.json` (incl. `breadcrumbs.guestClaims`),
  `common.json`, `errorCodes.json`
- `src/views/admin/UsersView.vue`, `AdminEventsView.vue` (`ListPagination` swap only)
- `frontend/e2e/helpers/api.ts`
- stubs, handed off afterwards: `src/views/shared-lists/SharedListsView.vue` → WP6;
  `SharedListWizardView.vue` → WP7; `src/layout/GuestLayout.vue`,
  `src/views/guest/SharedListPublicView.vue`, `GuestSignupManageView.vue`,
  `GuestClaimsView.vue`, `src/components/guest/PublicListPreview.vue` (props
  `{ list: PublicSharedList }`) → WP8

**Accepted when:**

- all the frontend gates in the command list above pass (eslint, locales, both
  type-checks, `test:unit:coverage`, `build-only`);
- the existing E2E `chromium` project is green;
- the sidebar link appears for an event admin and for a person in charge, and not
  for a plain member.

### WP6. Management page, detail dialog, guest tags (after WP5)

**Owns:**

- `src/views/shared-lists/SharedListsView.vue` (after the handoff)
- `src/components/shared-lists/*` except `wizard/` (including
  `SharedListRemoveSignupsDialog.vue` and `SharedListManagersSwitch.vue`)
- `src/stores/sharedLists.ts` (+ spec)
- `src/locales/{en,de}/sharedLists.json`
- edits to `src/components/tasks/ShiftRoster.vue`, `ShiftBookingsTable.vue`,
  `ShiftDetailDialog.vue`, `src/views/bookings/BookingDetailView.vue` and
  `src/components/events/EventHours.vue`
- E2E `tests/authenticated/shared-lists-manage.spec.ts`,
  `tests/multi-user/shared-lists-people-in-charge.spec.ts`,
  `tests/mobile/shared-lists.spec.ts`, and the edit to
  `tests/a11y/admin-routes.spec.ts`

**Accepted when:**

- the frontend gates pass;
- `--project=chromium`, `--project=multi-user`, `--project=mobile` and
  `--project=a11y` pass for its specs;
- a manual check at 375 px width shows no horizontal scroll and the bulk bar clear of
  the bottom nav.

### WP7. Create/edit wizard (after WP5, in parallel with WP6 and WP8)

**Owns:**

- `src/views/shared-lists/SharedListWizardView.vue` (after the handoff)
- `src/components/shared-lists/wizard/*`
- `src/lib/shared-list-selection.ts`, `src/lib/shared-list-share-message.ts` (+ specs)
- `src/composables/useSharedListWizardApi.ts` (+ spec)
- `src/locales/{en,de}/sharedListWizard.json`
- E2E `tests/authenticated/shared-list-wizard.spec.ts`

**Accepted when:**

- the frontend gates pass;
- the wizard E2E passes;
- the selection spec covers every case of correction (a) listed in §7.4.

### WP8. Public and guest UI, claim, infrastructure, user-facing copy (after WP5; merges last)

**Owns:**

- `src/layout/GuestLayout.vue`, `src/views/guest/*`, `src/components/guest/*` (after the
  handoff)
- `src/stores/guestSignup.ts`, `guestClaim.ts` (+ specs)
- `src/locales/{en,de}/guestSignup.json`, `preauth.json`, `duties.json`
- edits to `src/views/HomeView.vue` and `src/views/events/SelectEventView.vue`
  (banner mounts), `src/views/auth/RegisterView.vue`
  (`?email=` prefill), `src/views/preauth/PrivacyView.vue`,
  `src/lib/content-pages.ts` and `src/components/landing/LandingFeatures.vue`
- `frontend/src/docs/{en,de}/**` (§9)
- `frontend/src/changelog/{en,de}/*_v0.29.0.md` and images
- `README.md`
- `frontend/nginx/default.conf`, `frontend/scripts/prerender.mjs` (robots line only)
- `frontend/playwright.config.ts` (`guest` project)
- E2E `tests/guest/*`, `tests/a11y/guest-pages.spec.ts`,
  `tests/mobile/shared-list-public.spec.ts`,
  `tests/authenticated/guest-claim.spec.ts`, the edit to
  `tests/public/content-pages.spec.ts`
- `frontend/e2e/COVERAGE.md` (final regeneration)

**Accepted when:**

- the frontend gates pass, including `docs-content.spec.ts`, `seo.spec.ts` and
  `wording.spec.ts`;
- `--project=guest`, `--project=public`, `--project=a11y` and `--project=mobile` pass;
- `pnpm --prefix frontend generate-changelog` lists 0.29.0 in both languages;
- `pnpm --prefix frontend build-only` writes a `robots.txt` with
  `Disallow: /guest-signup` and no `/l/` line;
- `/l/<code>` is absent from `dist/sitemap.xml` and `llms.txt`;
- COVERAGE.md is regenerated and committed.

---

## 11. Open questions for the product owner

Each has a recommended default, which the plan already assumes.

1. **Should event admins' lists let guests join the event by claiming?** A claim
   makes the person a `member`, who sees every published task and the member list
   with email addresses (events.py:1405-1426). So it is offered only on lists where
   an event admin ticked "Wer sich hier einträgt, kann mit einem Konto später der
   Veranstaltung beitreten" (D4); people in charge cannot. Sign-ups on other lists
   stay guest sign-ups (manage link only), and no upsell is shown there.
   *Default: the option exists, is off by default, and only event admins can switch
   it on per list.*
2. **How long do we keep guest data?**
   *Default: anonymise 30 days after the guest's last shift (`GUEST_DATA_RETENTION_DAYS`,
   §4.15). Bookings stay counted anonymously.*
3. **Voucher tasks on lists.**
   *Default: allowed. A shift that ends while a guest holds it earns nothing, ever,
   and the wizard says so. After a claim, shifts that end later earn like any
   account booking; shifts that ended before the claim stay at 0 ("earned is
   earned", D10).*
4. **Terms of Service and privacy roles.** The Terms still say an account is required
   (L:818, 850, 854), and changing them triggers the four-week notice mail to every
   account holder (L:833). The privacy text also needs one sentence on who is
   responsible for guest data (operator as controller of the platform, organisers
   deciding what a list asks for), which someone responsible for the legal texts
   must confirm before release.
   *Default: leave the Terms unchanged in 0.29.0. Cover guests in the privacy policy
   and the notice on the form, with the operator named as controller, and amend the
   Terms with the next planned notice.*
5. **Naming.** "Geteilte Listen" sits next to the existing invitation "Geteilte Links".
   *Default: rename the invitation links to "Einladungslinks" / "Invitation links"
   everywhere (UI and docs).*
