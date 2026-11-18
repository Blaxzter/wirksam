# Volunteer vouchers

Many events thank their volunteers with tokens for food and drinks, say two per
shift. In the app a task earns `vouchers_per_shift` for every worked shift, and
a task flagged `is_voucher_point` takes them: the volunteer shows a short code,
or someone allowed to picks their name from a list. The German UI says "Marken".
Neither UI says token, credit or ledger.

A voucher is a promise that may already be spent at a stand, and the design
follows from that. What someone earned does not shrink afterwards, every write
that lowers a balance is serialised, and a retry never takes anything twice.
There is no per-event switch: with no task earning and none taking, nothing
changes and the navigation hides the pages (`EventRead.voucher_task_count`,
`voucher_point_count`).

The code is in `app/logic/vouchers.py` (the numbers, redeeming),
`app/api/routes/vouchers.py` (routes, corrections), `app/crud/voucher.py` (rows,
the lock) and `app/models/voucher.py`; the gate is in
`app/logic/permissions.py`. The people who run a stand are described in
[`PEOPLE_IN_CHARGE.md`](PEOPLE_IN_CHARGE.md). Design notes:
[`plans/2026-10-30-task-managers-and-vouchers.md`](plans/2026-10-30-task-managers-and-vouchers.md),
amended by
[`plans/2026-11-02-people-in-charge-and-vouchers-followups.md`](plans/2026-11-02-people-in-charge-and-vouchers-followups.md).
Both are history: where they disagree with the code, the code is right.

## Who may redeem

`require_voucher_redeemer` is the one gate, and grepping for it finds every
check.

| Caller | With a code | Without a code (`manual=True`) |
|---|---|---|
| Event admin, superadmin | yes | yes |
| The point's people in charge | yes | yes |
| Confirmed booking on a shift of this task running now | yes | only while `events.voucher_manual_redeem` is `on_shift` (the default), else `403 voucher.manual_not_allowed` |
| Anyone else | `403 voucher.not_allowed` | `403 voucher.not_allowed` |

"Running" is `redeem_window`: from 30 minutes before the start to 30 minutes
after the end, on the event wall clock, and all day for a shift without times.
An overnight shift dated yesterday can still be running and a 00:15 shift opens
at 23:45 the day before, so `redeem_window_dates` widens the date range the
candidates are loaded from.

The routes check in a fixed order: the task is in this event (`404
task.not_found`), then the gate, then the flag (`422 voucher.not_a_point`), then
that the point isn't archived (`409 voucher.point_archived`): an archived point
has left the list, so it stops taking vouchers, and `can_redeem` says false. The
gate itself says nothing about whether the task is a point. Every voucher route
starts with `require_event_visible`, because `require_event_role` alone would
let the superadmin into someone's demo (see
[`SANDBOX.md`](SANDBOX.md#invisibility)).

**Why the default opens a door.** Showing a code is the volunteer's consent.
Picking from the list is for a dead phone or no smartphone, and under `on_shift`
a member who books a shift at a point anyone may book can spend other people's
vouchers. On a point with no rate of its own a running shift can be booked on
the spot. On one that earns, `booking.shift_started` stops that, but a shift
starting within 30 minutes can still be booked and is already inside its window.
What is left is tracing and choice: every manual redemption records `actor_name`
and `method="manual"`, the event settings say so under the option and suggest a
team on such points, and `in_charge` closes the door. The gate makes no team
check. The per-task volunteer desk in the original plan
(`tasks.is_voucher_desk`) is gone, dropped in migration `20261102_0002`.

The client reads the same answers from `VoucherPointRead.can_redeem`,
`can_redeem_manually` and `TaskRead.can_redeem`.

**Guests of shared lists are redeemed by code only.** The gate is about the
redeemer, always a member or an organiser. Whose vouchers are taken is decided
in `vouchers._holder_or_404`: a current member either way, and with a code
also a guest (`users.is_list_guest`) whose manage link is alive and who has a
part in the event (`vouchers.appears_in_event`). Showing the code is the
guest's consent to be named at the stand, as it is a member's. Picking from a
list stays members-only (`available_for_members`, the picker's
`/points/{task_id}/people`), so guests' names never reach the screen of
everyone on shift at a point. For a guest whose phone died, an event admin
books a negative correction instead. `VoucherCheckResult.is_guest` tags the
confirm sheet.

### What a redeemer can see

- **Counts in the redeem picker.** `GET
  /events/{id}/vouchers/points/{task_id}/people` answers what each current
  member can redeem, for whoever may redeem without a code at that point
  (`require_voucher_redeemer(manual=True)`, so the same two 403s otherwise). It
  returns the user id and `available` and nothing else; the picker takes names
  and faces from the member list. The organisers' `/vouchers/people` carries
  e-mail addresses and former members, so it stays admin-only and the picker
  does not use it. The counts are a convenience: `redeem` checks the balance
  again under its lock (`409 voucher.insufficient`).
- **A point's entries.** `.../points/{task_id}/entries`: admins and people in
  charge see every redemption, an on-shift redeemer only the ones they made. The
  totals (`today_*`, `total_*`) are counted in the database over the same rows,
  so `limit` does not cap them. "Today" is the event wall-clock day.

Who sees the names on a shift list is in
[`PEOPLE_IN_CHARGE.md`](PEOPLE_IN_CHARGE.md#who-sees-what-on-a-task).

## What someone has

```
balance   = earned - redeemed + adjusted
available = max(balance, 0)
```

The API reports `available`; the raw balance is not a field. Under today's rules
a balance never goes below zero, and the `max` guards rows written under older
ones.

Neither figure filters on membership or task status. Someone who worked and left
still worked, and an archived task's shifts still count. The [booking
rules](#booking-rules-that-exist-because-of-earnings) are what keep that honest.

Guests who signed up through a shared list earn exactly like members: the
derivation and `settle_earnings` do not ask who booked. A balance is one user's,
so a guest's is their guest user's: a sign-up chain's, or a guest account's
once the address was confirmed ([below](#guests-of-shared-lists)).

`vouchers.appears_in_event` is who has a part in an event: a current member, or
someone with entries, settled earnings worth something or confirmed bookings
there. The overview lists exactly these, corrections and `GET
/vouchers/people/{user_id}` admit them, and redeeming by code admits the guests
among them.

### Earned: derived until something would change it

An ended booking's vouchers are derived the way worked hours are:
`tasks.vouchers_per_shift` for every booking that
`work_hours.counts_as_worked()`, on a shift whose `shift_ends_at` has passed
`clock.wall_clock_now(event.timezone)`. Nothing is written when a shift ends.

Before anything would change that figure for a shift already over, the route
calls `vouchers.settle_earnings`. It freezes what the ended bookings earned in
`voucher_earnings`: one row per booking, with the amount at that moment and a
snapshot of the task and the shift. Reads (`_voucher_shifts`) add the settled
rows to the bookings not settled yet.

This is correct because of one invariant: **every ended, worked booking without
an earning row still derives today exactly what it earned when its shift
ended.** Time passing cannot break it, because a shift ends at the rate in
force, which stays the current rate until a rate change settles it. Every other
change settles first.

Hours do not work this way. Deleting a worked shift removes its hours and keeps
its vouchers: hours are a record organisers keep correcting, and nothing has
been handed out against them.

### What must settle first

| Route | Settles | Note |
|---|---|---|
| `PATCH /tasks/{id}` changing `vouchers_per_shift` | the task | `include_zero=True` |
| `PATCH /tasks/{id}` moving to another event | the task | earned stays in the source event |
| `DELETE /tasks/{id}` | the task | |
| `PATCH /shifts/{id}` changing `date`, `start_time` or `end_time` | the shift | |
| `DELETE /shifts/{id}` | the shift | |
| `DELETE /tasks/{id}/batches/{batch_id}` | the batch's shifts | |
| `POST /tasks/{id}/regenerate-shifts`, real run | the shifts about to go | kept shifts match on date and times, so their timing does not change |
| `POST /events/{id}/shift-dates` | the event's tasks | |
| `PATCH /events/{id}` changing `timezone` | the event's tasks | at the old zone's `now`: on the new clock a shift that ended may not have yet |
| `DELETE /users/me`, `DELETE /users/{id}` | tasks the account created | `tasks.created_by_id` cascades. A no-op on the admin route today, which refuses or hands the tasks over first |

**Anything new that changes what an ended booking earns must settle first**, in
the route's transaction, before the change, with the `now` the route uses.
Attendance (#177) is next: marking a no-show after the fact settles that booking
first, and taking its vouchers back is then an explicit correction.

Nothing needs settling for these:

- Cancelling or reactivating a booking on an ended shift is refused for
  everyone, admins included (`409 booking.shift_over`).
- Leaving an event cancels only unfinished bookings. The ended ones stay
  confirmed and derived.
- Deleting an event removes its voucher rows, and the sandbox purge removes
  everything.

### How settling behaves

- **Idempotent.** `ON CONFLICT (booking_id) DO NOTHING`: settling a booking
  twice, or from two requests at once, writes one row.
- **It takes no lock.** It turns a derived amount into the same stored amount,
  so no total changes. That depends on the read being one statement:
  `_voucher_shifts` is `settled UNION ALL derived`, one snapshot, so a
  settlement committing meanwhile is counted as one or the other, never both and
  never neither. Splitting it into two queries would break this.
- **A rate change writes zero rows.** `include_zero=True` also freezes bookings
  at rate 0, so raising a rate from 0 does not pay for shifts already over.
  Every other change skips tasks at 0. Zero rows are not listed or counted; they
  only keep the booking out of the derivation.
- **Final.** A settled booking stays out of the derivation for good, so a shift
  moved into the future and ending again cannot earn twice. The row counts
  whatever happens to the booking afterwards.
- **Running shifts are left alone.** A rate change applies to a shift still
  running.
- **Moving a task** leaves what was earned in the source event. Shifts not over
  yet move and earn in the target, where the booker may not be a member.

`VoucherShift.shift_id` and `task_id` are None once that shift or task is gone,
so the client does not link to it.

## Redemptions and corrections

`voucher_entries` holds what cannot be derived. A redemption is negative and
append-only (`409 voucher.entry_not_editable`). A correction is an event admin's
signed amount with a required reason, and may be edited or deleted.

### Redeeming

`logic/vouchers.redeem` is a logic function so the concurrency test can call it
on two sessions. The route has already run the gate. The order matters:

1. Find the volunteer: the code's owner, or the person picked. They must be a
   current member, or, by code only, a live guest with a part in the event
   (`404 event.member_not_found`), so a former member's balance can be
   corrected but not redeemed.
2. `crud_voucher.lock_ledger`.
3. Look for an earlier result with this `request_id`.
4. Read the pass again under the lock (`reload_pass`). The first read is in the
   identity map from before the lock, and the code may since have been used,
   replaced, or deleted by a guest's confirmation. A pass that no longer belongs
   to the volunteer is `409 voucher.code_expired`, a check of record a
   confirmation cannot reach, since it deletes codes rather than moving them.
5. Check `available` (`409 voucher.insufficient`, extension `available`).
   Nothing has been written yet, so a refusal does not rely on a rollback, which
   the test client would not perform. The code stays valid for a smaller amount.
6. Consume the pass and insert the entry. The unique indexes on `pass_id` and
   `request_id` are backstops the lock makes unreachable in practice.

**The advisory lock.** `lock_ledger` is `pg_advisory_xact_lock` on
`vouchers:{event}:{user}`. The balance is derived, so there is no row to lock
`FOR UPDATE`, and locking the user row would also block every insert that takes
a key-share lock on it (bookings, notifications). It is released at commit or
rollback, and under READ COMMITTED every statement after it sees what the
previous holder committed. A hash collision only serialises two unrelated
volunteers. Redemptions and corrections hold it, since they are the only writes
that lower a balance.

**`request_id`.** The client generates one per confirm and a retry reuses it, so
a retry whose response was lost returns the first result (`replayed: true`).
Manual redemptions have no pass to make them single use, so this is their only
protection against debiting twice. An id belonging to another redeemer or event
is `409 voucher.request_conflict`: a key the client chose must not let one
person read another's redemption.

### Corrections

`POST`, `PATCH` and `DELETE /events/{id}/vouchers/adjustments`, event admins
only, under `lock_ledger`. Whatever lowers the balance is capped at what the
person can still redeem (`409 voucher.correction_exceeds_available`): a negative
amount, a `PATCH` that lowers one, or deleting a positive correction whose
vouchers are already spent. Adding is always allowed.

`PATCH` and `DELETE` read the entry once for the lock's key, then again under
the lock (`_locked_adjustment`). Another organiser may have changed it while
this request waited, and checking against the stale amount could go below zero.

A correction can target anyone `vouchers.appears_in_event` admits, which covers
every row of the overview, guests included. Settled earnings count on their
own: deleting an ended shift cancels the booking behind the earning. The route
asks it under the ledger lock, so a correction racing a guest's merge lands
first and moves with it, or answers `404 event.member_not_found` once the chain
is gone.

## Codes

A `voucher_passes` row is six characters from an alphabet without look-alikes,
lives two minutes and works once. The QR code holds `WV1:` plus the code, and
`normalize_code` also takes lower case, dashes and spaces.

- **Unique across the installation.** A code from another event answers `409
  voucher.code_other_event` ("ask them to switch"), which `voucher.code_invalid`
  could not say.
- **Stored in plain text.** It lives two minutes, works once and is only
  accepted from someone allowed to redeem, and a hash of six characters adds
  nothing.
- **The hold.** `POST .../vouchers/check` stamps `checked_at`, and the code
  stays redeemable for `PASS_HOLD` (60 s) even if it runs out meanwhile, so a
  slow network between check and redeem never loses it. Only an unexpired code
  takes a new hold, so checking again and again cannot keep one alive: it is
  dead 60 s after its two minutes at the latest.
- **Issuing** inserts a row and deletes the person's other unused, unheld codes
  in the event. There is deliberately no unique constraint on `(event_id,
  user_id)`: two tabs issuing at once briefly leave two live codes, which is
  harmless, and a constraint would turn that race into a 500. Used passes stay,
  so the status poll can still say "redeemed".
- **The countdown** runs from `ttl_seconds` on receipt, never from `expires_at`
  against the device clock.
- **The check reads its pass again after the hold.** `check` takes no ledger
  lock, and `hold_pass` has no user filter. A check that read a guest chain's
  code just before a confirmation deleted it waits in `hold_pass` for that
  delete, then finds nothing: `404 voucher.code_invalid`, never the deleted
  chain's name.
- **Rate limits.** `voucher_code_limiter`, 60 a minute per redeemer on check and
  redeem with a code (a busy stand does about 25 people a minute, and 60 still
  makes guessing pointless). `voucher_pass_limiter`, 20 a minute for issuing.
  These are the in-process `RateLimiter`, so they do not count across workers.

**A guest's code.** A guest has no session, so their manage page asks through
public routes that the manage token opens (`app/api/routes/public_shared_lists.py`,
`logic/shared_lists/guest_vouchers.py`), under the members' rules:

| Route | Does | Limit |
|---|---|---|
| `POST /public/guest-signups/vouchers/pass` | `{token, event_id}` → 201 `VoucherPassRead`. `404 guest_signup.not_found` for an event in which the guest has no vouchers (`guest_vouchers.voucher_event_ids`) | `voucher_pass_limiter`, keyed `guest:<user id>:<kind>` (`mail` or `response`, [SHARED_LISTS.md](SHARED_LISTS.md#rate-limits)) |
| `POST /public/guest-signups/vouchers/pass-status` | `{token, event_id, pass_id}` → `VoucherPassStatus`; `404 voucher.pass_not_found` once replaced or deleted | `guest_pass_status_limiter`, 120 a minute per guest |

Both count per guest once the token resolves, and per IP only when it does not
(see [`SHARED_LISTS.md`](SHARED_LISTS.md#rate-limits)): the screen asks for the
status every two seconds, and a queue of guests behind one venue NAT must not
share a bucket. Any live token of a chain may ask; a guest account's codes are
only reached through mail tokens. A confirmation deletes the chain's unused
codes, promoted or merged: whoever only typed the address may hold one, and it
must never spend what the confirmation pools.

A code screen whose code vanished before its time (`voucher.pass_not_found` for
the code on screen: deleted by a confirmation, or replaced from another screen)
shows a new code at once, through whatever link it holds by then
(`VoucherCodeDialog.vue`). It does that once per opening; a second time it
offers "Try again" instead, so two screens of one person never take turns
deleting each other's codes. A dead link ends the screen for good
(`PassSourceGone`).

## Booking rules that exist because of earnings

Earnings follow bookings, so a hole in booking would be free vouchers
(`api/routes/bookings.py`):

| Rule | Refusal | Applies to |
|---|---|---|
| Must be a member of the task's event | `403 event.forbidden` | everyone but the superadmin |
| The task must be published | `403 task.not_published` | unless the caller can manage it |
| The shift must not have ended; also for cancelling and reactivating | `409 booking.shift_over` | every task, every caller |
| The shift must not have started | `409 booking.shift_started` | tasks that earn vouchers, unless the caller can manage the task |

`booking.shift_started` exists because vouchers are a flat amount per shift:
booking a 10:00–18:00 shift at 17:59 would pay the whole shift a minute later. A
shift without times counts as started at 00:00 of its day. Tasks that earn
nothing keep accepting bookings on running shifts, for helpers who turn up on
the day.

Booking holds the caller's membership row `FOR KEY SHARE` until commit
(`_lock_membership`). A leave committing at the same moment then waits, and its
clean-up (`cancel_unfinished_bookings_in_event`) sees and cancels the booking,
so a former member neither keeps a place on future rotas nor goes on earning.
Bookings on shifts already over stay, because that work happened.

The limits on people in charge (the shift history rule, voucher shifts) are in
[`PEOPLE_IN_CHARGE.md`](PEOPLE_IN_CHARGE.md#what-a-person-in-charge-may-do).

## Guests of shared lists

Someone who signs up through a shared list ([`SHARED_LISTS.md`](SHARED_LISTS.md))
is a guest user (`users.is_list_guest`), never a member, and earns like
everyone else. Nothing about guests needs settling first: a guest never takes a
shift that has started, their own cancel refuses a shift that is over (`409
booking.shift_over`), an organiser's removal skips one with that code, and
erasing keeps their confirmed bookings of ended shifts, without a name.

**Whose balance.** Earnings, entries and codes are keyed by user, so a guest's
balance is their guest user's:

- a **sign-up chain** (one visit to one list) holds its own vouchers. Any token
  of the chain shows a code for them, which covers guests without an address;
- a **guest account** is a chain whose address was confirmed through a mail
  link (`shared_list_guests.confirmed_at`), at most one per event and address.
  The first confirmation promotes its chain in place; every later one merges
  its chain into the account (`logic/shared_lists/guest_account.py`): bookings,
  reminders, earnings, entries and used codes move to the account's user, the
  unused codes are deleted, and the chain's user goes. One page then shows the
  pooled balance.

Moving a booking changes no amount, because ownership does not enter the
derivation, so a merge needs no settling, except in the defensive case of both
users confirmed on one shift, where it settles before it drops one booking.

**No-shows** earn, as no-show members do until attendance (#177) exists. The
organisers' tool is a negative correction.

**Expiry.** Unredeemed vouchers expire when a guest's data is anonymised (their
own erase, "Das war ich nicht", or `GUEST_DATA_RETENTION_DAYS` after their last
shift): the manage link goes, so no code can be shown. The organisers still see
the amount on the anonymous row and can correct it to 0.

## Settings

| Column | Default | Meaning |
|---|---|---|
| `events.voucher_manual_redeem` | `on_shift` | `on_shift`: whoever is on shift at a point may also pick a person there. `in_charge`: only admins and people in charge may |
| `events.managers_edit_voucher_shifts` | `false` | May people in charge change the shifts of a task that earns vouchers? See [`PEOPLE_IN_CHARGE.md`](PEOPLE_IN_CHARGE.md#shifts-of-a-task-that-earns-vouchers) |
| `tasks.vouchers_per_shift` | `0` | 0 to 50; 0 earns nothing |
| `tasks.is_voucher_point` | `false` | Vouchers can be redeemed here |

The event rules are set by event admins through `PATCH /events/{id}`, in the
event settings' Vouchers tab (`?tab=vouchers`,
`components/events/EventVoucherSettings.vue`). A new event starts with the
defaults, and an explicit `null` in a `PATCH` leaves the value. The task fields
are in `ADMIN_ONLY_TASK_FIELDS`. Cloning an event copies all four, and never
entries, earnings or codes. `events.timezone` is the zone every shift comparison
in the event runs in.

## Gotchas

- **`logic/vouchers.py` does no gating.** It must not import
  `logic/permissions.py`, which imports it. The routes run the gate. It may
  import `crud.shared_list_guest`, plain CRUD, for the guest checks.
- **A guest user with ledger entries, or with earnings worth something, is
  never deleted**, by an erase or the retention sweep: the CASCADE would take a
  stand's redemptions, and `point_totals`, with it. It is anonymised instead,
  and the notes of its corrections are cleared (a note is free text, and the
  natural one names the person); the amounts stay.
- **A merge takes both users' ledger locks, then the chain's `users` row.**
  `settle_earnings` takes no lock, and `voucher_earnings.booking_id` has no
  foreign key, so the `users` row is the only thing that orders a settle
  against the merge: an earning inserted first moves with the rest, one that
  comes later fails its foreign key and the organiser retries. Taken before the
  ledger locks, it would deadlock with a redemption that inserts its entry
  under that row's key-share lock.
- **Two clocks.** Shift comparisons use `clock.wall_clock_now(event.timezone)`, stored
  timestamps `clock.utc_now()`, and `redeem` and `check` take both. Comparing a
  shift with UTC would make a shift that ends at 18:00 end at 20:00 in a German
  summer. `VoucherShift.ends_at` is converted (`clock.wall_clock_to_utc`), so shifts and entries
  sort on one time line. Tests patch `app.logic.clock.wall_clock_now`.
- **No foreign key to a task, shift, booking, actor or pass** in
  `voucher_entries` or `voucher_earnings`. A CASCADE would refund a debit along
  with a deleted point, or take an earning along with its shift, and SET NULL
  next to `event_id` is the trap in
  [`backend/app/models/CLAUDE.md`](../backend/app/models/CLAUDE.md). Names are
  snapshots. Add neither.
- **The day after the event.** The router's selected-event guard blocks event
  pages once `end_date` has passed, the redeem page included, so an after-party
  that takes vouchers needs the end date to cover it. "My vouchers" is exempt
  (`SELECTED_EVENT_EXEMPT_ROUTES`) and only reads by then.
- **Error codes.** Every `voucher.*` and `booking.*` code needs an entry in
  `frontend/src/locales/{en,de}/errorCodes.json`, or the raw backend string
  shows on screen.
