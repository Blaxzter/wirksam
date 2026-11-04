# People in charge of a task

An event with twenty stands either makes twenty people admin, which lets them
change everything including the member list, or sends every "can you add a shift
at the bar" through the organisers. A person in charge runs one task and nothing
else. The English UI says "person in charge", the German UI "Verantwortliche",
and the code `TaskManager`, `task_managers` and `require_task_manager`. "Lead"
already means a team lead and "organiser" an event admin.

This is separate from teams on purpose. `tasks.team_id` decides who may **book**
a task; people in charge can **fix its rota**. A task can have both, either or
neither.

Three rules do most of the work:

- Being in charge counts only while the person is a member of the task's event.
- The past of a booked shift belongs to the event admins.
- On a task that earns vouchers the shifts belong to the event admins too,
  unless the event allows otherwise.

Vouchers themselves are in [`VOUCHERS.md`](VOUCHERS.md). Design notes:
[`plans/2026-10-30-task-managers-and-vouchers.md`](plans/2026-10-30-task-managers-and-vouchers.md),
amended by
[`plans/2026-11-02-people-in-charge-and-vouchers-followups.md`](plans/2026-11-02-people-in-charge-and-vouchers-followups.md).

## The gates

All of them are in `app/logic/permissions.py` and let event admins and the
superadmin through. Grepping for them finds every check, so do not inline an
equivalent condition.

| Gate | Decides | Refusal |
|---|---|---|
| `task_access` | `"admin"`, `"manager"` or `None`; the rest build on it | |
| `require_task_manager` | Editing the task (`PATCH /tasks/{id}`) and a shift (`PATCH /shifts/{id}`). Returns the level, so the route can refuse what stays with admins | `403 task.forbidden` |
| `require_shift_editor` | Adding, deleting and regenerating: `POST /shifts/`, `DELETE /shifts/{id}`, `POST /tasks/{id}/add-shifts`, `POST /tasks/{id}/regenerate-shifts` (dry run too), `DELETE /tasks/{id}/batches/{batch_id}` | `403 task.forbidden`, `403 task.voucher_shifts_admin_only` |
| `check_voucher_shifts` | The same voucher rule for `PATCH /shifts/{id}`, asked only when a value in `SHIFT_EARNING_FIELDS` changes | `403 task.voucher_shifts_admin_only` |
| `check_shift_history` | A booked shift's past. Pure: the routes pass `has_bookings`. `shift_history_refuses` is the same rule as a flag, for the dry run | `403 task.shift_history_admin_only` |
| `require_task_visible` | Reading one task | `404 task.not_found`, `403 task.not_published` |

`task_access` asks for the event role first and returns `None` for someone with
no role before it reads `task_managers`. That is the membership rule: a row left
behind grants nothing. A task whose event was deleted is the superadmin's alone.

`require_task_visible` checks for a demo before the role, because
`get_event_role` reports the superadmin as owner (see
[`SANDBOX.md`](SANDBOX.md#invisibility)). Drafts and archived tasks are for
event admins and the task's people in charge. With `booked_shift_id`, which `GET
/shifts/{id}` and `GET /shifts/{id}/bookings` pass, someone with a booking of
any status can reopen their own shift after the organisers archive the task.

## What a person in charge may do

They may edit the task's name, description, dates, location and category; within
the two rules below add, edit, delete and regenerate its shifts and batches; see
the contact details of the people booked on it; see it while it is a draft;
redeem at it with or without a code if it is a point; book one of its shifts
that has started (never one that has ended); and step down.

These stay with event admins:

| What | Why |
|---|---|
| `status` | Publishing runs `dispatch_task_published`, which reaches every active account on the installation |
| `team_id` | It decides who may book |
| `event_id` | Moving needs admin rights in both events |
| `vouchers_per_shift`, `is_voucher_point` | Vouchers are currency, so the rate and the places that take them are the organisers' call |
| Deleting the task | It removes the task for everyone |
| Naming, inviting or removing others | A person in charge may only remove themselves |

The fields are `ADMIN_ONLY_TASK_FIELDS` in `api/routes/tasks/crud.py`. A changed
value is refused (`403 task.admin_only_field`, naming the fields), and one sent
with its current value is ignored, so a form that always sends the whole task
keeps working.

### The shift history rule

Hours, and vouchers not settled yet, are derived from booked shifts that have
ended, so whoever rewrites a booked shift's past rewrites other people's hours.
`check_shift_history` binds people in charge, and only on a shift with a
confirmed booking:

- A shift that has started cannot be deleted, and its date and start time cannot
  change. Its end may still move while the shift is unfinished ("we're staying
  an hour longer"), but not once it has ended.
- A shift cannot be moved so that it starts or ends at or before now. Moving
  only the start matters too: next week's 10–12 turned into "since midnight,
  ends in a minute" has not ended yet, but a minute later it has, with the whole
  back-dated length counted as worked.

"Started" is `combine(date, start_time or 00:00) <= now`, on the event wall
clock. The regenerate dry run reports refused shifts as `locked`, so the editor
can warn before the person confirms, and the real run refuses them.

Creating a shift never calls this rule. Nobody can book a shift that has ended,
and one created already running is allowed on purpose ("we forgot the morning
setup shift").

### Shifts of a task that earns vouchers

Every extra or bigger shift earns vouchers, so on a task with
`vouchers_per_shift > 0` adding, re-timing, resizing, deleting and regenerating
shifts stay with the event admins unless `events.managers_edit_voucher_shifts`
is on (default off). A person in charge can still edit the task's details and a
shift's title, description, place and category ("meet at gate B"). Raising the
rate from 0 locks the shifts from then on, and lowering it back to 0 lifts the
lock. With the setting on, the shift history rule still applies.

`TaskRead.can_manage_shifts` tells the client, from the pure
`voucher_shifts_locked`. The task page, the edit screen and the add-shifts
screen hide shift actions on it, never on `can_manage`.

"Edit task" stays available to whoever may edit the task. With the shifts
locked, or with more than one batch, it offers only the details and saves them
with a plain `PATCH`: regenerating the whole task would rebuild every batch from
one schedule. `PATCH /tasks/{id}` carries a rename to the shifts whose titles
the generator wrote (`<name> 10:00-12:00`, `renamed_shift_title`) and to batches
labelled with the old name (`follow_task_rename`), and typed titles stay.
Regenerating is different: it overwrites the title, place and category of every
shift it keeps.

## Who sees what on a task

**Names on the shift list.** Who booked a shift (names, never contact details)
is visible to everyone who may read its task. Three routes show it, so widening
who sees names means changing all of them:

- `GET /shifts/{id}/bookings`, the roster, which also lets a booker of that
  shift in;
- `GET /shifts/?task_id=…&with_bookers=true`, `ShiftRead.bookers`, for all the
  task page's tiles at once. The flag does nothing without a `task_id`, so a
  mixed list never has to decide per shift;
- `GET /tasks/{id}/bookings`.

**Contact details.** E-mail, phone and notes in `GET /shifts/{id}/bookings` go
to event admins, the task's people in charge and each booker on their own row.
Phone numbers in `GET /tasks/{id}/bookings` go to the first two. The redaction
is partial, because `GET /events/{id}/members` shows every member's e-mail
address to every member.

**Finding their own task.** The task lists widen their status filter to the
drafts of tasks the caller is in charge of (`also_include_task_ids`).
`restrict_to_event_ids` stays a hard AND, so a task in an event they left never
comes back. The feed hides fully booked tasks from plain members and always
shows the ones you run, and the sidebar lists the tasks you are in charge of
first (`SidebarTask.is_managed`).

What each member can redeem at a point is in
[`VOUCHERS.md`](VOUCHERS.md#what-a-redeemer-can-see).

## Naming people

| Route | Effect |
|---|---|
| `POST /tasks/{id}/managers` | Puts a picked member in charge |
| `POST /tasks/{id}/managers/invite` | Takes a typed address, see below |
| `POST /tasks/with-shifts` (`manager_ids`, `manager_emails`) | The same two while creating the task |
| Event clone with `copy_members` | Copies the rows of people who come along, without a notice of its own |

All of them are event admins only. There is no list endpoint:
`TaskRead.managers` is the list, and the editor reloads the task after a change.

A typed address that belongs to a member puts them in charge at once (`added`).
Anyone else, with an account or without, gets the same answer (`invited`), so
the dialog cannot be used to find out who has an account.

`task.manager_added` goes to whoever someone else put in charge, by mail and
push. It is not sent when you name yourself, on a clone, or when you accept an
invitation. `task.manager_removed` goes only to someone an organiser took off
the task, in-app and by push, so they learn it before their next edit fails.
Stepping down, leaving, and deleting or moving the task send neither.

### Invitations that carry tasks

These are ordinary event invitations: same table, same token, same
`/invite/{token}` page and accept endpoint, same registration gate.
`event_invitation_tasks` records which tasks one asks the person to run, and
`app/logic/invitations.py::invite_to_task` does the work.

- **One open invitation per address and event.** A new task is added to the
  open, valid one, whose role stays as it was. Expired ones are revoked and
  their links move to the new invitation, so "Invite again" from any task
  re-invites for all of them.
- **`for_tasks_only`** marks what this flow created. Such an invitation is
  revoked when its last task goes, so its link answers "withdrawn" and does not
  make someone a plain member of an event they were only asked to run one task
  in. One from the event settings stays valid and loses the link. Deleting or
  moving a task goes through `crud.event_invitation_task.detach_task` for this.
- **Accepting** (`POST /invitations/{token}/accept`) applies the links of every
  open, valid invitation to that address in the event and marks them all
  accepted, even for someone already a member. Holding a token sent to that
  mailbox shows the person controls the address. A newcomer takes the strongest
  role among them, and `added_by_*` names the organiser who asked, not the
  invitee.
- **Joining another way applies nothing.** Addresses are not verified in this
  app (`users.email_verified` gates nothing), so applying links from the address
  alone would let someone register with an invited address and take over the
  task. The dialog flags the row `is_member_now` and offers "Add now", which
  goes through the member path and takes the link off the invitation
  (`release_task_invitations`).
- **The inviter leaving or being demoted** changes nothing. It is the event's
  invitation, and the other organisers can see and withdraw it. Deleting the
  inviter's account cascades through `invited_by_id`.
- **The accept page** lists the tasks only to the addressee. The token alone
  shows the event, not what its organisers asked of whom.
- **Demos** refuse an invitation (`403 sandbox.invitations_disabled`), and
  putting a member in charge still works. Create-with-shifts passes
  `skip_refusals`, so a refusal comes back as `skipped` and does not roll back
  the task just built.
- **The mail.** `dispatch_event_invitation` sends an account the
  `event.invitation` notification and an address without one a direct mail
  (`logic/invitation_emails.py`). Plain invitations from the event settings take
  the same path. A notice whose `data` has a `token` opens `/invite/{token}`,
  never the event's page, which is a 404 to a non-member of a private event. The
  rule is in three places: `notificationTarget()` in `src/lib/notifications.ts`,
  `public/sw.js` and the e-mail channel.
- **`registration_may_fail`** warns when an allowed-domains list with the
  invitation bypass off would stop the address from registering. It is computed
  from the domain rule alone, never from whether an account exists.

## The limits, and how they hold

Anyone can create an event and so be its organiser, and these mails reach
addresses that never signed up. So targeted invitations are limited, counted in
the database because the counters in `core/rate_limit.py` live in one worker
process.

| Limit | Counted | Refusal |
|---|---|---|
| 200 per organiser per 24 hours | invitations created | `429 invitation.rate_limited` |
| 3 per address per 24 hours, across the installation | invitations created | `429 invitation.address_limited` |
| One mail per invitation per 10 minutes | `last_sent_at` | "Send again": `429 invitation.resend_too_soon`. Inviting into an open invitation: no refusal, `emailed: false` |

The counts include revoked and accepted invitations, because what is limited is
mail going out. Adding a task to an open invitation creates no row, so it counts
against neither daily limit. Both also apply to the invitations from the event
settings, where bulk reports refused addresses in `skipped_rate_limited`. The
superadmin is exempt from the two daily limits, and they are off under `TESTING`
because the E2E fixtures invite the same people into many events. The ten-minute
rule has no exemptions. Sending again keeps the link open for at least another
14 days.

**Counting.** A count followed by an insert only holds if nobody inserts in
between, and there is no row to lock until the invitation exists.
`lock_invitation_quota` takes transaction-scoped advisory locks, the organiser's
first and then the addresses' in sorted order, before any invitation row lock. A
caller inviting several addresses (bulk, create-with-shifts) takes them all up
front. Taken one by one in the order typed, two requests could deadlock.

**Linking versus accepting.** Inviting into an open invitation, putting a member
in charge directly and accepting all lock the address's open invitations first
(`open_for_address(..., for_update=True)`). A task linked while someone accepts
is then either applied or lands on a new invitation, never on a closed one
nobody will apply. A request that waited re-checks "open" against what the other
committed.

**Granting versus leaving.** The routes where an organiser puts someone in
charge read that person's membership `FOR KEY SHARE` (`lock_member_ids`). A
leave's `DELETE` then waits for the grant and its clean-up removes it. Without
that, a leave committing between the check and the insert would miss the row,
and the right would come back when the person re-joined. Role changes do not
touch the key and are not held up. Booking takes the same lock.

**Duplicates.** The insert runs inside `begin_nested()`, so losing the race on
`uq_task_manager_task_user` is a `409 task.manager_already` and leaves the
transaction usable.

## Stepping down, leaving, moving

- **Stepping down** (`DELETE /tasks/{id}/managers/{own id}`) needs no role and
  tells nobody. Removing someone else needs an event admin.
- **Leaving or being removed** (`DELETE /events/{id}/members/{user_id}`) deletes
  the membership first, then the team rows, the task rows
  (`remove_user_from_event_tasks`) and the unfinished bookings, so re-joining
  restores nothing. `POST /users/{id}/transfer-ownership` runs the same
  clean-up, because the source account leaves those events.
- **Moving the task** to another event drops everyone in charge
  (`remove_all_for_task`), since they are members of the source event, and calls
  `detach_task`.
- **Deleting the event** leaves the task with `event_id` NULL and its rows
  inert: `task_access` answers `None` to anyone but the superadmin.

## What this does not prevent

Earnings are a flat amount per shift, so a person in charge who may change a
voucher task's shifts can create many short future shifts and have friends who
are members book them. With one-minute shifts that pays out within minutes, and
the shift history rule does not stop it. What keeps it in check is that it
shows: the shifts are on the task page, the bookings in its roster and the
earnings at the top of the organisers' voucher overview, where a correction
undoes them. An event that wants this ability has to switch it on.

Hours have the same gap on any task: a shift created already running and booked
by a member counts its whole length a minute later, and the fix is a correction.

## Gotchas

- **`TaskManager` has no ORM relationship.** Without `passive_deletes`, deleting
  a task through the ORM would try to NULL `task_id`, so the CASCADE lives in
  the database only. For the same reason the unit of work cannot order inserts
  against `users`: flush new users before adding rows in seeds and tests.
- **`added_by_id` has no foreign key.** A CASCADE would remove the grant when
  the granting admin deletes their account, and SET NULL is the trap in
  [`backend/app/models/CLAUDE.md`](../backend/app/models/CLAUDE.md).
  `added_by_name` is a snapshot.
- **A task read needs decorating.** `can_manage`, `can_manage_shifts`,
  `can_redeem` and `managers` are viewer-relative and default to false or empty,
  so every route returning a `TaskRead`, write routes included, goes through
  `logic/task_managers.py::decorate_task_reads`.
