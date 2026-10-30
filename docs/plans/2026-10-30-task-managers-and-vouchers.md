# People in charge of a task, and volunteer vouchers

Two features on one branch (`feat/task-managers-and-credits`). The second one
uses the first: the people who run a stand are the ones who take its vouchers.

## Problem

**Running a task.** Only event admins can edit a task or touch its shifts. An
event with twenty stands either makes twenty people admin, which lets them
change everything including the member list, or sends every "can you add a
shift at the bar on Saturday" through the organisers. The person who runs
the drinks stand needs to manage the drinks stand and nothing else.

**Thanking volunteers.** Many events give volunteers tokens for food and
drinks, for example two per shift. Today that is paper, counted out by hand at
a volunteer desk with no record of who already got theirs. The app knows who
worked which shift. It can work out the balance and let a stand take tokens
without paper. A stand that doesn't want to use the app keeps taking paper.

## Decisions

### A. People in charge of a task

- **A task can have any number of people in charge** (`task_managers`, n:m).
  The English UI says "person in charge" / "people in charge", short label
  "In charge". German says "Verantwortliche" / "Verantwortlich". The English
  avoids "lead" (team leads), "organiser" (event admins in `teamLocks.json`)
  and "coordinator" (event admins in `duties.availability`). Code names follow
  the product owner's working term: `TaskManager`, `task_managers`,
  `require_task_manager`.
- **Separate from teams on purpose.** `tasks.team_id` decides who may *book*.
  People in charge *run* the task. A task can have a team, people in charge,
  both or neither. Teams answer "who may book" and people in charge answer
  "who can fix the rota", which are different people at most events.
- **People in charge must be event members.** Leaving the event, or being
  removed from it, deletes their rows, so re-joining does not quietly restore
  the right. This is the same rule as for team rows.
- **What they may do:** edit their task's name, description, dates, location
  (only an existing location of the event, or free text) and category. They
  may create, edit and delete its shifts and shift batches, add shifts, and
  regenerate shifts. They see contact details of the people booked on it.
  With feature B they may redeem vouchers at it if it takes vouchers.
- **The past belongs to the organisers (shift history rule).** Hours and
  vouchers are both derived from booked shifts that have ended, so whoever
  rewrites a booked shift's past rewrites other people's hours and vouchers.
  For a person in charge (`task_access == "manager"`), on every task:
  - a shift that **has started** and **has confirmed bookings** cannot be
    deleted (single delete, batch delete, or regenerated away), and its date
    and start time cannot change. Its end time may still move as long as the
    shift stays unfinished ("we're staying an hour longer");
  - a shift with confirmed bookings cannot be moved so that it ends at or
    before now, nor so that it starts at or before now. Moving only the start
    back ("since midnight, ends in a minute") leaves a shift that has not
    ended yet, but a minute later it has, with the whole back-dated length
    counted as worked.

  Both are refused with `403 task.shift_history_admin_only`. Event admins are
  not limited. This closes the instant ways to create vouchers (book a
  future shift, then move it into the past) and to wipe other volunteers'
  earned vouchers or hours (delete a worked shift). Creating a shift that
  has already ended needs no rule: nobody can book it (see "Earning requires
  real membership and honest timing"). Creating one that is already running
  is not limited either; see "What this does not prevent".
- **What stays with event admins**, with reasons:
  - *Delete the task.* It removes the task for everyone, and the task isn't
    theirs to remove. (Deleting single future shifts stays possible; the
    shift history rule protects the worked ones.)
  - *Move it to another event.* That needs admin rights in both events
    anyway.
  - *Change `status`.* Publishing runs `dispatch_task_published`, which
    reaches **every active account on the installation**
    (`logic/notifications/triggers.py`). That is the event's call.
  - *Change `team_id`.* That decides who may book, so it stays with the
    admins, which is why teams and people in charge stay separate.
  - *Change `vouchers_per_shift` / `is_voucher_point` / `is_voucher_desk`
    (B).* Vouchers are currency, so the rate and the places that take them
    are the organisers' decision.
  - *Name or remove people in charge.* The one exception: a person in charge
    may step down themselves.
- **What this does not prevent.** Earnings are a flat amount per shift, and
  people in charge shape the future shifts of their task. Someone in charge of
  a voucher task can therefore still create many short future shifts and have
  friends who are event members book them; with one-minute shifts that pays
  out within minutes. The history rule does not stop this. What keeps it in
  check is that it is visible: the shifts appear on the task page, the
  bookings in its roster, and the earnings at the top of the organisers'
  voucher overview (sorted by available), where a correction undoes them.
  People in charge are trusted the way team leads are trusted to check
  certificates. The same goes for a shift created already running: a person
  in charge can add one at 14:00 that started at 00:00 and ends at 14:01, a
  member books it, and a minute later fourteen hours count as worked. A
  person in charge may need exactly that ("we forgot the morning setup
  shift"), so creating is not refused; the shift and its booking are visible
  the same way. Whether voucher tasks
  should instead keep shift creation with the organisers is the one open
  question for the product owner (see "Open question").
- **Per task, not per location.** Locations are optional. Responsibility for a
  whole location is a later extension (see "Not done").
- **One gate, in `app/logic/permissions.py`**, next to `require_event_role` and
  `require_team_manager`. Event admins and the platform superadmin pass it, as
  they pass every gate.
- **The retired global `task_manager` role gets cleaned up.** The backend
  stripped it in `20260821_0001`, but the admin user list still offers "Make
  Task Manager" (`UserRowActions.vue`). Next to a per-task "person in charge"
  that dead toggle would mislead, so frontend package A removes it. Backend
  tests that use "task manager" to mean "event admin" (in `test_shifts.py`,
  `test_reporting.py`, `test_user_ownership_transfer.py` and two docstrings
  in `test_tasks.py`; list under Tests) are renamed, so a grep for
  `task_manager` finds the new feature plus the historical migration and the
  fixture docstring that explains the retirement.

### B. Volunteer vouchers

The English UI says "vouchers". The German UI says "Marken", with the title
"Helfermarken" where context is needed. The UI never says "token", "credit" or
"ledger".

- **Earned vouchers are derived, never stored**, like worked hours
  (`logic/work_hours.py`). A volunteer earns `task.vouchers_per_shift` for
  every *confirmed* booking on a shift that has *ended*. The table stores only
  redemptions (debits) and manual adjustments by event admins (± corrections).
  - *Why not store grants?* A grant row has to be written when a shift ends.
    That needs a scheduler and idempotency, and nothing like it exists. It
    would also go stale whenever an admin corrects a shift's times.
  - Derived earnings follow every correction automatically, just as hours do.
    Attendance (#177) then becomes a one-line change: no-show bookings stop
    counting through one shared predicate.
- **Balances can go negative, and we accept that.** Several things lower what
  was earned after vouchers were spent: lowering `vouchers_per_shift`,
  deleting a past shift, or moving a shift into the future. `balance = earned
  + ledger` may then be below zero. The app shows `available = max(balance,
  0)` and refuses redemptions above it. The admin overview flags negative
  balances. The voucher settings show the hint "changes also count for shifts
  already worked".
- **No per-event on/off switch.** Everything already depends on per-task
  values. With no task earning vouchers and none taking them, nothing changes
  and the navigation entry stays hidden. A second switch would be one more
  place to forget, and turning it "off" while people still hold balances
  raises questions a switch cannot answer. `EventRead` carries two counts that
  the UI checks.
- **Redemption happens at tasks flagged as places that take vouchers**
  (`tasks.is_voucher_point`, "redemption point" in this document). Examples:
  - The central volunteer desk is a task like any other. Its staff redeem in
    the app and hand out paper vouchers.
  - A drinks stand that wants to take part is flagged and redeems directly.
  - A stand that doesn't want the app is simply not flagged and keeps taking
    paper from the desk.
  No stand is ever forced to use the app.
- **Who may redeem at a point:** event admins, its people in charge, and
  anyone with a confirmed booking on one of its shifts that is running now.
  "Running" includes 30 minutes before the start and 30 minutes after the end.
  An untimed shift runs all day.
- **Redeeming without a code** (picking the person from a list, for a dead
  phone or no smartphone) is for admins and people in charge, and for staff
  on shift at a point the organisers have marked as a **volunteer desk**
  (`tasks.is_voucher_desk`, admin-only, only meaningful together with
  `is_voucher_point`). Showing the code is the volunteer's consent, and the
  full member list is more than a drinks-stand volunteer needs; the desk is
  where people without a working phone are sent, so its staff need the list.
  "Staff" means approved members of the team that books the desk
  (`tasks.team_id`): being on shift is only a booking, and on a desk anyone
  may book, any member could book its running shift and spend every member's
  vouchers a minute later. A desk without a team therefore gives its on-shift
  staff no manual redemption (admins and people in charge keep it), and
  someone dropped from the team loses it even if an older booking remains.
  The redeem view tells an on-shift redeemer without that right who can help
  ("No phone? Ask Anna or Ben"), from the point's people in charge.
- **The code is a short-lived, single-use pass stored in the database.** It is
  6 characters from an alphabet without look-alikes, lives for 120 seconds,
  can be used once, and is unique across the installation, so a code shown in
  the wrong event can be recognised as such. The QR code holds the same code.
  Once a redeemer has checked a code it stays redeemable for 60 more seconds
  even if its two minutes run out, so a slow network between "check" and
  "redeem" never loses it. Only a check before expiry takes a hold, so
  checking again and again cannot keep a code alive: it is dead 60 seconds
  after its two minutes at the latest. Issuing a new code deletes the old one
  unless it is being redeemed at that moment. Reasons for a stored code:
  - Single use needs a database write either way, so a signed token (JWT)
    gains nothing.
  - A JWT is around 200 characters, which nobody can type.
  - A short code doubles as the "type it in" fallback.
  - The volunteer's screen can show "redeemed ✓".
- **Double spending is prevented with a transaction-scoped advisory lock per
  (event, volunteer)**. Reasons are given under "Redeeming".
- **Event wall-clock time for shift comparisons.** Shift dates and times are
  wall-clock times with no zone. Comparing them with naive UTC, as hours do
  today, makes an 18:00–22:00 stand shift "run" from 20:00 to 24:00 in a
  German summer. A volunteer who finishes at 18:00 would then wait two hours
  for their vouchers. So:
  - A new setting, `EVENT_TIMEZONE` (IANA name, default `Europe/Berlin`),
    drives a single helper, `clock.wall_clock_now()`.
  - The helper is used for "has this shift ended" (vouchers **and** hours, so
    the two always agree) and "is this shift running".
  - Stored timestamps stay naive UTC.
  - A timezone per event is out of scope.
- **Earning requires real membership and honest timing.** Pre-existing holes
  that would turn into free vouchers:
  - `POST /bookings/` does not check event membership. Booking now requires
    it: `403 event.forbidden`.
  - Anyone can book a shift that has already ended, or reactivate a cancelled
    booking on one.
  - Anyone can cancel a booking after the shift has ended (taking back
    vouchers already spent).
  - A member can book a shift of a draft or archived task: `GET /shifts/`
    without `task_id` lists them, `GET /shifts/{id}` only checks the event,
    and `create_booking` never looks at the task's status.
  - A member who leaves keeps their future bookings, which then go on
    earning.

  Booking, reactivating and cancelling an ended shift are refused with `409
  booking.shift_over` on **every** task, not only voucher tasks. Earnings are
  derived from the task's current `vouchers_per_shift`, so a shift booked
  after the fact on a task with 0 vouchers would start earning the moment an
  organiser sets a value ("changes also count for shifts already worked").
  A shift that is over can't be booked or cancelled in any meaningful sense,
  so the rule is general; organisers fix the past with hour and voucher
  corrections. The shared test fixtures date their shifts in the past
  (`tests/fixtures/shifts.py`: 2026-05-24), so the four test modules that
  book through the API pin the clock (see Tests). Booking a non-published
  task is refused with `403 task.not_published` unless the caller can manage
  the task. Leaving or being removed from an event cancels the person's
  confirmed bookings on its shifts that have not ended; the booking holds
  the caller's membership row `FOR KEY SHARE` (`lock_member_ids`), so a leave
  running at the same moment cannot miss a booking still in flight.

  On a task with `vouchers_per_shift > 0`, a shift that **has started**
  (`combine(date, start_time or 00:00) <= now`, the shift history rule's
  "started") cannot be booked or reactivated either: `409
  booking.shift_started`, unless the caller can manage the task. Refusing
  only ended shifts left the late booking open: vouchers are a flat amount
  per shift, so booking a 10:00–18:00 shift at 17:59 paid the whole shift a
  minute later, and an untimed shift (which counts as worked at midnight and
  never clashes with another untimed one) booked at 23:58 did the same for
  every such shift of the day. Tasks without vouchers keep accepting
  bookings on running shifts, for helpers who turn up on the day.

## Data

Two migrations, so that package A can merge without B:

| Revision | File | down_revision |
|---|---|---|
| `20261030_0001` | `20261030_0001_add_task_managers.py` | `"20261027_0001"` (current head) |
| `20261030_0002` | `20261030_0002_add_volunteer_vouchers.py` | `"20261030_0001"` |

`env.py` takes the revision id from the date of generation. If B is generated
on a later day its id changes, but its `down_revision` must still be A's
revision. Each migration starts with the house docstring (why, in user terms,
then `Revision ID / Revises / Create Date`) and needs a round trip
(`upgrade`, `downgrade -1`, `upgrade`, `alembic check`).

Every table below inherits `Base`: `id` (uuid PK, indexed as `ix_<table>_id`),
plus `created_at` and `updated_at` (`sa.DateTime`, naive UTC, NOT NULL).

### `task_managers` (A, `app/models/task_manager.py`, class `TaskManager`)

| Column | Type | Null | FK / default | Index |
|---|---|---|---|---|
| `task_id` | Uuid | no | `tasks.id` **ON DELETE CASCADE** | `ix_task_managers_task_id` |
| `user_id` | Uuid | no | `users.id` **ON DELETE CASCADE** | `ix_task_managers_user_id` |
| `added_by_id` | Uuid | yes | **no FK** | – |
| `added_by_name` | String | yes | – | – |

- `__table_args__ = (sa.UniqueConstraint("task_id", "user_id", name="uq_task_manager_task_user"),)`.
- **No ORM `Relationship`** from `Task` or `User`. Without `passive_deletes`,
  `session.delete(task)` would make the ORM null the FK, which violates NOT
  NULL. CASCADE lives in the database only, like `event_team_members`.
- `added_by_id` has no FK for the same reason as `WorkLog.created_by_id`: a
  CASCADE would remove the grant when the granting admin deletes their
  account, and SET NULL is the trap in `app/models/CLAUDE.md`.
- Unit-of-work order: `app.models.task_manager.TaskManager` sorts before
  `app.models.user.User`, so flush new users (seeds, tests) before adding
  manager rows.

### `tasks` (B)

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `vouchers_per_shift` | Integer | no | `0`, `server_default="0"` | 0 = none. Schemas allow 0–50. `sa.CheckConstraint("vouchers_per_shift >= 0", name="ck_tasks_vouchers_per_shift_non_negative")` in a new `Task.__table_args__` and in the migration |
| `is_voucher_point` | Boolean | no | `False`, `server_default=sa.text("false")` | "Vouchers can be redeemed here" |
| `is_voucher_desk` | Boolean | no | `False`, `server_default=sa.text("false")` | "Staff on shift can also redeem without a code" (the volunteer desk). Writes force it to `False` when `is_voucher_point` ends up `False`; the redeem gate also checks both |

### `voucher_entries` (B, `app/models/voucher.py`, class `VoucherEntry`)

The stored half of a balance. Rows are append-only except adjustments, which
event admins may edit or delete.

| Column | Type | Null | FK | Notes |
|---|---|---|---|---|
| `event_id` | Uuid | no | `events.id` **CASCADE** | indexed `ix_voucher_entries_event_id` |
| `user_id` | Uuid | no | `users.id` **CASCADE** | the volunteer, indexed `ix_voucher_entries_user_id` |
| `kind` | String(16) | no | – | `redemption` \| `adjustment` |
| `amount` | Integer | no | – | signed: redemption < 0, adjustment ≠ 0 |
| `method` | String(16) | yes | – | redemptions: `code` \| `manual` |
| `note` | Text | yes | – | required for adjustments (the reason) |
| `task_id` | Uuid | yes | **no FK** | the redemption point |
| `task_name` | String | yes | – | snapshot, still shown after the task is deleted |
| `actor_id` | Uuid | yes | **no FK** | who redeemed or adjusted |
| `actor_name` | String | yes | – | snapshot (`user.name or user.email`) |
| `pass_id` | Uuid | yes | **no FK** | `unique=True, index=True` → one unique index `ix_voucher_entries_pass_id` (backstop for single use; NULLs are distinct) |
| `request_id` | Uuid | yes | – | redemptions: the client's idempotency key. `unique=True, index=True` → `ix_voucher_entries_request_id`. A retried redemption returns the first result instead of debiting twice |

`__table_args__`:
- `sa.Index("ix_voucher_entries_event_id_user_id", "event_id", "user_id")`
- `sa.Index("ix_voucher_entries_event_id_task_id", "event_id", "task_id")`
- `sa.CheckConstraint("kind IN ('redemption', 'adjustment')", name="ck_voucher_entries_kind")`
- `sa.CheckConstraint("amount <> 0", name="ck_voucher_entries_amount_nonzero")`
- `sa.CheckConstraint("kind <> 'redemption' OR amount < 0", name="ck_voucher_entries_redemption_negative")`

`alembic check` does not compare CHECK constraints, but write them in the
model and in the migration anyway.

`task_id` deliberately has no FK. A CASCADE would delete the debits along
with a deleted point task, which refunds them. SET NULL is not safe either:
`tasks.created_by_id` is `ON DELETE CASCADE`, so deleting a user who created
both the event and the point task removes the event and the task in one
statement, and a SET NULL on `task_id` would re-check `event_id` against the
event already gone. That is the trap in `app/models/CLAUDE.md`, reached
through a task instead of a user FK. No FK plus a name snapshot, as on
`WorkLog` and `decided_by_*`, avoids it. Never put SET NULL on any FK in this
table.

### `voucher_passes` (B, same file, class `VoucherPass`)

| Column | Type | Null | FK | Notes |
|---|---|---|---|---|
| `event_id` | Uuid | no | `events.id` **CASCADE** | indexed |
| `user_id` | Uuid | no | `users.id` **CASCADE** | indexed |
| `code` | String(6) | no | – | plain text (see below) |
| `expires_at` | DateTime | no | – | `sa.Column(sa.DateTime, nullable=False)`, naive UTC |
| `checked_at` | DateTime | yes | – | naive UTC; set by a successful `check`, holds the pass for `PASS_HOLD` |
| `used_at` | DateTime | yes | – | naive UTC |

`__table_args__`:
- `sa.UniqueConstraint("code", name="uq_voucher_passes_code")`. Unique across
  the installation, not per event: a redeemer in event B who scans a code
  issued in event A gets `409 voucher.code_other_event` ("ask them to switch
  to this event") instead of a useless "invalid code". 31⁶ ≈ 887 million
  codes against a few dozen live ones, with the retry in `issue_pass`.
- `sa.Index("ix_voucher_passes_event_id_user_id", "event_id", "user_id")`

Notes:
- There is **no unique constraint on (event_id, user_id)**. Issuing a pass
  inserts a row and then deletes the user's other *unused, unheld* passes in
  that event. Two tabs issuing at once can briefly leave two live codes,
  which is harmless. A unique constraint would turn that race into a 500.
- Used passes are kept (one row per redemption, like the ledger), so the
  volunteer's status poll can still report "redeemed" after a new code was
  issued. They go with the event or the user.
- The code is stored in plain text. It lives two minutes, works once, and is
  only accepted by someone allowed to redeem at a point. A 6-character code
  could be brute-forced offline anyway, so hashing would add nothing.
- Register `TaskManager`, `VoucherEntry` and `VoucherPass` in
  `app/models/__init__.py` (imports and `__all__`) so autogenerate sees them.

## Who can do what

| Action | Who |
|---|---|
| See a task, its people in charge, its shifts and booked names | event members (drafts and archived tasks: event admins and its people in charge; a booker can always open their own shift and its roster) |
| Book a shift | event members, on published tasks only (admins and people in charge also on drafts); never once the shift has ended; on a task that earns vouchers, not once it has started (its people in charge and admins still can) |
| Edit name, description, dates, location, category; create, edit and delete shifts and batches; add and regenerate shifts | its people in charge, event admins (people in charge within the shift history rule) |
| Change or delete a booked shift that has started, or move a booked shift into the past | event admins |
| See phone and notes of the people booked on its shifts | its people in charge, event admins (and each booker their own row). E-mail is redacted in the same places, but this is partial: `GET /events/{id}/members` already shows every member's e-mail to every member |
| Change status, team, voucher settings; move to another event; delete the task | event admins |
| Name or remove people in charge | event admins; a person in charge may remove themselves |
| See own vouchers, show own code | event members |
| Redeem with a code at a point | event admins, its people in charge, anyone on a running shift there (±30 min) |
| Redeem without a code (pick the person) | event admins, its people in charge, staff on a running shift at a point marked as volunteer desk who are approved members of its team (`team_id`) |
| See one person's available vouchers | whoever checks them at a point (needed to choose the amount) |
| See redemptions made at a point | event admins, its people in charge; on-shift redeemers see their own |
| See everyone's balance, add/edit/delete corrections | event admins |

The platform superadmin passes every check. Sandboxes stay hidden from them
through `require_event_visible`, and through the new sandbox clause in
`require_task_visible`.

### New gates in `app/logic/permissions.py`

```python
TaskAccess = Literal["admin", "manager"]

async def task_access(user: User, session: AsyncSession, task: Task) -> TaskAccess | None:
    """'admin' for event admins/owner/superadmin, 'manager' for a person in charge
    who is still an event member, else None. task.event_id None -> superadmin only."""

async def can_manage_task(user: User, session: AsyncSession, task: Task) -> bool:
    return await task_access(user, session, task) is not None

async def require_task_manager(user: User, session: AsyncSession, task: Task) -> TaskAccess:
    """Raise 403 task.forbidden unless can_manage_task. Returns the level so the
    caller can refuse admin-only fields."""

async def require_task_visible(
    user: User, session: AsyncSession, task: Task, *, booked_shift_id: uuid.UUID | None = None
) -> EventRole:
    """The read gate for one task. 404 task.not_found for a task in a sandbox event
    the caller did not create, decided on the event and not on Task.is_sandbox
    alone (checked first: get_event_role reports the superadmin as owner), or
    when the caller has no role in the task's event. 403
    task.not_published for a non-published task unless task_access() is not None,
    or unless booked_shift_id is given and the caller has a booking (any status)
    on that shift: a volunteer can always reopen their own booking after the
    organisers archive the task."""

def check_shift_history(
    access: TaskAccess, *, before: Shift, has_bookings: bool,
    new_date: dt.date | None = None, new_start: dt.time | None = None,
    new_end: dt.time | None = None, deleting: bool = False, now: dt.datetime,
) -> None:
    """The shift history rule. No-op for 'admin'. For 'manager': 403
    task.shift_history_admin_only when a booked shift that has started would be
    deleted or get a new date or start time, or when a booked shift would start
    (after a new date or start time) or end at or before ``now`` (event wall
    clock, logic/clock.wall_clock_now).
    'Started' is combine(date, start_time or 00:00) <= now; 'ends' is
    work_hours.shift_ends_at. Pure, so the routes pass in has_bookings.
    Creating shifts never calls it: nobody can book a shift that has ended."""
```

`check_shift_history` is the one place the rule lives. Callers:
- `PATCH /shifts/{id}`: when `date`, `start_time` or `end_time` is in the
  body, with the shift's confirmed-booking count;
- `DELETE /shifts/{id}` and `DELETE /tasks/{id}/batches/{batch_id}`: for each
  shift, with `deleting=True`;
- `POST /tasks/{id}/regenerate-shifts`, **not** in dry run: for each shift in
  `shifts_to_delete`, with `deleting=True`. The dry run reports the refused
  shifts instead (`AffectedBookingInfo.locked: bool`), so the editor can warn
  before the person in charge confirms.

Package A needs `clock.wall_clock_now()` for this, so `app/logic/clock.py`
and `EVENT_TIMEZONE` move from Backend B step 1 into Backend A (see
Implementation order).

`task_access` follows the shape of `can_manage_team`. First
`get_event_role`. With `role_at_least(role, "admin")` the result is
`"admin"`. With `role is None` the result is `None`, so a stale row of someone
who left grants nothing. Otherwise the result is `"manager"` if
`crud_task_manager.is_manager(session, task_id=…, user_id=…)` holds.

Feature B adds a further gate in the same file:

```python
RedeemerKind = Literal["admin", "manager", "on_shift"]

async def voucher_redeemer_kind(
    user: User, session: AsyncSession, task: Task, *, now: dt.datetime
) -> RedeemerKind | None:
    """task_access() first; then, for an event member, a confirmed booking on a
    shift of this task whose redeem window (logic/vouchers.redeem_window) contains
    ``now`` (event wall clock). The candidate shifts are loaded with
    logic/vouchers.redeem_window_dates(now): the dates from
    (now - REDEEM_GRACE_AFTER - 1 day) to (now + REDEEM_GRACE_BEFORE), i.e.
    yesterday (overnight shifts) through tomorrow (a shift at 00:15 opens at
    23:45). ``now`` is always clock.wall_clock_now()."""

async def may_redeem_manually(
    user: User, session: AsyncSession, kind: RedeemerKind, task: Task
) -> bool:
    """admin/manager, or on_shift at a point that is a desk with a team_id
    whose approved members include the user (async: one team lookup)."""

async def require_voucher_redeemer(
    user: User, session: AsyncSession, task: Task, *, now: dt.datetime, manual: bool = False
) -> RedeemerKind:
    """403 voucher.not_allowed if voucher_redeemer_kind is None;
    403 voucher.manual_not_allowed if manual and not may_redeem_manually."""
```

`permissions.py` may import `app.crud.task_manager`, `app.crud.booking`,
`app.logic.work_hours.shift_ends_at`, `app.logic.clock` and
`app.logic.vouchers.redeem_window` / `redeem_window_dates`. To keep that free
of cycles, `app/logic/vouchers.py` and `app/logic/work_hours.py` must **not**
import `app.logic.permissions`, because the routes do the gating.

Update the module docstring of `permissions.py`, the "Auth Pattern"
section of `CLAUDE.md`, and the gate list in `backend/app/api/routes/README.md`
(which today says grepping `require_event_role` and `require_event_visible`
finds every check). Next to the team gates, add: "**People in charge**
(`app/api/routes/tasks/managers.py`) add `require_task_manager` (edit a
task's details and shifts; admin-only fields refused with `403
task.admin_only_field`; booked shifts that have started are the organisers'
through `check_shift_history`) and `require_task_visible` (reading one task;
drafts for admins and the task's people in charge). **Vouchers**
(`app/api/routes/vouchers.py`) add `require_voucher_redeemer`." Add a short
paragraph on how vouchers work, with a link to this plan.

### Existing call sites

**Switch to `require_task_manager`** (they call `require_event_role` today):

| File | Endpoint | Note |
|---|---|---|
| `api/routes/tasks/crud.py` | `PATCH /tasks/{task_id}` | plus the admin-only-field check below; moving still also calls `require_event_role` on the target event |
| `api/routes/tasks/shifts.py` | `POST /tasks/{task_id}/add-shifts` | |
| `api/routes/tasks/shifts.py` | `POST /tasks/{task_id}/regenerate-shifts` | plus the snapshot fix (edge cases) and `check_shift_history` on deletions |
| `api/routes/tasks/batches.py` | `DELETE /tasks/{task_id}/batches/{batch_id}` | plus `check_shift_history` per shift |
| `api/routes/shifts.py` | `POST /shifts/` | plus `batch.wrong_task` check (edge cases) |
| `api/routes/shifts.py` | `PATCH /shifts/{slot_id}` | plus `check_shift_history` |
| `api/routes/shifts.py` | `DELETE /shifts/{slot_id}` | plus `check_shift_history` |

The code a plain member or outsider gets on these changes from `403
event.forbidden` to `403 task.forbidden`. Existing assertions that check the
code need updating.

**Switch to `require_task_visible`.** These are inline copies of the same
check today, and the new gate replaces them:

| File | Endpoint |
|---|---|
| `api/routes/tasks/crud.py` | `GET /tasks/{task_id}` |
| `api/routes/tasks/feed.py` | `GET /tasks/{task_id}/shift-window` |
| `api/routes/shifts.py` | `GET /shifts/?task_id=` (the `if task_id:` block) |

**Get `require_task_visible` where they have no gate, or only the event
gate, today:**

| File | Endpoint | Extra rule |
|---|---|---|
| `api/routes/tasks/crud.py` | `GET /tasks/{task_id}/bookings` | `user_phone_number` only when `task_access()` is not None, else `None` |
| `api/routes/tasks/batches.py` | `GET /tasks/{task_id}/batches` | – |
| `api/routes/shifts.py` | `GET /shifts/{slot_id}` (today `require_event_visible` only) | `booked_shift_id=slot_id`, so a booker of an archived or unpublished task still opens their booking |
| `api/routes/shifts.py` | `GET /shifts/{slot_id}/bookings` (gate on the shift's task) | `booked_shift_id=slot_id`, as above. `user_email`, `user_phone_number` and `notes` only when `task_access()` is not None or the row is the caller's own, else `None` |

**`GET /shifts/` without `task_id`** lists every shift in the caller's
events today, drafts and archived tasks included. It gets the same status
filter as the task list: `crud_shift.get_multi_filtered` /
`get_count_filtered` take `status`, `also_include_event_ids` (the caller's
manageable events) and `also_include_task_ids` (the tasks they are in charge
of), applied in `_apply_event_scope` as `Task.status == status OR
Task.event_id IN (...) OR Task.id IN (...)`. The superadmin stays unfiltered
(sandboxes excluded as today). Every frontend caller passes `task_id`, so
nothing visible changes.

**`POST /bookings/`** (package B, see "Booking") refuses a task whose
`status != "published"` with `403 task.not_published` unless `task_access()`
is not None.

**Lists that also show the drafts of tasks the caller is in charge of.**
`crud/task.py::_apply_common_filters`, `get_multi_filtered` and
`get_count_filtered` get a new `also_include_task_ids: list[uuid.UUID] | None`.
Inside `if status:`, it is OR-ed into the status filter just like
`also_include_group_ids` is. `restrict_to_event_ids` stays a hard AND, so a
task in an event the caller has left never shows up. That `status` is the
visibility rule (always `"published"` for everyone but the superadmin), not
the caller's query parameter: `GET /tasks/?status=` goes into a separate
`only_status`, ANDed on top, so a member asking for `draft` gets none rather
than every draft in their events. Callers pass
`await crud_task_manager.task_ids_for_user(session, user_id=current_user.id)`:

- `GET /tasks/` (`list_tasks`)
- `GET /tasks/feed` (`task_feed`)

**Stay admin-only** (`require_event_role`, unchanged):

- `POST /tasks/` and `POST /tasks/with-shifts`: they create a task.
- `DELETE /tasks/{task_id}`.
- `events.py`: `shift-dates`, `clone`. (`task-date-bounds` is a read gated
  by `require_event_visible`, so it stays as it is; it reports draft task
  dates to anyone who can see the event, a pre-existing detail this plan
  leaves alone.)
- `work_hours.py` (everything except `GET /hours/{user_id}` for oneself,
  which already takes `minimum="member"`) and `reporting.py`
  (`_get_managed_task_ids`).
- `locations.py` and `venue_map.py` edits, and their draft-shift visibility.
- `GET /tasks/active-dates` draft dates.
- `teams.py`.
- Naming people in charge (`POST /tasks/{id}/managers`).
- All voucher admin routes.

### Admin-only fields in `PATCH /tasks/{task_id}`

```python
ADMIN_ONLY_TASK_FIELDS = ("status", "event_id", "team_id")  # B appends "vouchers_per_shift", "is_voucher_point"

access = await require_task_manager(current_user, session, db_task)
update_data = task_in.model_dump(exclude_unset=True)
if access == "manager":
    changed = [f for f in ADMIN_ONLY_TASK_FIELDS
               if f in update_data and update_data[f] != getattr(db_task, f)]
    if changed:
        raise_problem(403, code="task.admin_only_field",
                      detail="Only event admins can change this", extensions={"fields": changed})
    for f in ADMIN_ONLY_TASK_FIELDS:
        update_data.pop(f, None)   # sent unchanged: ignored
```

A field sent with its current value is ignored rather than refused, so a form
that always sends the whole task still works for a person in charge.

## API

All errors go through `raise_problem`. Every code below needs an entry in
`frontend/src/locales/{en,de}/errorCodes.json`; the wording is under
Frontend.

### A. People in charge (`app/api/routes/tasks/managers.py`, included in `tasks/__init__.py`)

| Method | Path | Gate | Body → Response |
|---|---|---|---|
| POST | `/tasks/{task_id}/managers` | `require_event_role(task.event_id, "admin")` | `TaskManagerAdd {user_id}` → **201** `TaskManagerBrief` |
| DELETE | `/tasks/{task_id}/managers/{user_id}` | admin, **or** `user_id == current_user.id` (stepping down) | → **204** |

Errors:
- `404 task.not_found`: no such task.
- `403 event.forbidden`: the caller is not an admin.
- `422 task.manager_not_event_member`: the person is not a member of the
  task's event, or the task has no event. The membership row is read
  `FOR KEY SHARE` (`crud_membership.lock_member_ids`, also used for
  `manager_ids` on create), so a concurrent leave waits for the grant and
  its clean-up removes it, instead of missing a row that would come back
  when the person re-joins.
- `409 task.manager_already`: the person is already in charge. Check first,
  then insert inside `begin_nested()` and map an `IntegrityError` to the same
  409.
- `404 task.manager_not_found`: on DELETE, the person is not in charge.

There is no separate list endpoint. `TaskRead.managers` is the list, and the
editor reloads the task after each change.

**Creating with people in charge.** `TaskCreateWithShifts` gets
`manager_ids: list[uuid.UUID] = []`. In `POST /tasks/with-shifts`, after the
task is created:
- deduplicate the ids;
- each one must be a member of `payload.event_id`, otherwise `422
  task.manager_not_event_member`;
- with `new_event` the list must be empty (same 422).

`TaskCreate` and `POST /tasks/` do not get the field. `TaskBase` is also the
base of `TaskRead`, so the field would leak into reads.

**Schemas** (`app/schemas/task_manager.py`):

```python
class TaskManagerAdd(BaseModel):
    user_id: uuid.UUID

class TaskManagerBrief(BaseModel):
    user_id: uuid.UUID
    name: str | None = None
    avatar_etag: str | None = None
```

**`TaskRead` additions** (`app/schemas/task.py`). These are viewer-relative,
like `locked_by_team`, and `FeedTaskItem` inherits them:

```python
#: True for event admins, the superadmin and the task's people in charge.
can_manage: bool = False
#: The task's people in charge, by name.
managers: list[TaskManagerBrief] = []
```

They are filled by `app/logic/task_managers.py`:

```python
async def mark_task_access(session, user, reads: Sequence[_TaskAccessEntry]) -> None
async def decorate_task_reads(session, user, reads) -> None   # mark_task_locks + mark_task_access
```

`mark_task_access` uses a fixed number of queries:
- one query loads every task's manager rows joined to `users` (ordered by
  name);
- one `get_event_role` per distinct event, as `team_locks` does.

Call `decorate_task_reads` wherever `mark_task_locks` runs today:
- `list_tasks`, `get_task` and `task_feed` (the feed calls only
  `mark_task_access` next to its existing lock code).

Also call it in the write routes, which currently return an undecorated row,
so that `can_manage` would read False right after an edit:
- `POST /tasks/` and `PATCH /tasks/{id}`: return a decorated `TaskRead`
  rather than the model;
- `with-shifts`, `add-shifts` and `regenerate-shifts`: decorate the `task`
  inside their response.

**`app/crud/task_manager.py`** (instance `task_manager`):
- `is_manager(session, *, task_id, user_id) -> bool`
- `task_ids_for_user(session, *, user_id) -> list[uuid.UUID]`
- `managers_for_tasks(session, *, task_ids) -> dict[uuid.UUID, list[tuple[TaskManager, User]]]`
- `user_ids_for_task(session, *, task_id) -> list[uuid.UUID]`, kept for help
  alerts later
- `add(session, *, task_id, user_id, added_by: User) -> TaskManager`
- `remove(session, *, task_id, user_id) -> bool`
- `remove_all_for_task(session, *, task_id)`
- `remove_user_from_event_tasks(session, *, user_id, event_id)`, copied from
  `crud/event_team.py::remove_user_from_event_teams`: delete where `user_id`
  matches and `task_id IN (SELECT id FROM tasks WHERE event_id = :event_id)`,
  then flush.
- `rows_for_clone(session, *, task_ids, user_ids) -> dict[uuid.UUID, list[TaskManager]]`

### B. Vouchers (`app/api/routes/vouchers.py`, `APIRouter(prefix="/events", tags=["vouchers"])`, registered in `api/api.py` after `work_hours`)

Every route starts with `event = await crud_event.get(...)` and
`require_event_visible`, the same as `work_hours._event_for`, so a sandbox
stays 404 even for the superadmin. Literal sub-paths are used throughout
(`me`, `people/{user_id}`) so that no `{user_id}` route can swallow `me`.

| Method | Path | Gate | Body → Response |
|---|---|---|---|
| GET | `/events/{event_id}/vouchers/me` | member | → `VoucherAccount` |
| POST | `/events/{event_id}/vouchers/me/pass` | member; `voucher_pass_limiter` per user | → **201** `VoucherPassRead` |
| GET | `/events/{event_id}/vouchers/me/pass/{pass_id}` | member, own pass only | → `VoucherPassStatus` |
| GET | `/events/{event_id}/vouchers/points` | member | → `list[VoucherPointRead]` |
| GET | `/events/{event_id}/vouchers/points/{task_id}/entries?limit=50` | `require_voucher_redeemer` on the point; `admin`/`manager` see every entry, `on_shift` only the ones they made (`actor_id == me`) | → `PointRedemptionList` |
| POST | `/events/{event_id}/vouchers/check` | `require_voucher_redeemer` (`manual` if `user_id`); `voucher_code_limiter` per user when a code is given | `VoucherCheckRequest` → `VoucherCheckResult` |
| POST | `/events/{event_id}/vouchers/redeem` | as `check` | `VoucherRedeemRequest` → **201** `VoucherRedeemResult` |
| GET | `/events/{event_id}/vouchers/people` | admin | → `list[VoucherBalance]` |
| GET | `/events/{event_id}/vouchers/people/{user_id}` | admin (for someone with a part in the event, as for corrections; else `404 event.member_not_found`), or self (member) | → `VoucherAccount` |
| POST | `/events/{event_id}/vouchers/adjustments` | admin | `VoucherAdjustmentCreate` → **201** `VoucherEntryRead` |
| PATCH | `/events/{event_id}/vouchers/adjustments/{entry_id}` | admin | `VoucherAdjustmentUpdate` → `VoucherEntryRead` |
| DELETE | `/events/{event_id}/vouchers/adjustments/{entry_id}` | admin | → **204** |

The `points` list holds the event's tasks with `is_voucher_point`: published
ones, plus drafts the caller can manage. `check`, `redeem` **and `points/{task_id}/entries`**
look the task up and require, in this order, `task.event_id == event_id`
(else `404 task.not_found`), then the gate, then `task.is_voucher_point`
(else `422 voucher.not_a_point`). The entries query filters on both
`event_id` and `task_id`.

`POST …/adjustments` accepts a `user_id` that is a current member **or** has
ledger rows or confirmed bookings in the event (else `404
event.member_not_found`), so an organiser can settle the balance of someone
who has left and still appears in the overview.

**Schemas** (`app/schemas/voucher.py`):

```python
VoucherEntryKind = Literal["redemption", "adjustment"]
VoucherRedeemMethod = Literal["code", "manual"]

class VoucherEntryRead(BaseModel):          # from_attributes
    id: uuid.UUID; kind: VoucherEntryKind; amount: int
    method: VoucherRedeemMethod | None = None; note: str | None = None
    task_id: uuid.UUID | None = None; task_name: str | None = None
    actor_name: str | None = None
    created_at: dt.datetime; updated_at: dt.datetime

class VoucherShift(BaseModel):              # one earning (or upcoming) booking
    booking_id: uuid.UUID; shift_id: uuid.UUID; task_id: uuid.UUID; task_name: str
    title: str; date: dt.date; start_time: dt.time | None; end_time: dt.time | None
    ends_at: dt.datetime                     # naive UTC (wall clock converted via
                                             # EVENT_TIMEZONE), same convention as
                                             # created_at, so history sorts as one list
    vouchers: int; completed: bool

class VoucherBalance(BaseModel):
    user_id: uuid.UUID; name: str | None; email: str | None; avatar_etag: str | None
    role: EventRole | None                   # None = has left the event
    earned: int; upcoming: int
    redeemed: int                            # positive number
    adjusted: int                            # signed sum of corrections
    balance: int                             # earned - redeemed + adjusted, may be < 0
    available: int                           # max(balance, 0)

class VoucherAccount(BaseModel):
    summary: VoucherBalance; shifts: list[VoucherShift]; entries: list[VoucherEntryRead]

class VoucherPassRead(BaseModel):
    id: uuid.UUID; code: str; qr_payload: str     # "WV1:" + code
    expires_at: dt.datetime; ttl_seconds: int     # count down from ttl, not from the device clock
    event_name: str                               # shown in the dialog, so the volunteer sees which event

class VoucherPassStatus(BaseModel):
    status: Literal["active", "checking", "used", "expired"]   # checking = held by a redeemer
    redeemed_amount: int | None = None; task_name: str | None = None
    available: int

class VoucherPointRead(BaseModel):
    task_id: uuid.UUID; name: str; location: str | None
    can_redeem: bool; can_redeem_manually: bool
    is_desk: bool
    managers: list[TaskManagerBrief]              # "No phone? Ask Anna or Ben"

class VoucherCheckRequest(BaseModel):
    task_id: uuid.UUID
    code: str | None = Field(default=None, max_length=32)
    user_id: uuid.UUID | None = None
    # model_validator: exactly one of code / user_id (plain 422 validation error)

class VoucherRedeemRequest(VoucherCheckRequest):
    amount: int = Field(ge=1, le=50)
    request_id: uuid.UUID                         # client-generated once per confirm; a retry reuses it

class VoucherCheckResult(BaseModel):
    user_id: uuid.UUID; name: str | None; avatar_etag: str | None; available: int

class VoucherRedeemResult(BaseModel):
    entry: VoucherEntryRead; user_id: uuid.UUID; name: str | None; available: int  # after
    replayed: bool = False                        # true when request_id matched an earlier redemption

class VoucherAdjustmentCreate(BaseModel):
    user_id: uuid.UUID
    amount: int = Field(ge=-999, le=999)      # validator: != 0
    note: str = Field(min_length=1, max_length=500)   # stripped; blank -> 422

class VoucherAdjustmentUpdate(BaseModel):
    amount: int | None = Field(default=None, ge=-999, le=999)   # != 0
    note: str | None = Field(default=None, min_length=1, max_length=500)

class PointRedemptionRead(VoucherEntryRead):
    user_id: uuid.UUID; user_name: str | None

class PointRedemptionList(BaseModel):
    items: list[PointRedemptionRead]; total_amount: int   # sum of -amount over items
```

Read-schema flags:

- **`TaskRead`** gets the stored fields `vouchers_per_shift: int = 0`,
  `is_voucher_point: bool = False` and `is_voucher_desk: bool = False`. They
  go in `TaskBase`, so `TaskCreate` accepts them, with `Field(ge=0, le=50)` on
  the first. `TaskUpdate` (optional) and `TaskCreateWithShifts` get them as
  well.
- **`TaskRead`** also gets the viewer-relative `can_redeem: bool = False`:
  true when `is_voucher_point` holds and the caller may redeem there *right
  now*. `mark_task_access` fills it using one extra query: the caller's
  confirmed bookings on shifts of the point tasks they cannot manage, dated
  within `redeem_window_dates(clock.wall_clock_now())` (yesterday through
  tomorrow, the same range `voucher_redeemer_kind` uses), filtered with
  `redeem_window`.
- **`EventRead`** gets `voucher_task_count: int = 0` (published tasks with
  `vouchers_per_shift > 0`) and `voucher_point_count: int = 0` (published
  points). Both are for members only, like `team_count`, and are filled in
  `decorate_events` by one grouped query,
  `crud_task.voucher_counts_by_event(session, event_ids=member_of)`.

Other changes:
- `ADMIN_ONLY_TASK_FIELDS` gains `vouchers_per_shift`, `is_voucher_point`
  and `is_voucher_desk`.
- `AffectedBookingInfo` (regenerate's dry-run answer) gains `user_name` and
  `locked: bool` (package A). The editor that confirms the regenerate is now
  often a person in charge who has to "tell them yourself", and today sees
  only the first 8 characters of a user id.
- `core/rate_limit.py`: `RateLimiter.__init__(self, limit, window_seconds, *,
  code: str = "auth.rate_limited")`, so `check()` raises with
  `code=self.code`. Two new buckets, keyed by user id:
  - `voucher_code_limiter = RateLimiter(60, 60, code="voucher.rate_limited")`
    makes guessing codes pointless (a busy stand does a check and a redeem
    per person, about 25 a minute, so 30 would be too tight);
  - `voucher_pass_limiter = RateLimiter(20, 60, code="voucher.rate_limited")`
    because each issue writes a row.

### Error codes

| Status | Code | Raised by |
|---|---|---|
| 403 | `task.forbidden` | `require_task_manager` |
| 403 | `task.admin_only_field` (`fields`) | `PATCH /tasks/{id}` by a person in charge |
| 403 | `task.not_published` | `require_task_visible`, and booking a non-published task (existing code, gets an i18n entry now) |
| 403 | `task.shift_history_admin_only` | `check_shift_history` (person in charge changing or deleting a booked shift's past) |
| 422 | `task.manager_not_event_member` | add, and with-shifts `manager_ids` |
| 409 | `task.manager_already` | add |
| 404 | `task.manager_not_found` | remove |
| 400 | `batch.wrong_task` | `POST /shifts/` with another task's batch (existing code, gets an i18n entry now) |
| 403 | `voucher.not_allowed` | `require_voucher_redeemer` |
| 403 | `voucher.manual_not_allowed` | redeeming by `user_id` while only on shift at a point that is not a desk |
| 422 | `voucher.not_a_point` | check / redeem / points entries on an unflagged task |
| 404 | `voucher.code_invalid` | unknown or malformed code, or a pass replaced between check and redeem |
| 409 | `voucher.code_other_event` | the code was issued in another event |
| 409 | `voucher.code_used` (`amount`, `task_name`, `actor_name`, `used_at`) | pass already used; the extensions let the redeemer see "Already redeemed: 2 at Bar, 14:03" rather than scanning a fresh code |
| 409 | `voucher.code_expired` | pass expired and not held by a check |
| 409 | `voucher.request_conflict` | a `request_id` that belongs to another redeemer or event |
| 409 | `voucher.insufficient` (`available`) | amount above what is available |
| 429 | `voucher.rate_limited` | the two limiters |
| 404 | `voucher.pass_not_found` | pass status for a pass that isn't yours or was replaced |
| 404 | `voucher.entry_not_found` | adjustment id not in this event |
| 409 | `voucher.entry_not_editable` | PATCH/DELETE on a redemption |
| 409 | `booking.shift_over` | booking, reactivating or cancelling a shift that has ended (any task) |
| 409 | `booking.shift_started` | booking or reactivating a shift that has started, on a task that earns vouchers, by someone who cannot manage the task |
| 403 | `event.forbidden` | booking a shift in an event you are not a member of (existing code) |
| 404 | `event.member_not_found` | redeeming for a non-member; adjusting for someone with no membership, ledger rows or bookings in the event (existing code) |

## How a balance is worked out

`app/logic/clock.py` (new, created in package A because the shift history
rule needs it):

```python
def utc_now() -> dt.datetime:          # naive UTC, for stored timestamps (passes, entries)
def wall_clock_now() -> dt.datetime:   # datetime.now(ZoneInfo(settings.EVENT_TIMEZONE)).replace(tzinfo=None)
```

Callers use `clock.wall_clock_now()` through the module attribute, so a test
monkeypatches one target, `app.logic.clock.wall_clock_now`.
`settings.EVENT_TIMEZONE: str = "Europe/Berlin"` gets a validator that builds
`ZoneInfo(value)` and refuses to boot on an unknown name. `tzdata` is
installed today only through `icalendar`, so add it to `pyproject.toml`
explicitly; Windows dev needs it. Add the setting to `.env.example` and to the
backend environment in `docker-compose.yml` next to `SANDBOX_TTL_MINUTES`.
Add a line to CLAUDE.md "Environment".

`app/logic/work_hours.py`:

```python
def counts_as_worked() -> ColumnElement[bool]:
    """Whether a booking earns hours and vouchers: the one line #177 changes."""
    return col(Booking.status) == "confirmed"
```

`_booked_shifts` uses it in place of its inline `status == "confirmed"`.
`_tally`'s default `now` becomes `clock.wall_clock_now()`. Update the module
docstring, which currently says shifts are compared with naive UTC.

`app/logic/vouchers.py`:

```python
PASS_TTL = dt.timedelta(seconds=120)
PASS_HOLD = dt.timedelta(seconds=60)    # after a successful check, the pass stays redeemable this long
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"   # no 0 O 1 I L
CODE_LENGTH = 6
QR_PREFIX = "WV1:"
REDEEM_GRACE_BEFORE = dt.timedelta(minutes=30)
REDEEM_GRACE_AFTER = dt.timedelta(minutes=30)

def normalize_code(raw: str) -> str | None:   # strip, upper, drop QR_PREFIX, '-', spaces; None unless 6 chars of the alphabet
def redeem_window(date, start, end) -> tuple[dt.datetime, dt.datetime]:
    # (combine(date, start or 00:00) - GRACE_BEFORE, shift_ends_at(date, start, end) + GRACE_AFTER)
def redeem_window_dates(now) -> tuple[dt.date, dt.date]:
    # ((now - GRACE_AFTER).date() - 1 day, (now + GRACE_BEFORE).date()): the shift dates
    # whose window can contain ``now``; the "- 1 day" covers overnight shifts
def pass_redeemable(p: VoucherPass, utc_now) -> bool:
    # p.used_at is None and (p.expires_at > utc_now
    #   or (p.checked_at is not None and p.checked_at + PASS_HOLD > utc_now))
def to_utc(wall: dt.datetime) -> dt.datetime:
    # wall clock in EVENT_TIMEZONE -> naive UTC, for VoucherShift.ends_at
```

Using `shift_ends_at` gives one definition of "ended" for overnight shifts,
start-only shifts and shifts with no times.

**Earned, for one event.** `_voucher_shifts(session, event_id, *, user_id=None, now)`:

```python
select(Booking.id, Booking.user_id, Shift.id, Task.id, Task.name, Shift.title,
       Shift.date, Shift.start_time, Shift.end_time, Task.vouchers_per_shift)
.join(Shift, Shift.id == Booking.shift_id)
.join(Task, Task.id == Shift.task_id)
.where(Task.event_id == event_id, counts_as_worked(), Task.vouchers_per_shift > 0)
[.where(Booking.user_id == user_id)]
.order_by(Shift.date, Shift.start_time)
```

In Python, `completed = shift_ends_at(date, start, end) <= now`. Completed
rows add to `earned` and the rest to `upcoming`. `VoucherShift.ends_at` is
`to_utc(shift_ends_at(...))`, so the history can merge shifts and ledger
entries on one naive-UTC time line (otherwise, in a German summer, every
entry would sort two hours early against the shifts). The query uses the
existing indexes `ix_bookings_user_id` and `ix_shifts_task_id_date`.

**Ledger.**
`select(VoucherEntry.user_id, VoucherEntry.kind, func.sum(VoucherEntry.amount)).where(event_id == :e [, user_id == :u]).group_by(user_id, kind)`.
`redeemed = -sum(redemption)` and `adjusted = sum(adjustment)`.

Public functions:
- `account(session, event_id, user, *, now) -> VoucherAccount`
- `balances(session, event_id, *, now) -> list[VoucherBalance]`: every member
  plus former members whose `earned`, `redeemed` or `adjusted` is not 0,
  merged with `crud_membership.list_members` the way `event_hours` does it.
  Sorted by `available` descending, then name.
- `available_for(session, event_id, user_id, *, now) -> int`

Neither query filters on membership or task status. Someone who worked and
then left still worked, and an archived task's shifts still count. What
keeps that honest is upstream: leaving cancels the person's unfinished
bookings, nobody can book an ended shift, and members cannot book shifts of
unpublished tasks.

## Redeeming

`logic/vouchers.redeem(session, *, event_id, task, redeemer: User, code: str | None,
user_id: uuid.UUID | None, amount: int, request_id: uuid.UUID, wall_now, utc_now)
-> VoucherRedeemResult`. It is a logic function so that the concurrency test
can call it on two sessions.

1. *(route)* Check event visibility, that the task is in the event, the
   gate `require_voucher_redeemer(..., manual=user_id is not None)`, and the
   point flag. Then apply the code limiter.
2. **Who:**
   - With a code: `normalize_code`, or `404 voucher.code_invalid`. Then
     `SELECT * FROM voucher_passes WHERE code = :c` (codes are unique across
     the installation), or `404 voucher.code_invalid`. A pass whose
     `event_id` is not this event is `409 voucher.code_other_event`. The
     volunteer is the pass's `user_id`.
   - Without a code: the volunteer is `user_id`.
3. The volunteer must be a current member, otherwise `404
   event.member_not_found`.
4. **Lock:**
   `SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))` with
   `k = f"vouchers:{event_id}:{volunteer_id}"`. This lives in
   `crud_voucher.lock_ledger(session, *, event_id, user_id)`.
5. **Replay:** `SELECT … FROM voucher_entries WHERE request_id = :r`. If a row
   exists with this `event_id` and `actor_id == redeemer.id`, return it as
   the result with `replayed=True` (and the current `available`); if it
   belongs to anyone else, `409 voucher.request_conflict`. A redeemer whose
   response was lost retries with the same `request_id` and sees what went
   through instead of debiting twice; this covers manual redemptions, which
   have no pass to make them single-use.
6. With a code: **re-read the pass under the lock**, with
   `execution_options(populate_existing=True)`, because step 2 loaded it into
   the identity map before the lock. **If the row is gone** (the volunteer's
   screen issued a new code in between and the pass was not held), the answer
   is `404 voucher.code_invalid`, never an attribute error. If `used_at` is set
   the answer is `409 voucher.code_used` with the extensions of the matching
   entry; if `not pass_redeemable(pass, utc_now)` it is `409
   voucher.code_expired`.
7. `available = available_for(...)`. If `amount > available`, raise `409
   voucher.insufficient` with `extensions={"available": available}`. **Nothing
   has been written yet.** The answer does not rely on a rollback, which the
   test client would not perform (see `tests/fixtures/client.py`, "KNOWN
   GAP"). The code stays valid for a smaller amount.
8. With a code: `UPDATE voucher_passes SET used_at = :now WHERE id = :id AND
   used_at IS NULL AND (expires_at > :now OR checked_at > :now - PASS_HOLD)
   RETURNING id`. Zero rows means `409 voucher.code_used`. This is a
   backstop: step 4 already serialises.
9. Insert a `VoucherEntry`:
   - `kind="redemption"`, `amount=-amount`, `method="code"|"manual"`;
   - `task_id`, `task_name=task.name`;
   - `actor_id=redeemer.id`, `actor_name=redeemer.name or redeemer.email`;
   - `pass_id` (code path), `request_id`.

   Then flush inside `begin_nested()`. An `IntegrityError` on `pass_id` is
   `409 voucher.code_used`; one on `request_id` re-runs the replay lookup of
   step 5. Both are last backstops.
10. Return `available - amount`.

`check` runs steps 1–3 and 6 without the lock and without touching the
ledger, and returns the name, avatar and `available`. With a code it makes
one small write: `UPDATE voucher_passes SET checked_at = :now WHERE id = :id
AND used_at IS NULL AND expires_at > :now`, which **holds** the pass for
`PASS_HOLD`. A check after expiry, inside an earlier hold, still answers but
does not move the hold on, so re-checking cannot keep a code alive. The redeemer
sees who is in front of them and the maximum before choosing an amount, and
a code that runs out while they choose still goes through. A used code
answers `409 voucher.code_used` with its extensions, so the redeemer sees
"Already redeemed: 2 at Bar, 14:03".

**Why an advisory lock.**
- It serialises every write that changes one volunteer's balance in one
  event: two stands redeeming at once, or a correction during a redemption.
  Adjustments take the same lock.
- It needs no row. The balance is derived, so there is no row to lock with
  `FOR UPDATE`.
- `FOR UPDATE` on the user row would also block every insert that takes a
  `KEY SHARE` lock on that user (bookings, notifications) while it is held.
- It is released at commit or rollback, so it cannot leak.
- Under Postgres's default READ COMMITTED, every statement after the lock
  sees the other transaction's committed debit, so step 6 reads the true
  balance.
- A hash collision only serialises two unrelated volunteers. It is never
  wrong.

SERIALIZABLE isolation would need retry loops, which the app has nowhere.

**Issuing a pass** (`crud_voucher.issue_pass(session, *, event_id, user_id, now)`):
1. Generate a code with `secrets.choice` over `CODE_ALPHABET`.
2. Insert the row with `expires_at = now + PASS_TTL` inside `begin_nested()`.
   On an `IntegrityError` on `uq_voucher_passes_code`, retry; give up after 5
   attempts.
3. `DELETE FROM voucher_passes WHERE event_id = :e AND user_id = :u AND id <>
   :new AND used_at IS NULL AND (checked_at IS NULL OR checked_at <= :now -
   PASS_HOLD)`.

The old code is invalid from then on, unless a redeemer is holding it right
now, and a screenshot of it is worthless. Used passes are kept so that their
status can still say "redeemed". The response carries `ttl_seconds = 120`,
and the client counts down from the moment it receives the response, never
from `expires_at` against the device clock.

**Pass status.** Load the pass by `id` and the caller's `user_id`, otherwise
`404 voucher.pass_not_found`.
- `used` if `used_at` is set, with `redeemed_amount` and `task_name` from the
  entry whose `pass_id` matches;
- `checking` if `checked_at` is set and `pass_redeemable` holds (a redeemer
  is on it; the client stops rotating);
- `expired` if not `pass_redeemable`;
- otherwise `active`.

It also returns `available`.

## Side effects handled

**Membership removal.** `events.py::remove_member` calls
`crud_task_manager.remove_user_from_event_tasks` right after
`crud_team.remove_user_from_event_teams`. This covers leaving and being
removed. From package B it also calls
`crud_booking.cancel_unfinished_bookings_in_event(session, *, user_id,
event_id, now=clock.wall_clock_now())`: the person's confirmed bookings on
shifts of the event's tasks whose `shift_ends_at > now` become `cancelled`
with the same snapshot fields `cancel_bookings_for_shifts` writes. A former
member then neither keeps a place on future rotas nor keeps earning;
bookings on shifts already over stay, because that work happened.

**Ownership transfer.** `crud/event.py::reassign_owner` (used by `POST
/users/{id}/transfer-ownership`, a superadmin action after which the source
account survives) moves the source user's `owner` membership rows to the
target, so the source user **leaves** every one of those events. The route
calls `crud_task_manager.remove_user_from_event_tasks` (and, for the same
reason, `crud_team.remove_user_from_event_teams`, a pre-existing gap) for
each `owned_event_id`; `reassign_owner` returns those ids alongside the
count so the route need not query them twice. Otherwise re-inviting the
person would quietly restore "in charge".

**User deletion.**
- `task_managers.user_id`, `voucher_entries.user_id` and
  `voucher_passes.user_id` are CASCADE. Deleting a volunteer removes their
  ledger, and their earned vouchers vanish with their bookings anyway.
- Deleting a *redeemer* or an admin who made a correction keeps the rows,
  with `actor_name`. The same goes for `added_by_name`.

**Event deletion.**
- `voucher_entries` and `voucher_passes` cascade from the event.
- Tasks survive with `event_id` NULL (existing behaviour), and so do their
  `task_managers` rows. They are inert: `task_access` returns `None` for a
  task without an event unless the caller is the superadmin, so a former
  person in charge controls nothing nobody else can see.

**Deleting a task** cascades its manager rows. Ledger rows keep `task_name`.

**Moving a task to another event** (`PATCH`, admin only): in the same block
that clears `team_id` and `location_id`, call
`crud_task_manager.remove_all_for_task`. People in charge are members of the
source event. The voucher settings stay, because the mover is admin in both
events and sees them. The task's earned vouchers move with it, as its hours
already do.

**Regenerating shifts used to delete without a record.** Unmatched shifts
were removed with `session.delete(shift)`, which left their bookings
confirmed with `shift_id` NULL and no snapshot. Hours and vouchers dropped
silently, and the volunteer saw nothing. Now, before step 6c, call
`crud_booking.cancel_bookings_for_shifts(session, slot_ids=[s.id for s in
shifts_to_delete], task_name=db_task.name)`, like every other delete path.
People in charge can trigger this route now, which is why the fix belongs to
package A. For a person in charge, `check_shift_history` runs over
`shifts_to_delete` first; the dry run marks those shifts `locked` and
carries `user_name`, so the editor can name the people affected. The dry run
also used to copy the new title, places, location and category onto the kept
shifts before checking `dry_run`, and the request's commit kept them, so a
cancelled preview edited the rota. Those updates now happen in the real run
only.

**Another task's batch.** `POST /shifts/` used to accept any `batch_id`. With
per-task rights, the person in charge of task B could then delete batch B and
with it a shift of task A. A `batch_id` whose `batch.task_id != slot_in.task_id`
is refused with `400 batch.wrong_task`.

**Event clone** (`events.py::clone_event`):
- `_clone_task` copies `vouchers_per_shift`, `is_voucher_point` and
  `is_voucher_desk`, and returns `tuple[Task, list[Shift]]` rather than only
  the shifts.
  `clone_event` collects `task_map[src.id] = new_task.id`.
- After its existing `await session.flush()`, it adds `TaskManager` rows for
  `crud_task_manager.rows_for_clone(task_ids=task_map keys,
  user_ids=carry_members)` and flushes again. `carry_members` is the same set
  passed to `_clone_teams`: the copied roster plus the cloner with
  `copy_members`, otherwise empty.
- Adding the rows after the flush avoids relying on insert order.
  `added_by_*` is copied.
- Ledger rows and passes are never copied, just as bookings are not.

**Booking** (`api/routes/bookings.py`, package B):
- `create_booking` calls `require_event_role(current_user, session,
  task.event_id, minimum="member")` before the team gate, then
  `crud_membership.lock_member_ids` on the caller (not for the superadmin),
  `403 event.forbidden` if the row is gone by then.
- It then refuses `task.status != "published"` with `403 task.not_published`
  unless `task_access()` is not None.
- If `shift_ends_at(...) <= clock.wall_clock_now()`, the answer is `409
  booking.shift_over`, on every task. This also covers reactivating a
  cancelled booking, which goes through the same route.
- On a task with `vouchers_per_shift > 0`, a shift that has started is `409
  booking.shift_started` unless `task_access()` is not None.
- `cancel_booking` (DELETE) and `update_booking` (PATCH with
  `status="cancelled"`) refuse the same case with the same code, on every
  task.
- A no-show is corrected with a negative adjustment (and an hours
  correction) until #177 exists.

**Admin edits after the fact** (lowering vouchers per shift, deleting a past
shift or batch or task, moving a shift's date) can push a balance below zero.
The app shows 0 available and refuses redemptions; the admin overview shows
the negative number with an explanation.

**The day after the event.** The router's selected-event guard blocks every
event page once `end_date < today` (`router/index.ts`). The redeem page is no
exception: an after-party that should still take vouchers needs the event's
end date to cover it, documented in the admin hint. **My vouchers** is
exempt (`SELECTED_EVENT_EXEMPT_ROUTES`, as `event-settings` is): a volunteer
asking "did I get mine?" the next morning still sees their balance and
history. Once the event has expired the page is read-only ("Show my code" is
hidden), and the expired notice in `SelectEventView` links to it when the
expired event used vouchers.

**Sandbox purge** (`logic/sandbox/cleanup.py`):
- Step 2: `delete(TaskManager).where(TaskManager.task_id.in_(task_ids))`
  before `delete(Task)`.
- Step 3, after `event_memberships`:
  `delete(VoucherPass).where(VoucherPass.event_id == event_id)`, then
  `delete(VoucherEntry).where(VoucherEntry.event_id == event_id)`.
- All of these would cascade, but they are spelled out as for the teams.
- `docs/SANDBOX.md`: update the order diagram (steps 3 and 4) and the seed
  paragraph. Add an invisibility-table row for `require_task_visible` (a
  sandbox task 404s for anyone but its guest, the superadmin included) and
  one saying voucher routes go through `require_event_visible`.

## Seeds (`logic/sandbox/seed.py`, also used by `just seed`)

The cost is small and the demo then shows both features:

- `_TaskSpec` gets `vouchers_per_shift: int = 2`, `voucher_point: bool =
  False` and `voucher_desk: bool = False`. Set `voucher_point=True` on
  "Welcome desk" (the volunteer desk, also `voucher_desk=True`) and "Café
  counter".
- After `_seed_teams`, with the teammates already flushed:
  - `TaskManager` rows put `teammates[0]` in charge of "Café counter" and
    "Grill stand", with `added_by_name=owner.name`.
  - One `VoucherEntry`: `kind="redemption"`, `amount=-1`, for the visitor
    (`owner`), at "Café counter", by `teammates[0]`, `method="code"`,
    `created_at = now - 20 h`.
- The visitor already has one past booking (`_seed_bookings`, "one already
  behind them"), so they earn at least 2 and show at least 1 available.
- Update the SANDBOX.md seed description.

## Frontend

All paths are relative to `frontend/src/`. In task routes, `params.eventId`
is the **task** id. The backend packages end by regenerating and committing
`src/client` (see Implementation order); each frontend package starts by
checking that `just generate-client` leaves no diff. The viewer's own id is
always `authStore.profile?.id`, never `authStore.user?.id`, which has no id
under the E2E `X-Test-User-Email` bypass (see `ShiftDetailDialog.vue`).
User-facing strings call event admins **organisers** / **Organisator:innen**,
matching the role label (`duties.events.roles.admin`) and `teamLocks.json`.

### A. People in charge

**Two predicates replace one.** In `views/tasks/TaskDetailView.vue`,
`canManage = authStore.canManageEvent(task.event_id)` becomes:
- `canManageTask = computed(() => task.value?.can_manage ?? false)`
- `canAdminEvent = computed(() => authStore.canManageEvent(task.value?.event_id))`

| Place in `TaskDetailView.vue` | Predicate |
|---|---|
| `StatusDropdown :editable` | `canAdminEvent` (people in charge cannot publish) |
| desktop "Edit task" (`btn-edit-task`), mobile "Edit" | `canManageTask && !hasBatches` |
| add-shifts dropdown (`btn-add-shifts`), mobile add batch / single shift | `canManageTask` |
| delete task (`btn-delete-task`), mobile delete and **its separator** | `canAdminEvent` (render the separator only when delete is shown) |
| location details button (`btn-task-location-details`) and `LocationFormDialog` | `canAdminEvent` (it edits the event-wide location) |
| per-batch Edit / Delete | `canManageTask` |
| delete icon on each shift card | `canManageTask` (a refusal under the shift history rule arrives as `task.shift_history_admin_only` through `toastApiError`) |
| create-shift dialog's `LocationPicker` | unchanged: it allows "new location" only for admins on its own |
| draft banner (`duties.tasks.draftBanner`, "Set the status to Published") | `canAdminEvent`; people in charge see a new variant, `duties.tasks.draftBannerManager` ("Ask an organiser to publish it") |
| mini-map container (`task-mini-map`, today `sharedLocationDetail && (miniMapPin \|\| canManage)`) | `sharedLocationDetail && (miniMapPin \|\| canAdminEvent)`: the empty map is an invitation to place a pin on the event-wide location, which is admin work |

**Showing who is in charge.** Create
`components/tasks/managers/TaskManagersInline.vue`: small avatars plus
`joinNames` (`components/events/teams/teamHelpers.ts`). It goes in the info
row (dates · location · category) as "In charge: Anna, Ben" and is hidden
when the list is empty. It adds a "You're in charge" badge when the viewer
is in the list and not an event admin.

**Editing who is in charge**, for admins only:

- A desktop "More actions" dropdown (EllipsisVertical button, `hidden
  sm:flex` row) holds "People in charge…" and, from B, "Vouchers…".
- The phone ⋮ menu gets the same items in a group above the separator and
  delete.
- For a person in charge who is not an admin, the same places show "Step
  down" (`confirmDestructive`, then `DELETE …/managers/{profile.id}`). Then
  reload the task quietly if it is published; if it is a draft, go to the
  task list instead, because the reload would answer `403
  task.not_published` and `loadTask` would toast an error before redirecting.
- "People in charge…" opens `components/tasks/managers/TaskManagersDialog.vue`
  (`ResponsiveDialog`, so a drawer on phones), which contains
  `TaskManagersEditor.vue`:
  - `EventMemberPicker` on top, fed by `GET /events/{id}/members`. Current
    people in charge go in `unavailable` with the reason "Already in charge".
  - Below it, rows with avatar and name and a ⋮ `DropdownMenu` with
    "Remove" (`variant="destructive"`, `confirmDestructive`). This is the
    `TeamRoster.vue` row pattern.
  - Each action posts, toasts and emits `changed`; the view reloads the task.
  - Errors go through `toastApiError`.
- The editing lives on the detail page, not in `TaskEditView`, because tasks
  with two or more batches cannot reach the edit form.

**Other views:**
- `router/routes.ts`: remove `requiresEventManager` from `task-edit` and
  `task-add-shifts`. Keep it on `task-create`.
- `TaskEditView.vue` and `TaskAddShiftsView.vue`: the in-view guard becomes
  `if (!ev.can_manage) router.replace(task-detail)`.
- `TaskEditView.vue`: the "Who can book" card (`section-who-can-book`) gets
  `v-if="!isBatchMode && canAdminEvent"`. Its PATCH is only sent when the
  team changed, so hiding the card is enough.
- `TaskCreateView.vue`: a "People in charge" section after "Who can book",
  shown when `locationEventId` is set. It uses `EventMemberPicker` plus chips
  for the picks, resets in the same watch as `teamId`, and sends `manager_ids`
  in the with-shifts body.
- `components/tasks/quick-view/TaskQuickViewCard.vue`: the status badge and
  ShieldCheck icon use `task.can_manage`. Delete uses
  `authStore.canManageEvent(task.event_id)`. Add an "In charge" badge when
  `task.can_manage && !authStore.canManageEvent(task.event_id)`.
- `components/tasks/TaskListView.vue`: the badge uses `task.can_manage`, and
  delete uses `authStore.canManageEvent(task.event_id)` (it uses the global
  `isManager` today, which is wrong for people in several events).
- `components/tasks/ShiftRoster.vue` and `ShiftBookingsTable.vue`: show e-mail
  and notes when the server sent them (`v-if="entry.user_email"`). The
  `authStore.isAdmin` checks go, because the server redacts now.
  - `ShiftRoster.vue` also shows `user_phone_number` as a `tel:` link when
    present. On site the phone number is what a person in charge needs, and
    today only the print views render it.
  - In `ShiftBookingsTable.vue` notes are a whole column (`TableHead` and
    `TableCell`), so the column is gated by a table-level `showNotes =
    computed(() => bookings.some((b) => b.notes != null))`, not per row.
- `views/bookings/BookingDetailView.vue`: load `/shifts/{id}/bookings` after
  the `Promise.all`, in its own `try`, so a refused or failed roster hides the
  roster card instead of sending the volunteer back to My Bookings.
- `TaskEditView.vue`, regenerate's "affected bookings" dialog: show
  `user_name` (from the new `AffectedBookingInfo.user_name`) instead of
  `user_id.substring(0, 8)`, and mark `locked` rows with
  `duties.tasks.editView.affectedBookings.locked` ("Only an organiser can
  remove this shift"); the confirm button is disabled when any row is
  locked.
- `views/print/PrintTaskView.vue` and `PrintEventView.vue`: render the phone
  column only when at least one row has a phone.
- `views/events/EventCloneView.vue`: on the review step, next to the
  members option, add one line saying people in charge come along only with
  members.
- **Cleanup of the retired global role:** remove the "Make / Remove Task
  Manager" item and the `toggleTaskManager` emit chain from
  `components/admin/users/UserRowActions.vue`, `UsersTable.vue` and
  `UsersGroupedList.vue`, and from `views/admin/UsersView.vue`
  (`patchUserRoles` takes only `'admin'`). Delete the four
  `admin.users.*TaskManager*` keys in en and de.
- No new file in `lib`, `composables` or `stores`, so there is no coverage
  gate for package A.

### B. Vouchers

**Scanner: `qr-scanner@1.4.2`**, installed with `pnpm --prefix frontend add
qr-scanner@1.4.2`. The API was checked against Context7 `/nimiq/qr-scanner`:
`new QrScanner(video, onDecode, {preferredCamera, maxScansPerSecond,
highlightScanRegion, highlightCodeOutline, onDecodeError,
returnDetailedScanResult})`, `start()` rejects with `'Camera not found.'` or
a `DOMException`, and the API also has `destroy()` and `hasCamera()`.
Details that matter (re-checked against Context7):
- With an options object as the third argument the **new API** is in effect:
  `onDecode` receives a `ScanResult` `{data, cornerPoints}`, not a string, so
  the component emits `result.data`.
- `onDecode` fires on **every** decoded frame, not once per code.
- `pause()` stops the camera stream after 300 ms (`pause(true)` at once);
  `start()` re-acquires it. So pausing between people does not keep the
  stream, and on iOS may bring the permission prompt back. Gating
  detections in our own code does.
- The highlight overlay is an absolutely positioned `div` inserted next to
  the video, so the video needs a `relative` wrapper.
- Without `BarcodeDetector` the decoder runs in a Worker created from a
  `blob:` URL. A Content-Security-Policy added later must allow `worker-src
  blob:` (next to `camera=(self)` in any `Permissions-Policy`).

Reasons:
- It uses the native `BarcodeDetector` where present and otherwise a bundled
  worker. That matters because `BarcodeDetector` is missing on iOS Safari and
  on Windows Chrome.
- There is no WASM and no request to a third-party CDN. That matters for
  GDPR and on festival networks. `vue-qrcode-reader` and the
  `barcode-detector` ponyfill load zxing WASM from jsDelivr by default.
- Our codes are large and low-density on a bright screen, so its decoder is
  enough.
- Risk: there has been no release since 2022. It stays behind one component,
  so replacing it is a one-file change.

**Number field:** `pnpm dlx shadcn-vue@latest add number-field`, run from
`frontend/`. This is the CLI `CLAUDE.md` names, run through pnpm. Its ±
buttons carry hard-coded English `aria-label`s ("Increase"/"Decrease" in
reka-ui), so every use passes translated ones (`common.actions.increase` /
`common.actions.decrease`). Everything else is already in `components/ui`:
responsive-dialog, toggle-group, collapsible, native-select, switch,
dropdown-menu, avatar, badge, card, skeleton, table.

**Routes** (`router/routes.ts`, children of `/app`, **no**
`requiresEventManager`, since volunteers on shift must reach the redeem page).
Both take an optional event id, like `teams/:eventId?` and `map/:eventId?`,
and fall back to the selected event. Vue Router ranks the static `redeem`
segment above the parameter, so the two paths don't collide:

| Path | Name | View |
|---|---|---|
| `vouchers/:eventId?` | `my-vouchers` | `views/vouchers/MyVouchersView.vue`. In `SELECTED_EVENT_EXEMPT_ROUTES` (see "The day after the event"); with no event at all it shows an empty state linking to the picker |
| `vouchers/redeem/:eventId?` | `voucher-redeem` | `views/vouchers/RedeemVouchersView.vue`. `?task=<id>` preselects the point; links from `TaskDetailView` always pass `eventId: task.event_id`, so a task of a non-selected event redeems against its own event |

**Navigation.**
- `components/navigation/AppSidebar.vue`: in `navMain`, add "Vouchers" right
  after My Bookings, shown when `selectedEvent.voucher_task_count > 0 ||
  selectedEvent.voucher_point_count > 0`.
- `components/navigation/MobileBottomNav.vue`: the same entry and condition
  in the event group of `moreGroups`. No fifth tab. `moreRoutes` is built
  only from the route names in `moreGroups`, so add a `VOUCHER_ROUTES = new
  Set(['my-vouchers', 'voucher-redeem'])` mapped to `'more'` in `activeTab`;
  otherwise the redeem page highlights no tab.
- The counts live on `authStore.selectedEvent`, which loads once. Call
  `authStore.refreshSelectedEvent(task.event_id)` after
  `TaskVoucherSettingsDialog` saves and after a status change on a task with
  vouchers or a point, so the organiser sees the entry at once. Others pick
  it up on their next load; `MyVouchersCard` does not depend on the counts
  (below).

**New files:**

| File | What |
|---|---|
| `lib/vouchers.ts` + `lib/__tests__/vouchers.spec.ts` (≥ 90 % coverage; specs live in `lib/__tests__/`) | `normalizeVoucherCode(input)` (upper-case, strip `-`, spaces and the `WV1:` prefix, validate against the alphabet), `parseVoucherPayload(text)` (QR: only `WV1:` + 6 valid chars, else `null`), `formatVoucherCode(code)` → `K7M-4QX`, `secondsLeft(receivedAtMs, ttlSeconds, nowMs)`, `historySortKey(item)` (`ends_at` / `created_at` through `parseServerDate` from `lib/server-time.ts`, since both are naive UTC) |
| `views/vouchers/MyVouchersView.vue` | Event from `route.params.eventId` or the selected event. Balance card: big "available" number, plus earned / used / corrections and "still to come". Full-width "Show my code" (disabled at 0 available, hidden once the event has expired). History (`VoucherHistory`). A "Redeem vouchers" button when `GET …/vouchers/points` has any `can_redeem` |
| `views/vouchers/RedeemVouchersView.vue` | Event from `route.params.eventId`, else the selected event. Point picker: `NativeSelect` of points with `can_redeem`, preselected from `?task=`, else the only one, else the last one used (localStorage, in try/catch). **No `Tabs`:** reka's `TabsRoot` unmounts inactive panels by default (`unmountOnHide`), which would destroy the scanner and stop the camera each time someone switches to typing, and with `unmountOnHide=false` the inactive panel is `hidden`, where the scanner must never sit. Layout instead: the scanner always mounted on top, with `redeem.scanHint` under it; below, a `Collapsible` "Type the code instead" with the code input; below that, when `can_redeem_manually`, a "Pick a person" button that opens an `EventMemberPicker` in a `ResponsiveDialog`. When the point allows no manual redemption and has people in charge, a line "No phone? Ask {names}" (`redeem.askManagers`, from `VoucherPointRead.managers`). A detection or input calls `POST …/check`, which opens `VoucherRedeemConfirm`. Below that, "Redeemed here recently" (`…/points/{id}/entries`): everything for people in charge and organisers, "Your recent redemptions" for on-shift redeemers. An empty state when no point is redeemable |
| `components/vouchers/MyVouchersCard.vue` | Like `MyHoursCard`: reads `authStore.selectedEventId` and loads `GET …/vouchers/me`. It shows itself when that account has anything to show (earned, upcoming or entries) or the cached counts say the event uses vouchers, so a freshly enabled voucher task appears without a reload. Hides itself on error. Has a "Show my code" button. Mounted in `views/HomeView.vue` between `NextShiftCard` and the grid, and in `views/bookings/MyBookingsView.vue` under `MyHoursCard` |
| `components/vouchers/VoucherCodeDialog.vue` | See "Showing the code" below |
| `components/vouchers/VoucherScanner.vue` | The only file importing `qr-scanner`, through `await import('qr-scanner')` in `onMounted`. Checks `window.isSecureContext` and `navigator.mediaDevices?.getUserMedia` first. Uses `preferredCamera: 'environment'`, `maxScansPerSecond: 8`, both highlights, and `onDecodeError: () => {}`. The `<video>` sits in a `relative` wrapper (the highlight overlay is absolutely positioned next to it). Emits `detect(result.data)` (new-API `ScanResult`) and `error('insecure' \| 'denied' \| 'no-camera' \| 'other')`. Takes a `paused: boolean` prop that only gates emitting; the stream keeps running. Calls `destroy()` in `onBeforeUnmount`. Is never mounted inside a `v-show`-hidden or `hidden` element (the constructor forces a hidden video visible) |
| `components/vouchers/VoucherRedeemConfirm.vue` | `ResponsiveDialog`: avatar and name, "{name} has {n} available", a `NumberField` (min 1, max `min(available, 50)`, default 1, large ± buttons with translated `aria-label`s), and a full-width "Redeem {n}" button. It generates `request_id = crypto.randomUUID()` when it opens and reuses it for every retry of that confirm, so a retry after a lost response returns the first result (`replayed`) instead of debiting again. Success shows "{n} redeemed for {name}. {left} left." and a "Next person" button. A `voucher.code_used` answer shows "Already redeemed: {n} at {place}, {time}" from the problem's extensions instead of a bare error |
| `components/vouchers/VoucherHistory.vue` | Earned shifts (completed only) and entries in one list, newest first, sorted on one key: `ends_at` for shifts and `created_at` for entries, both naive UTC |
| `components/events/EventVouchers.vue` | Admin overview modelled on `EventHours.vue`: table on desktop, cards on phones, with column labels `admin.colAvailable`, `admin.colBalance`, `admin.colEarned`, `admin.colUpcoming`. Negative balances in red with a hint. A row opens a dialog with that person's `VoucherAccount`; corrections have a ⋮ menu for edit and delete. An "Add correction" button |
| `components/events/VoucherAdjustmentDialog.vue` | Modelled on `WorkLogFormDialog.vue`: the person via `EventMemberPicker` (locked when opened for one person; a large event makes a `NativeSelect` unwieldy), an "Add / Take away" `ToggleGroup` plus a **positive** amount (iOS numeric keypads have no minus key; the dialog sends the sign), and the reason |
| `components/tasks/vouchers/TaskVoucherSettingsFields.vue` | A number input "Vouchers per shift" (0–50) plus a switch row "Vouchers can be redeemed here", with a hint that changes with the state (`TeamFormDialog.vue` switch-row pattern), and, shown only while that switch is on, a second switch row "Volunteer desk: staff on shift can also redeem without a code" (`is_voucher_desk`). Plus the static hint that changes also count for shifts already worked |
| `components/tasks/vouchers/TaskVoucherSettingsDialog.vue` | `ResponsiveDialog` around the fields that saves with `PATCH /tasks/{id}`. Reached from "Vouchers…" in the TaskDetailView actions (admins) |

**Showing the code** (`VoucherCodeDialog.vue`, a `ResponsiveDialog`):
1. On open, `POST …/me/pass`. The title names the event (`code.forEvent`,
   from `event_name`), so a volunteer at two events sees which one the code
   is for.
2. Show the QR from `components/print/QrCode.vue` with `qr_payload` at
   260 CSS px, inside an always-white `bg-white p-4 rounded-lg` box, so it
   scans in dark mode. Its `alt` is empty: the same code is printed right
   below it as text.
3. Show the code below it, `formatVoucherCode`, monospace, `text-2xl`.
4. Count down from `ttl_seconds`. Five seconds before the end, or when the
   page becomes visible again after an expiry (`useDocumentVisibility`),
   issue a new pass, **unless** the last status was `checking` or `used`.
5. Poll `GET …/me/pass/{id}` every 2 s while open:
   - `checking` replaces the countdown with "Being redeemed…" and pauses
     rotation (the server holds the pass for up to 60 s);
   - `used` shows a check mark with "{n} used at {place}", refreshes the
     balance and stops rotating; "Show a new code" starts again;
   - after a rotation, the previous pass id is polled too until it reports
     `used` or `expired`, so a redemption that lands on it still shows;
   - a 404 (replaced) is ignored.
6. Keep the screen awake with `useWakeLock` (@vueuse/core) while open.
7. Screen readers: only the state changes ("Redeemed…", "New code") go into
   an `aria-live="polite"` region, never the seconds.

**Scanning a queue** (`RedeemVouchersView.vue`). `onDecode` fires on every
decoded frame, up to 8 times a second, so the view gates detections itself:
- `busy` is true from a detection until the `check` answer arrives, and
  stays true while `VoucherRedeemConfirm` is open; detections while busy are
  dropped (the scanner gets `paused`, which only stops emitting).
- The last handled code is remembered; the same code is ignored until a
  different one has been seen, or for 10 s. Without that, the used code still
  in front of the camera after "Next person" would re-check, answer
  `code_used` and toast again and again, and burn the redeemer's rate limit.
- The camera stream is never paused or destroyed between people (see the
  `pause()` note above).

**Changes to existing files:**
- `QrCode.vue` gets the props `margin` (default 0), `pixelRatio` (default
  1) and `alt` (default: the current hard-coded `'QR Code'`, so print views
  are unchanged). The image is generated at `size * pixelRatio` but displayed
  at `size`, with `errorCorrectionLevel: 'M'`. Print views keep the
  defaults.
- **Ended shifts** (with the backend's `booking.shift_over` on every task):
  hide Book and Cancel for shifts whose end has passed. Extract
  `BookingDetailView`'s `isInPast` into `lib/shift-time.ts::shiftHasEnded(date,
  start, end, now)`, mirroring `work_hours.shift_ends_at` (overnight,
  start-only, untimed), with a spec. Use it in `BookingDetailView.vue`
  (Cancel), `MyBookingsView.vue` (the Cancel icon), `ShiftDetailDialog.vue`
  (`canBook` and its cancel item) and `TaskDetailView.vue` (the click on a
  booked or open shift). The server stays the authority; the browser's local
  time is close enough to hide the buttons. **Started shifts on voucher
  tasks** (`booking.shift_started`): add `shiftHasStarted(date, start, now)`
  (`combine(date, start or 00:00) <= now`) next to it and hide Book on a
  shift whose task has `vouchers_per_shift > 0` once it has started, unless
  `task.can_manage`. The guided tour's `tourBookable` in
  `components/tasks/quick-view/WeekDayColumns.vue` must apply the same rule
  (and the ended one), or the tour's "press Book" step can land on a shift
  the server refuses (every seeded demo task earns vouchers).
- `views/events/SelectEventView.vue`: in the `expired` notice, when the
  expired event has `voucher_task_count > 0`, a link "See your vouchers"
  (`vouchers.afterEventLink`) to `my-vouchers` with its id.
- `TaskDetailView.vue`:
  - Badges in the info row: "{n} vouchers per shift" when
    `vouchers_per_shift > 0`, and "Takes vouchers" when `is_voucher_point`.
  - "Vouchers…" in the admin actions (desktop More dropdown and phone menu).
  - When `task.is_voucher_point && task.can_redeem`: a "Redeem vouchers"
    button in the desktop row, and a **full-width primary button under the
    info row on phones**, since that is the main action at a stand. It goes
    to `{ name: 'voucher-redeem', params: { eventId: task.event_id }, query:
    { task: task.id } }`.
- `TaskCreateView.vue`: `TaskVoucherSettingsFields` after "People in
  charge". Both fields go in the with-shifts body.
- `TaskQuickViewCard.vue`: the two voucher badges, compact.
- `views/events/EventSettingsView.vue`: `EventVouchers` in the People tab
  under `EventHours`, when `canManage` and the event uses vouchers.
- `composables/useAuthenticatedClient.ts`: do not refresh the sidebar for
  URLs matching `/\/vouchers(\/|$|\?)/`. Otherwise every new code, every two
  minutes, triggers a refresh.
- `lib/api-errors.ts`: `voucher.insufficient` builds its message with the
  problem's `available`, the way `booking.time_conflict` builds its own. Add
  a spec case so the file keeps its coverage.
- Check that the guided tour's `my-bookings` anchors (`tour/tracks/helper.ts`)
  still land now that the demo event shows `MyVouchersCard`.

**Mobile layout:**
- The redeem view is a full route, not a dialog, so that one camera stream
  stays open across a queue of volunteers. iOS may ask for permission again
  if the stream stops.
- On the redeem view: the point picker is one line at the top, the video
  fills the width (`aspect-square`, `rounded-lg`, inside a `relative`
  wrapper), the typed-code fallback is a collapsible section under it (not a
  tab, see the view's row above), and the confirm step is a bottom drawer
  with a full-width button.
- Every new action in `TaskDetailView` goes into both the desktop row and the
  phone ⋮ menu.
- Rows with actions use a ⋮ `DropdownMenu`, never a row of wrapped buttons.

**Camera on dev URLs.** `http://wirksam.localhost:47300` is a secure context
in Chromium and Firefox. Desktop Safari needs https. A phone on the LAN IP is
not a secure context; test through an https tunnel or Android port
forwarding. Production is https and sends no `Permissions-Policy` or
Content-Security-Policy header. If one is added later it must allow
`camera=(self)` and `worker-src blob:` (qr-scanner's fallback decoder).

### i18n

Both locales, the same keys (`node ../scripts/pre-commit/check_locale_parity.js`).
German uses "du", as the rest of the app does. Plurals are written with
`\|` here; in the JSON they are plain `|`, and `t()` takes the count as its
third argument.

**`duties.json` → `duties.tasks.managers.*`**

| Key | en | de |
|---|---|---|
| `title` | People in charge | Verantwortliche |
| `label` | In charge | Verantwortlich |
| `youAreInCharge` | You're in charge | Du bist verantwortlich |
| `manage` | People in charge… | Verantwortliche… |
| `dialogTitle` | People in charge of {task} | Verantwortliche für {task} |
| `dialogDescription` | They can edit this task and its shifts and see who booked. They can't delete or publish it. | Sie können diese Aufgabe und ihre Schichten bearbeiten und sehen, wer gebucht hat. Löschen oder veröffentlichen können sie sie nicht. |
| `add` | Add a person | Person hinzufügen |
| `alreadyInCharge` | Already in charge | Bereits verantwortlich |
| `remove` | Remove | Entfernen |
| `removeConfirmTitle` | Remove {name}? | {name} entfernen? |
| `removeConfirmText` | {name} will no longer be able to edit this task. | {name} kann diese Aufgabe dann nicht mehr bearbeiten. |
| `stepDown` | Step down | Verantwortung abgeben |
| `stepDownConfirm` | You will no longer be able to edit this task. | Du kannst diese Aufgabe dann nicht mehr bearbeiten. |
| `added` | {name} is now in charge. | {name} ist jetzt verantwortlich. |
| `removed` | {name} is no longer in charge. | {name} ist nicht mehr verantwortlich. |
| `steppedDown` | You are no longer in charge of this task. | Du bist für diese Aufgabe nicht mehr verantwortlich. |
| `empty` | Nobody yet. The organisers look after this task. | Noch niemand. Die Organisator:innen kümmern sich um diese Aufgabe. |
| `createHint` | Optional. They can edit this task and its shifts. | Optional. Sie können diese Aufgabe und ihre Schichten bearbeiten. |
| `cloneNote` | People in charge come along only if members are copied too. | Verantwortliche werden nur übernommen, wenn auch die Mitglieder kopiert werden. |

The desktop "More actions" button reuses `common.actions.moreActions`, which
the phone menu already uses; no new key.

Other new keys:

| Key | en | de |
|---|---|---|
| `duties.tasks.draftBannerManager` | This task is a draft, so members can't see it yet. Ask an organiser to publish it. | Diese Aufgabe ist ein Entwurf, Mitglieder sehen sie noch nicht. Bitte eine:n Organisator:in, sie zu veröffentlichen. |
| `duties.tasks.editView.affectedBookings.locked` | Only an organiser can remove this shift, because it has started and people are booked. | Diese Schicht kann nur ein:e Organisator:in entfernen, weil sie begonnen hat und Leute gebucht sind. |
| `common.actions.increase` | Increase | Erhöhen |
| `common.actions.decrease` | Decrease | Verringern |

**`vouchers.json` (new namespace)**

| Key | en | de |
|---|---|---|
| `title` | Vouchers | Marken |
| `myTitle` | My vouchers | Meine Marken |
| `available` | `{n} voucher available \| {n} vouchers available` | `{n} Marke verfügbar \| {n} Marken verfügbar` |
| `earned` | Earned | Verdient |
| `used` | Used | Eingelöst |
| `adjusted` | Corrections | Korrekturen |
| `upcoming` | `{n} more for shifts you have booked` | `{n} mehr für deine gebuchten Schichten` |
| `howItWorks` | You get vouchers for each shift once it is over. Show your code where vouchers are taken. | Für jede Schicht bekommst du Marken, sobald sie vorbei ist. Zeig deinen Code dort, wo Marken angenommen werden. |
| `noneAvailable` | You have no vouchers to use right now. | Du hast gerade keine Marken zum Einlösen. |
| `showCode` | Show my code | Code zeigen |
| `code.title` | Your code | Dein Code |
| `code.forEvent` | Your code for {event} | Dein Code für {event} |
| `code.checking` | Being redeemed… | Wird gerade eingelöst … |
| `code.newCode` | New code | Neuer Code |
| `code.showNew` | Show a new code | Neuen Code zeigen |
| `code.hint` | Show this at the counter. It works once; a new one appears by itself. | Zeig ihn an der Theke. Er gilt nur einmal, ein neuer erscheint von selbst. |
| `code.expiresIn` | New code in {s} s | Neuer Code in {s} s |
| `code.redeemed` | `{n} voucher used at {place} \| {n} vouchers used at {place}` | `{n} Marke eingelöst bei {place} \| {n} Marken eingelöst bei {place}` |
| `code.failed` | Your code could not be loaded. Try again. | Dein Code konnte nicht geladen werden. Versuch es noch einmal. |
| `history.title` | History | Verlauf |
| `history.shift` | Shift: {task}, {date} | Schicht: {task}, {date} |
| `history.redeemed` | Used at {place} | Eingelöst bei {place} |
| `history.by` | by {name} | von {name} |
| `history.adjustment` | Correction | Korrektur |
| `history.empty` | Nothing yet. | Noch nichts. |
| `redeem.title` | Redeem vouchers | Marken einlösen |
| `redeem.open` | Redeem vouchers | Marken einlösen |
| `redeem.place` | Where | Wo |
| `redeem.scanHint` | Hold their code in front of the camera. | Halte den Code vor die Kamera. |
| `redeem.typeInstead` | Type the code instead | Code stattdessen eintippen |
| `redeem.pickPerson` | Pick a person | Person auswählen |
| `redeem.codePlaceholder` | e.g. K7M-4QX | z. B. K7M-4QX |
| `redeem.continue` | Continue | Weiter |
| `redeem.personHint` | Only if their phone isn't working. | Nur wenn das Handy nicht geht. |
| `redeem.askManagers` | No phone? Ask {names}. | Kein Handy? Frag {names}. |
| `redeem.alreadyRedeemed` | `Already redeemed: {n} voucher at {place}, {time} \| Already redeemed: {n} vouchers at {place}, {time}` | `Schon eingelöst: {n} Marke bei {place}, {time} \| Schon eingelöst: {n} Marken bei {place}, {time}` |
| `redeem.confirmTitle` | Redeem for {name} | Für {name} einlösen |
| `redeem.hasAvailable` | `{name} has {n} voucher \| {name} has {n} vouchers` | `{name} hat {n} Marke \| {name} hat {n} Marken` |
| `redeem.amount` | How many? | Wie viele? |
| `redeem.confirm` | `Redeem {n} \| Redeem {n}` | `{n} einlösen \| {n} einlösen` |
| `redeem.success` | {n} redeemed for {name}. {left} left. | {n} für {name} eingelöst. Noch {left} übrig. |
| `redeem.next` | Next person | Nächste Person |
| `redeem.notAVoucher` | That is not a voucher code. | Das ist kein Marken-Code. |
| `redeem.cameraDenied` | Camera access was refused. Allow it in your browser settings, or enter the code. | Der Zugriff auf die Kamera wurde verweigert. Erlaube ihn in den Browser-Einstellungen oder gib den Code ein. |
| `redeem.noCamera` | No camera found. Enter the code instead. | Keine Kamera gefunden. Gib stattdessen den Code ein. |
| `redeem.insecure` | The camera only works over a secure connection. Enter the code instead. | Die Kamera geht nur über eine sichere Verbindung. Gib stattdessen den Code ein. |
| `redeem.cameraFailed` | The camera could not be started. Enter the code instead. | Die Kamera konnte nicht gestartet werden. Gib stattdessen den Code ein. |
| `redeem.noPlaces` | You can take vouchers while you are on a shift at a place that takes them, or if you are in charge of one. | Marken annehmen kannst du, während du an einem Ort Schicht hast, der Marken annimmt, oder wenn du dafür verantwortlich bist. |
| `redeem.recent` | Redeemed here recently | Zuletzt hier eingelöst |
| `redeem.recentTotal` | {n} in total | Insgesamt {n} |
| `redeem.recentOwn` | Your recent redemptions here | Deine letzten Einlösungen hier |
| `task.perShift` | `{n} voucher per shift \| {n} vouchers per shift` | `{n} Marke pro Schicht \| {n} Marken pro Schicht` |
| `task.point` | Takes vouchers | Nimmt Marken an |
| `settings.title` | Vouchers | Marken |
| `settings.open` | Vouchers… | Marken… |
| `settings.dialogTitle` | Vouchers for {task} | Marken für {task} |
| `settings.perShift` | Vouchers per shift | Marken pro Schicht |
| `settings.perShiftHint` | Volunteers get this many for each shift once it is over. 0 means none. | So viele bekommen Helfende pro Schicht, sobald sie vorbei ist. 0 heißt keine. |
| `settings.retroHint` | Changes also count for shifts already worked. | Änderungen gelten auch für Schichten, die schon vorbei sind. |
| `settings.isPoint` | Vouchers can be redeemed here | Hier können Marken eingelöst werden |
| `settings.isPointOn` | The people in charge and whoever is on shift here can take vouchers in the app. | Die Verantwortlichen und wer hier gerade Schicht hat, können Marken in der App annehmen. |
| `settings.isPointOff` | This place doesn't take vouchers in the app. It can still accept paper vouchers. | Dieser Ort nimmt keine Marken in der App an. Papiermarken gehen trotzdem. |
| `settings.isDesk` | Volunteer desk: staff on shift can also redeem without a code | Ausgabestelle: Wer hier Schicht hat, kann auch ohne Code einlösen |
| `settings.isDeskHint` | For people whose phone isn't working. Staff pick them from the member list. This needs a team under "Who can book", so only people you chose can staff the desk. | Für Leute, deren Handy nicht geht. Sie werden aus der Mitgliederliste ausgewählt. Dafür braucht die Aufgabe ein Team unter „Wer kann buchen“, damit nur Leute an der Ausgabestelle sitzen, die ihr ausgewählt habt. |
| `settings.saved` | Voucher settings saved. | Marken-Einstellungen gespeichert. |
| `admin.title` | Vouchers | Marken |
| `admin.person` | Person | Person |
| `admin.colAvailable` | Available | Verfügbar |
| `admin.colBalance` | Balance | Stand |
| `admin.colUpcoming` | Still to come | Noch offen |
| `admin.balanceNegative` | More was handed out than is earned now, usually because a shift was changed afterwards. | Es wurde mehr ausgegeben, als jetzt verdient ist, meist weil eine Schicht nachträglich geändert wurde. |
| `admin.left` | Left the event | Nicht mehr dabei |
| `admin.addCorrection` | Add correction | Korrektur hinzufügen |
| `admin.editCorrection` | Edit correction | Korrektur bearbeiten |
| `admin.deleteCorrection` | Delete correction | Korrektur löschen |
| `admin.deleteConfirm` | Delete this correction? | Diese Korrektur löschen? |
| `admin.amount` | Amount | Anzahl |
| `admin.add` | Add | Hinzufügen |
| `admin.takeAway` | Take away | Abziehen |
| `admin.amountHint` | How many vouchers to add or take away. | Wie viele Marken du hinzufügst oder abziehst. |
| `admin.note` | Reason | Grund |
| `admin.saved` | Correction saved. | Korrektur gespeichert. |
| `admin.deleted` | Correction deleted. | Korrektur gelöscht. |
| `admin.afterEventHint` | Vouchers can be redeemed in the app until the event's end date. Volunteers can still see their balance afterwards. | Marken lassen sich in der App bis zum Enddatum der Veranstaltung einlösen. Ihren Stand sehen Helfende auch danach noch. |
| `admin.empty` | Nobody has earned vouchers yet. | Noch hat niemand Marken verdient. |
| `afterEventLink` | See your vouchers | Deine Marken ansehen |
| `noEvent` | Pick an event to see your vouchers. | Wähl eine Veranstaltung, um deine Marken zu sehen. |

**`navigation.json`**: `sidebar.items.vouchers.label` "Vouchers" / "Marken";
`sidebar.items.vouchers.description` "Your vouchers and your code" / "Deine
Marken und dein Code". If the More sheet uses its own keys, add the same
entries there.

**`errorCodes.json`**

| Key | en | de |
|---|---|---|
| `task.forbidden` | Only the people in charge of this task and the organisers can do this. | Das können nur die Verantwortlichen dieser Aufgabe und die Organisator:innen. |
| `task.admin_only_field` | Only organisers can publish a task, change who can book it or its vouchers, or move it to another event. | Nur Organisator:innen können eine Aufgabe veröffentlichen, ändern, wer sie buchen kann oder wie viele Marken es gibt, oder sie in eine andere Veranstaltung verschieben. |
| `task.not_published` | This task isn't published, so only the organisers and its people in charge can open or book it. | Diese Aufgabe ist nicht veröffentlicht. Nur die Organisator:innen und ihre Verantwortlichen können sie öffnen oder buchen. |
| `task.shift_history_admin_only` | This shift has started and people are booked on it, or the change would move it into the past. Only an organiser can do that. | Diese Schicht hat schon begonnen und es sind Leute gebucht, oder die Änderung würde sie in die Vergangenheit verlegen. Das kann nur ein:e Organisator:in. |
| `task.manager_not_event_member` | Only people in this event can be put in charge of its tasks. | Nur Leute aus dieser Veranstaltung können für ihre Aufgaben verantwortlich sein. |
| `task.manager_already` | That person is already in charge of this task. | Diese Person ist für diese Aufgabe schon verantwortlich. |
| `task.manager_not_found` | That person is not in charge of this task. | Diese Person ist für diese Aufgabe nicht verantwortlich. |
| `batch.wrong_task` | Those shifts belong to a different task. Reload the page and try again. | Diese Schichten gehören zu einer anderen Aufgabe. Lade die Seite neu und versuch es noch einmal. |
| `booking.shift_over` | This shift is already over, so it can't be booked or cancelled any more. | Diese Schicht ist schon vorbei und kann nicht mehr gebucht oder abgesagt werden. |
| `booking.shift_started` | This shift has already started. Shifts that earn vouchers can only be booked before they start; ask the people in charge if you're helping anyway. | Diese Schicht hat schon begonnen. Schichten mit Marken lassen sich nur vor Beginn buchen. Wenn du trotzdem hilfst, sag den Verantwortlichen Bescheid. |
| `voucher.not_allowed` | You can only take vouchers here while you are on shift here, or if you are in charge. | Marken annehmen kannst du hier nur während deiner Schicht hier oder wenn du verantwortlich bist. |
| `voucher.manual_not_allowed` | Only the people in charge, the organisers and the staff of a volunteer desk can redeem without a code. | Ohne Code einlösen können nur die Verantwortlichen, die Organisator:innen und wer an einer Ausgabestelle Schicht hat. |
| `voucher.not_a_point` | Vouchers can't be redeemed at this task. | Bei dieser Aufgabe können keine Marken eingelöst werden. |
| `voucher.code_invalid` | This code isn't valid. Ask them to show their code again. | Dieser Code ist ungültig. Bitte darum, den Code noch einmal zu zeigen. |
| `voucher.code_other_event` | This code is for a different event. Ask them to switch to this event in the app and show a new code. | Dieser Code gehört zu einer anderen Veranstaltung. Bitte darum, in der App zu dieser Veranstaltung zu wechseln und einen neuen Code zu zeigen. |
| `voucher.code_used` | This code has already been used. Ask for a new one. (The confirm step shows `vouchers.redeem.alreadyRedeemed` instead when the extensions are present.) | Dieser Code wurde schon benutzt. Bitte um einen neuen. |
| `voucher.code_expired` | This code has expired. Ask for a new one. | Dieser Code ist abgelaufen. Bitte um einen neuen. |
| `voucher.insufficient` | Not enough vouchers. | Nicht genug Marken. |
| `voucher.insufficient_with` | `Not enough vouchers: only {n} left.` | `Nicht genug Marken: nur noch {n} übrig.` |
| `voucher.rate_limited` | Too many tries. Wait a moment and try again. | Zu viele Versuche. Warte kurz und versuch es noch einmal. |
| `voucher.request_conflict` | Something went wrong with this redemption. Close it and scan again. | Bei dieser Einlösung ist etwas schiefgelaufen. Schließ sie und scanne noch einmal. |
| `voucher.pass_not_found` | That code is no longer there. Show a new one. | Diesen Code gibt es nicht mehr. Zeig einen neuen. |
| `voucher.entry_not_found` | That entry could not be found. It may have been deleted. | Dieser Eintrag wurde nicht gefunden. Vielleicht wurde er gelöscht. |
| `voucher.entry_not_editable` | A redemption can't be changed. Add a correction instead. | Eine Einlösung lässt sich nicht ändern. Füg stattdessen eine Korrektur hinzu. |

## Tests

### Backend

Move `act_as(app, user)` from `tests/api/routes/test_teams.py` into
`tests/fixtures/client.py` and re-export it from `conftest.py`. Time-dependent
tests monkeypatch `app.logic.clock.wall_clock_now` rather than relying on
today's date. Shifts that have ended get their bookings inserted directly,
since the API now refuses them on every task.

**The past-dated fixtures.** `tests/fixtures/shifts.py::test_shift` is dated
2026-05-24 and the fixture events lie in mid-2026, so with `booking.shift_over`
on every task the API would refuse them. Moving the fixture dates would shift
hours, reporting and dashboard tests that depend on them. Instead, a fixture
`clock_before_fixture_shifts` in `tests/fixtures/` monkeypatches
`app.logic.clock.wall_clock_now` to 2026-05-01 08:00, and the four modules
that book through the API (`test_bookings.py`, `test_bookings_extended.py`,
`test_booking_conflicts.py`, `test_teams.py`) apply it with `pytestmark =
pytest.mark.usefixtures("clock_before_fixture_shifts")`. The tests about
`booking.shift_over` itself override the clock. Grep `frontend/e2e` for
bookings on past-dated shifts as well; the existing E2E helpers use
`futureDate`.

| File | Cases |
|---|---|
| `tests/logic/test_task_access.py` (new) | `task_access` for: event admin → `admin`; owner → `admin`; superadmin → `admin`; person in charge → `manager`; plain member → None; a stale row of someone who left (row inserted by hand) → None; person in charge of a task in **another** event → None for this task; orphan task (`event_id` NULL) with a manager row → None, superadmin → `admin`; person in charge of **another task in the same event** → None for this task. `require_task_visible`: draft → 403 for a member, 200 for the person in charge; archived task → 403 for a member, but passes with `booked_shift_id` when the member has a booking on that shift; sandbox task → 404 for the superadmin. `check_shift_history` (pure, `now` injected): admin always passes; manager deleting a started booked shift → 403; deleting a started shift with no bookings → passes; deleting a future booked shift → passes; changing date or start of a started booked shift → 403; extending the end of a running booked shift → passes, moving that end to before now → 403; moving a future booked shift so it ends before now → 403 |
| `tests/api/routes/test_task_managers.py` (new) | **Add/remove:** admin adds a member → 201, shows up in `TaskRead.managers`; non-member → 422 `task.manager_not_event_member`; twice → 409 `task.manager_already`; member, person in charge or outsider tries to add → 403 `event.forbidden`; admin removes → 204; person in charge steps down → 204; member removes someone else → 403; removing someone not in charge → 404 `task.manager_not_found`. **Powers**, parametrised over admin / person in charge / member / outsider / person in charge of another task in the **same** event / person in charge of another event's task: PATCH name (200/200/403/403/403/403); PATCH `status`, `team_id` or `event_id` as person in charge → 403 `task.admin_only_field` with `fields`; the same field sent unchanged → 200; DELETE task as person in charge → 403 `event.forbidden`; `POST /shifts/`, `PATCH`/`DELETE /shifts/{id}`, `add-shifts`, `regenerate-shifts` (dry run and real), `DELETE` batch → allowed for admin and person in charge, 403 `task.forbidden` for the rest; `POST /tasks/with-shifts` as person in charge → 403. **Shift history** (clock patched): as person in charge, `DELETE /shifts/{id}` of a started booked shift → 403 `task.shift_history_admin_only`, as admin → 204; `PATCH /shifts/{id}` moving a future booked shift to yesterday → 403, as admin → 200; `DELETE` batch containing a started booked shift → 403 and nothing deleted; real `regenerate-shifts` that would delete a started booked shift → 403, and its dry run lists that shift with `locked: true` and `user_name`. **Drafts:** a person in charge of a draft gets it from `GET /tasks/{id}`, `GET /tasks/`, `GET /tasks/feed`, `shift-window` and `GET /shifts/?task_id=`; a member gets 403 `task.not_published`. **Booking lists:** `GET /shifts/{id}/bookings` → outsider 404; member sees names, with e-mail/phone/notes `None` except on their own row; person in charge of a sibling task in the same event sees them redacted like a member; person in charge and admin see everything; a member with a booking on a shift of an **archived** task gets 200 from `GET /shifts/{id}` and from `GET /shifts/{id}/bookings` (redacted rows), while a member without one gets 403 `task.not_published`; `GET /shifts/` without `task_id` leaves out a draft task's shifts for a member and includes them for its person in charge; `GET /tasks/{id}/bookings` phone only for person in charge and admin; `GET /tasks/{id}/batches` outsider 404. **Flags:** `can_manage` true for the person in charge in get, list, feed and the PATCH response. **Lifecycle:** leaving the event and being removed both delete the rows, and re-joining does not bring them back; `POST /users/{id}/transfer-ownership` removes the source user's rows in the events they no longer belong to; an admin moving the task to another event drops them; deleting the task cascades them. **Create:** `with-shifts` with `manager_ids` creates the rows; a non-member id → 422; `new_event` with ids → 422 |
| `tests/api/routes/test_shifts.py` | `POST /shifts/` with another task's `batch_id` → 400 `batch.wrong_task`. Regenerating away a booked shift leaves the booking `cancelled` with `cancelled_task_name` set, not confirmed with a NULL shift. Rename the classes and tests that still use "task manager" for "event admin": `test_shifts.py::TestShiftsTaskManagerRole` → `TestShiftsEventAdminRole`, `test_reporting.py::TestReportingTaskManagerRole` → `TestReportingEventAdminRole`, `test_user_ownership_transfer.py::test_transfer_forbidden_for_task_manager` → `test_transfer_forbidden_for_event_admin`, and fix their docstrings plus the two in `test_tasks.py` (lines 272 and 300; its class is already `TestTasksEventAdminRole`). Afterwards `task_manager` appears only in the new feature, the historical migration `20260821_0001` and the `tests/fixtures/users.py` docstring that explains the retirement. Update assertions that expect `event.forbidden` on the switched routes |
| `tests/api/routes/test_event_members.py::TestUserDeletionCascades` | Deleting a person in charge removes their row. Deleting the event owner while a task has people in charge: the event goes, the task survives with `event_id` NULL, the row survives and `task_access` refuses. Deleting a volunteer removes their entries and passes. Deleting a redeemer keeps their redemptions with `actor_name`. Deleting the event owner cascades the event's entries. Pattern: `db_session.delete(user)`, `flush()`, `SET CONSTRAINTS ALL IMMEDIATE` |
| `tests/api/routes/test_event_clone.py` | `TestCloneTaskManagers`: with `copy_members`, people in charge who come along keep the role and inactive ones don't; without `copy_members`, nobody does. `vouchers_per_shift`, `is_voucher_point` and `is_voucher_desk` are copied; no `voucher_entries` or `voucher_passes` are created |
| `tests/logic/test_vouchers.py` (new) | Derivation, with `now` injected: only ended shifts earn; an overnight 22:00–02:00 shift earns after 02:00 the next day; untimed shifts earn at midnight; start-only shifts; `end == start` counts as 24 h; cancelled bookings don't count; tasks with 0 are ignored; another event's bookings are ignored; redemptions lower the balance and corrections move it both ways; lowering `vouchers_per_shift` below what was redeemed gives a negative `balance` and `available` 0; deleting a past shift through the API lowers `earned`. `balances()` includes a former member with a non-zero balance and leaves out former members at zero. `redeem_window` with 30 min of grace, untimed and overnight. `redeem_window_dates` at 23:40 includes tomorrow (a 00:05 shift) and at 01:00 includes yesterday (an overnight shift). `VoucherShift.ends_at` is UTC (an 18:00 Berlin summer shift ends at 16:00). `normalize_code` cases. `wall_clock_now` honours `EVENT_TIMEZONE` (monkeypatch the setting) |
| `tests/logic/test_voucher_concurrency.py` (new) | **Not on `db_session`.** Uses two independent `async_sessionmaker(test_engine)` sessions. The setup (user, event, membership, task with 3 per shift, an ended shift, a confirmed booking) is committed for real. (1) Two `redeem(amount=2)` calls via `asyncio.gather`, each inside `async with session.begin()`: exactly one succeeds, the other raises 409 `voucher.insufficient`, and the ledger sum is −2. (2) The same code redeemed twice concurrently with amount 1: one succeeds, one gets 409 `voucher.code_used`. (3) A manual redemption sent twice concurrently with the same `request_id`: one entry, and both calls return it (one with `replayed`). A `finally` block deletes everything committed (events, tasks, users) in its own session, because the test database is shared |
| `tests/api/routes/test_vouchers.py` (new) | **Pass:** a member gets 201 with 6 characters from the alphabet, `ttl_seconds == 120` and `event_name`; a non-member → 403 or 404; issuing again deletes the old unused code (old → 404 `voucher.code_invalid`) but keeps a used one (its status still says `used`) and a held one; status goes active → checking (after a `check`) → used (with `redeemed_amount`), and expired once `expires_at` is set in the past. **Hold:** check, then set `expires_at` in the past: redeem still succeeds within 60 s of the check and fails with `voucher.code_expired` after. **Rotation race:** issue, redeem with a code whose row was deleted by a re-issue (no check) → 404 `voucher.code_invalid`, never a 500. **Other event:** a code issued in event A, redeemed at a point in event B → 409 `voucher.code_other_event`. **Retry:** the same `request_id` twice → one entry, second answer `replayed: true`; a `request_id` used by another redeemer → 409 `voucher.request_conflict`; a used code answers 409 `voucher.code_used` with `amount`, `task_name`, `actor_name` and `used_at`. **Redeem by code:** admin 201; person in charge of the point 201; a volunteer on a running shift 201 (clock patched: 29 min before start allowed, 31 min before → 403, 29 min after end allowed, 31 min after → 403; an untimed shift today allowed); a member not on shift → 403 `voucher.not_allowed`; on shift at another task → 403; unflagged task → 422 `voucher.not_a_point`; another event's task → 404 `task.not_found`; too much → 409 `voucher.insufficient` with `available`, after which the **same code** redeems a smaller amount (nothing was written); twice → 409 `voucher.code_used`; expired → 409 `voucher.code_expired`; garbage → 404. **Manual:** admin and person in charge 201; volunteer on shift → 403 `voucher.manual_not_allowed`; volunteer on shift at a point with `is_voucher_desk` → 201; non-member target → 404 `event.member_not_found`. **Snapshots:** after deleting the point task the entry still shows `task_name`. `check` doesn't consume. A sandbox event → 404 for the superadmin. **Accounts:** `me`; `people/{id}` (admin 200, member reading someone else 403, self 200); `people` (admin 200; member and person in charge 403). **Corrections:** create 201; 0 → 422; blank note → 422; someone who never was in the event → 404; a former member with bookings or entries → 201; member or person in charge → 403; PATCH/DELETE of a correction OK; of a redemption → 409 `voucher.entry_not_editable`; an id from another event → 404 `voucher.entry_not_found`. **Points:** `can_redeem` / `can_redeem_manually` per role (and for desk staff); `managers` listed; `points/{id}/entries` admin and person in charge 200 with every entry, an on-shift redeemer 200 with only their own, a member 403; a task of another event in the path → 404 `task.not_found`. `EventRead` counts. `TaskRead.can_redeem`, including a shift tomorrow at 00:15 with the clock at 23:50 → true. **Member leaving:** removing a member cancels their bookings on unfinished shifts (snapshot set) and keeps the ones on ended shifts |
| `tests/api/routes/test_bookings.py` | A non-member books → 403 `event.forbidden`. A member books a draft task's shift → 403 `task.not_published`; its person in charge → 201. Booking an ended shift → 409 `booking.shift_over` on a task with 0 vouchers and on a voucher task alike; reactivating a cancelled booking on an ended shift → 409. Cancelling one through DELETE or through PATCH with `status=cancelled` → 409. A shift that is running can still be booked |
| `tests/core/test_rate_limit.py` | `RateLimiter(code=...)` raises with that code |
| `tests/logic/test_sandbox_cleanup.py` | Add task manager, entry and pass ids to `_Inventory` / `_inventory` and counts to `_remaining`. A helper `_add_voucher_pass` keeps the census from being vacuously zero, and the docstring's table count goes from 24 to 27. `test_orphans_nothing_anywhere_in_the_database` must stay green |
| `tests/logic/test_sandbox_seed.py` | "Café counter" has a person in charge; "Welcome desk" and "Café counter" take vouchers and "Welcome desk" is a desk; every task has 2 per shift; the visitor has `available >= 1` and exactly one redemption |

Run one pytest at a time (see the memory note on the pre-commit venv sync).
`just check-migrations` must pass after each migration.

### Frontend

- `lib/__tests__/vouchers.spec.ts`: every helper, including the rejections.
- `lib/__tests__/shift-time.spec.ts`: `shiftHasEnded` for timed, overnight,
  start-only and untimed shifts.
- `lib/api-errors` spec: `voucher.insufficient` with `available`.
- **E2E is worth two small specs**, both typing the code, not using the
  camera:
  - `e2e/vouchers.spec.ts`:
    1. The volunteer books a future shift (API helper `bookShift`) on a task
       that has no vouchers yet, in an event that starts yesterday. The admin
       then moves that shift to yesterday with `PATCH /shifts/{id}` (admins
       may change the past), so it has ended without anyone booking an ended
       shift.
    2. The admin sets 2 per shift and flags another task as a point (detail
       page dialog).
    3. Only now does the volunteer's page session start, so its selected
       event carries the new counts. The volunteer opens My vouchers in-app,
       sees 2, opens Show my code and reads the code text.
    4. The admin opens Redeem vouchers on the point, enters the code and
       redeems 1.
    5. The volunteer's dialog shows the redeemed state.
  - `e2e/task-managers.spec.ts`: the admin puts a member in charge; as that
    member, Edit is visible, the task is renamed and a shift is added;
    Delete is not visible, and the draft banner asks an organiser to
    publish.

  Navigate in-app, not by reload (see the CI cookie note). Run `pnpm
  generate-e2e-coverage` afterwards.
- The whole local gate in `frontend/CLAUDE.md` before pushing.

## Docs to update

- `CLAUDE.md`: in "Auth Pattern", the two new gates and a short paragraph on
  vouchers. In "Environment", `EVENT_TIMEZONE`.
- The `app/logic/permissions.py` module docstring.
- `backend/app/api/routes/README.md`: the gate list ("grepping those two
  names must keep finding every check") gains `require_task_manager`,
  `require_task_visible`, `check_shift_history` and
  `require_voucher_redeemer`.
- `docs/SANDBOX.md`: order diagram, seed, invisibility table.
- `.env.example`: `EVENT_TIMEZONE=Europe/Berlin`, with one comment line.
- `app/logic/work_hours.py` docstring: the wall clock.
- A changelog entry (`src/changelog`), describing both features as they
  behave by default. Vouchers do nothing until a task has some.

## Not done (follow-ups)

- **Help alerts** ("we need people now" from the people in charge). Room is
  left for them: `require_task_manager` is the gate for sending, and
  `crud_task_manager.user_ids_for_task` plus the team-request recipient
  pattern (`dispatch_team_join_requested`) give the audience.
- A notification when someone is put in charge.
- People in charge per **location** rather than per task.
- People in charge in reporting, work hours, the venue map's draft shifts
  and `GET /tasks/active-dates`.
- People in charge in the sidebar quick links (`/dashboard/sidebar` lists
  published tasks plus admin-managed events, so a person in charge finds
  their draft on the Tasks page but not in the sidebar) and in the team tab
  of the Availability page (admin-only today). Both are reads that would
  help "the person who fixes the rota"; neither is needed for it.
- A per-person cap on vouchers earned per day, should the trust placed in
  people in charge of voucher tasks turn out to be misplaced (see "What this
  does not prevent").
- Redacting e-mail addresses in the event roster (`GET
  /events/{id}/members`) for non-admins, which would make the booking-list
  redaction complete. Team leads' member pickers read that roster today.
- Attendance (#177). It changes `counts_as_worked()` and nothing else.
- Undoing a redemption. A correction covers it today.
- A CSV export of balances.
- A timezone per event.
- Taking vouchers after the event's end date (seeing the balance afterwards
  is built; redeeming is not).
- Pushing "redeemed" over SSE instead of polling.

## Implementation order

Four packages, built one after another by separate agents. Each one ends
green on its own checks.

Each backend package ends with `just generate-client` and commits
`frontend/src/client` together with its last backend change. Pushing an
OpenAPI change without it makes the *Generate Client* workflow push a
correction commit onto the shared branch, and the next agent would have to
rebase (`frontend/CLAUDE.md`, "Generated files are committed and diffed").

### Backend A: people in charge

0. `app/logic/clock.py` (`utc_now`, `wall_clock_now`) and `EVENT_TIMEZONE`
   (+ validator, `tzdata` in `pyproject.toml`, `.env.example`, compose,
   CLAUDE.md "Environment"), because `check_shift_history` needs the wall
   clock. Hours keep their current clock until Backend B.
1. `app/models/task_manager.py`, registered in `models/__init__.py`.
   Migration `20261030_0001` (down_revision `"20261027_0001"`), round trip,
   `alembic check`.
2. `app/crud/task_manager.py` and `app/schemas/task_manager.py`.
3. `permissions.py`: `TaskAccess`, `task_access`, `can_manage_task`,
   `require_task_manager`, `require_task_visible` (with `booked_shift_id`),
   `check_shift_history`, and the docstring.
4. `app/logic/task_managers.py`: `mark_task_access` and `decorate_task_reads`.
   `TaskRead.can_manage` and `managers`.
5. `app/api/routes/tasks/managers.py`, included in `tasks/__init__.py`.
   `manager_ids` on `with-shifts`.
6. Switch the call sites (tables above), `ADMIN_ONLY_TASK_FIELDS`, draft
   widening (`also_include_task_ids`, also on `GET /shifts/` without
   `task_id`), `GET /shifts/{id}` on `require_task_visible`, booking-list
   redaction and gates, `check_shift_history` on every shift write,
   `batch.wrong_task`, the regenerate snapshot fix, `AffectedBookingInfo`
   (`user_name`, `locked`), and decorated write responses.
7. Membership removal, ownership transfer (`reassign_owner` returns the
   event ids), the move, clone (`_clone_task` returns the task; managers
   added after the flush).
8. Sandbox purge step 2, seed (people in charge only), SANDBOX.md,
   CLAUDE.md, `api/routes/README.md`.
9. Tests listed for A, plus the renamed test classes.
10. `just generate-client`, commit `frontend/src/client`.

### Backend B: vouchers (needs A merged)

What B uses from A, exactly:
- `task_access` / `can_manage_task` / `require_task_manager` /
  `require_task_visible` in `permissions.py`;
- `crud_task_manager.is_manager` and `task_ids_for_user`;
- `logic/task_managers.mark_task_access`, which B extends with `can_redeem`;
- `ADMIN_ONLY_TASK_FIELDS`, which B extends;
- `_clone_task`'s new return value and constructor, to which B adds three
  fields;
- `app/logic/clock.py` and `EVENT_TIMEZONE`;
- `check_shift_history` and `require_task_visible(..., booked_shift_id=)`;
- the purge and seed structure;
- A's revision id as `down_revision`.

Steps:
1. `counts_as_worked()`, and `_tally` on `clock.wall_clock_now()` (the clock
   itself came with A).
2. Task columns (`vouchers_per_shift`, `is_voucher_point`,
   `is_voucher_desk`), `VoucherEntry` (with `request_id`) and `VoucherPass`
   (with `checked_at`, globally unique `code`). Migration `20261030_0002`.
3. `app/crud/voucher.py`: ledger totals, lists, `get_in_event`,
   `lock_ledger`, `issue_pass`, `find_pass_by_code`, `get_pass_for_user`,
   `hold_pass`, `consume_pass`, `find_entry_by_request_id`.
   `crud_task.voucher_counts_by_event`.
   `crud_booking.cancel_unfinished_bookings_in_event`.
4. `app/logic/vouchers.py`: constants, `normalize_code`, `redeem_window`,
   `redeem_window_dates`, `pass_redeemable`, `to_utc`, derivation,
   `account`, `balances`, `available_for`, `check`, `redeem`.
5. `permissions.py`: `voucher_redeemer_kind`, `may_redeem_manually` and
   `require_voucher_redeemer`. `RateLimiter(code=…)` and the two limiters.
6. `app/schemas/voucher.py`. `TaskRead`/`TaskUpdate`/`TaskCreateWithShifts`
   fields, `TaskRead.can_redeem`, `EventRead` counts.
7. `app/api/routes/vouchers.py`, registered in `api/api.py`.
8. Booking guards (membership, `task.not_published`, `booking.shift_over` on
   every task) with the `clock_before_fixture_shifts` fixture for the four
   booking test modules; `remove_member` cancels unfinished bookings.
9. Clone copies the three fields. Purge step 3, seed vouchers, SANDBOX.md,
   CLAUDE.md.
10. Tests listed for B, including the concurrency test.
11. `just generate-client`, commit `frontend/src/client`.

### Frontend A: people in charge (needs backend A merged and `just generate-client`)

1. Split the `TaskDetailView` predicates. Inline display, the managers
   dialog, the editor, step down, and the desktop More dropdown.
2. Router meta, the `TaskEditView`/`TaskAddShiftsView` guards, and the
   team-card gate.
3. `TaskCreateView` people in charge, quick view and list badges and
   delete, roster contact display (phone link, notes column), the
   `BookingDetailView` roster load outside the `Promise.all`, the affected
   bookings dialog (`user_name`, `locked`), print phone column, clone note,
   draft banner variant and mini-map predicate.
4. Removal of the retired admin role toggle.
5. i18n (`duties`, `errorCodes`, `admin`, `common`),
   `e2e/task-managers.spec.ts`, and the local gate.

### Frontend B: vouchers (needs backend B, frontend A and `just generate-client`)

1. `pnpm --prefix frontend add qr-scanner@1.4.2`, then `pnpm dlx
   shadcn-vue@latest add number-field`.
2. `lib/vouchers.ts` with its spec, and the `QrCode.vue` props.
3. `VoucherCodeDialog`, `MyVouchersCard`, `MyVouchersView`, `VoucherHistory`,
   routes (`:eventId?`, the expired-guard exemption) and navigation
   (`VOUCHER_ROUTES` in the bottom nav, `refreshSelectedEvent` calls),
   the `SelectEventView` link.
4. `VoucherScanner`, `VoucherRedeemConfirm` and `RedeemVouchersView`
   (scanner outside any tabs, detection gating, `request_id`).
5. `lib/shift-time.ts` with its spec, and hiding Book and Cancel on ended
   shifts.
6. `TaskVoucherSettingsFields`/`Dialog`, the TaskDetailView badges and
   Vouchers… and Redeem actions, the `TaskCreateView` fields, and the quick
   view badges.
7. `EventVouchers`, `VoucherAdjustmentDialog`, and the EventSettingsView
   People tab.
8. `useAuthenticatedClient` ignore rule, `api-errors` message, i18n
   (`vouchers`, `errorCodes`, `navigation`), tour anchor check,
   `e2e/vouchers.spec.ts`, and the local gate.

## Open question

**Should people in charge of a voucher task be able to create shifts?** The
brief says people in charge create, edit and delete their task's shifts, and
vouchers are a flat amount per shift. Together that lets someone in charge of
a voucher task create many short future shifts for friends who are event
members (see "What this does not prevent"). This plan keeps the brief: the
shift history rule removes the instant and retroactive paths and the ability
to wipe other people's earnings, and the rest is visible to organisers. The
alternative is that, on tasks with `vouchers_per_shift > 0`, creating,
re-timing and deleting shifts stays with the organisers (`403
task.voucher_shifts_admin_only`), at the cost of "can you add a shift at the
bar on Saturday" going back through them for every voucher task. Building
either is a few lines in `check_shift_history`; the default needs no answer
before work starts.

## Review notes

Two critics reviewed this plan against the code (backend correctness;
product and frontend). Their findings were applied, except for the following,
which were rejected in whole or in part:

- **Keep shift structure admin-only on voucher tasks (first fix offered for
  the minting finding).** Rejected as the default, because the brief gives
  people in charge create/edit/delete rights over shifts with no voucher
  exception. The second fix was applied instead (the shift history rule:
  refuse changes that rewrite a booked shift's past). Its "cap shift
  creation" half was not: a minimum length or count would be arbitrary and
  would not stop the short-shift path either. The trade-off is now stated in
  the plan and raised as the one open question.
- **Rename the landing-page sentence or pick another task-level term.**
  Rejected. "Verantwortliche" is the product owner's German term, the
  landing sentence uses "someone in charge" / "Verantwortliche" in its
  everyday sense about events, and the landing page is a prerendered public
  page this feature should not touch. The rest of that finding was applied:
  new strings call event admins "organisers" / "Organisator:innen", and
  "paper tokens" became "paper vouchers".
- **Let the volunteer choose the amount (or a maximum) when showing the
  code.** Rejected. Redemption happens face to face, the volunteer's screen
  shows "{n} used at {place}" within two seconds, the ledger records who
  redeemed, and an organiser can correct a wrong amount. An extra step on
  every code would slow every queue to guard against a rare mistake. The
  desk half of that finding (no manual redemption at a desk staffed by
  volunteers, nobody named to ask) was applied with `is_voucher_desk` and
  the names of the people in charge.
- **Redact e-mails in the event roster for non-admins.** Not done here. Team
  leads' pickers read that roster, so it is a change of its own. The plan
  now says the booking-list redaction is partial, and the roster change is
  listed under "Not done".
- **Show drafts in the sidebar quick links / open the Availability team tab
  to people in charge.** Listed under "Not done" rather than built; neither
  blocks running a task.
- **Pause the scanner with `qr-scanner`'s `pause()` between people, or keep
  the Scan tab mounted and `pause()`/`start()` it.** Rejected after checking
  the library (Context7 `/nimiq/qr-scanner`): `pause()` stops the camera
  stream after 300 ms, which is what the plan wants to avoid. Detections are
  gated in our own code and the scanner sits outside any tabs.
- **Count only bookings created before the shift ended (alternative fix for
  late bookings).** Not chosen. `created_at` survives cancel-and-reactivate,
  so it would need a new column. Refusing to book or reactivate an ended
  shift on every task closes the hole with no schema change. (The review of
  package B showed it closed only half: a *running* shift booked a minute
  before its end still paid in full. Counting only bookings confirmed before
  the start would need that column and would silently pay nothing to a
  helper who joins late, so instead a voucher task's shift that has started
  can no longer be booked, `409 booking.shift_started`; see "Earning
  requires real membership and honest timing".)
- **Stop counting bookings on shifts that end after the membership ended
  (alternative fix for former members).** Not chosen, because a deleted
  membership row leaves no end time. Cancelling the person's unfinished
  bookings when they leave does the same job.
