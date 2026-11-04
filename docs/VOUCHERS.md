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
task.not_found`), then the gate, then the flag (`422 voucher.not_a_point`). The
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
   current member (`404 event.member_not_found`), so a former member's balance
   can be corrected but not redeemed.
2. `crud_voucher.lock_ledger`.
3. Look for an earlier result with this `request_id`.
4. Read the pass again under the lock (`reload_pass`). The first read is in the
   identity map from before the lock, and the code may since have been used or
   replaced.
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

A correction can target a current member, or anyone with entries, settled
earnings or confirmed bookings in the event (`_appears_in_event`), which covers
every row of the overview. Settled earnings count on their own: deleting an
ended shift cancels the booking behind the earning.

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
- **Rate limits.** `voucher_code_limiter`, 60 a minute per redeemer on check and
  redeem with a code (a busy stand does about 25 people a minute, and 60 still
  makes guessing pointless). `voucher_pass_limiter`, 20 a minute for issuing.
  These are the in-process `RateLimiter`, so they do not count across workers.

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
  `logic/permissions.py`, which imports it. The routes run the gate.
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
