# People in charge and vouchers: follow-ups

Follow-up work on `feat/task-managers-and-credits` (stacked under
`feat/dashboard-redesign`), after the product owner tried both features. The
original design is
[`2026-10-30-task-managers-and-vouchers.md`](2026-10-30-task-managers-and-vouchers.md);
this note only describes what changes. Scope was agreed with the product owner
beforehand, and their answers to the first draft's open questions are worked in
(see "Decided after review" at the end). The details and edge cases below are
decided here.

A separate design pass is reworking how the voucher and people-in-charge
screens look. This note covers behaviour, data and wording. Wherever it says
where something goes on a screen, the design pass may move it.

## Problem

1. **Nobody hears about being put in charge.** An organiser names Anna as
   person in charge of the bar. Anna gets no notification, so she finds out by
   chance or not at all.
2. **People in charge have to be event members first.** An organiser who wants
   their neighbour to run the grill has to invite them to the event, wait for
   them to accept, and then come back to the task. The dialog can't take an
   e-mail address. Reading the code also turned up two gaps in the existing
   invitations:
   - **A targeted invitation to an address without an account sends nothing.**
     `dispatch_event_invitation` (`logic/notifications/triggers.py`) returns
     early when no user has that address. Its docstring says the invitation "is
     picked up at first sign-in", but nothing in the frontend or backend picks
     it up (`list_pending_for_email` is only used by the registration gate).
     The organiser still sees the toast "Invitation sent".
   - **The invitation notification links to the wrong page.** For an existing
     account the notification carries `event_id` and `token`. The e-mail button
     (`channels/email.py::_build_html`) and the in-app click
     (`components/navigation/NotificationList.vue`) both go to
     `/app/event-settings/{event_id}`, which a non-member of a private event
     gets as a 404. The token is never used.
3. **The volunteer desk is the wrong level.** Who may redeem without a code is
   set per task (`tasks.is_voucher_desk`) and only works if the task also has a
   team. The product owner wants one event-wide rule that organisers can
   understand at a glance.
4. **People in charge can create vouchers out of thin air.** This was the open
   question in the original plan. Someone in charge of a voucher task can add
   short shifts for friends. The product owner decided that by default people
   in charge do not change the shifts of voucher tasks, and an event setting
   can allow it.
5. **Earned vouchers change after the fact.** Earnings are derived from the
   task's current rate and its current shifts every time they are asked for.
   Lowering the rate, deleting a worked shift, deleting the task or moving a
   shift into the future lowers what people earned, possibly below what they
   already spent, and raising the rate pays more for shifts long over. The
   product owner's verdict: "Wieso sollte sich sowas rückwirkend ändern? Wenn
   man die Marken verdient hat, hat man die verdient, und das wird nicht
   rückwirkend geändert."
6. **Two confusing labels.** The organiser overview has "Verfügbar" and "Stand"
   as two columns that only differ when the balance is negative, and the column
   "Noch offen" is unclear. On the redeem page, "Zuletzt hier eingelöst ·
   Insgesamt 4" counts vouchers but sits next to a list of entries, and only
   adds up the entries on screen (the last 20).
7. **Three bugs** the product owner hit (diagnosis under Decision F):
   - a task card on the task list says "0 verfügbar" and shows only dashes;
   - a person in charge does not find their fully booked task (Cafétheke) on
     the task list or in the sidebar;
   - on a phone, the search field on "Meine Buchungen" is squashed to "Suchen.".

## Decisions

### A. Notification when someone is put in charge

- **New notification type `task.manager_added`** in
  `logic/notifications/registry.py`: category `task` (the preference screen
  already has a "Tasks" group, next to `task.published`), classification
  `change` (something you hold changed, like `event.role_changed`), default
  channels `["email", "push"]`, user-configurable. The seeder upserts it on
  startup. No new preference category: preferences are per type and grouped by
  category, and `task` already exists.
- **Scope chain** `[("task", task_id), ("event", event_id)]`, so muting the
  task or the whole event also mutes this.
- **Who gets it:** whoever is put in charge, from all three places that do it:
  `POST /tasks/{id}/managers`, `POST /tasks/with-shifts` with `manager_ids`,
  and the new invite-by-e-mail endpoint when the address belongs to a member
  (Decision B). One notification per person per task.
- **Not when you name yourself.** An organiser who puts themselves in charge
  gets nothing. The dispatcher leaves out the actor, as `dispatch_event_cloned`
  does with the person who cloned.
- **Not on clone.** `clone_event` copies people in charge along with members.
  Those people already get `event.cloned`, and a notice per task would bury it.
- **Not when someone accepts an invitation to be in charge.** They just did it
  themselves. The organisers hear about it through `event.invitation_accepted`
  (Decision B).
- **Removal gets its own type, `task.manager_removed`**, sent only when an
  organiser takes someone else off a task (`DELETE /tasks/{id}/managers/{user_id}`
  with `user_id != current_user.id`). Otherwise the person finds out from a 403
  the next time they try to edit. Category `task`, classification `change`,
  default channels `["push"]` only (in-app and push, no e-mail by default;
  people can switch e-mail on). No notice when someone steps down (they did
  it), leaves the event or is removed from it (the rows go along with the
  membership, and the event removal is the bigger news), when the task is
  deleted (the link would lead to a 404), or when the task is moved to another
  event (organisers only, rare, and they talk to their people).
- **No batching.** No screen puts one person in charge of several tasks in one
  action: the dialog works on one task, and create-with-shifts names several
  people for one task. Several dialogs in a row are separate decisions and get
  separate notifications. The one place that touches many tasks at once (clone)
  sends none. If a bulk "put Anna in charge of these five" ever comes, it should
  send one notification that lists the tasks; nothing needs preparing now.
- **Text** names the organiser, the task and the event, and says what the
  person can now do (i18n below). `data = {"task_id", "event_id"}`, so the
  e-mail button and the in-app click open the task. The removal notice carries
  `task_id` only if the task is published (a person who is no longer in charge
  of a draft can't open it). Otherwise it carries `event_id`.

### B. Inviting non-members to be in charge, by e-mail

- **One field for both.** The member picker in the people-in-charge dialog and
  on the create form also accepts an e-mail address. If what was typed is a
  valid address that matches no member in the list, the dropdown offers
  "Invite {email} by e-mail". Typing a member's address finds the member, as
  the picker already searches e-mail.
- **What happens depends on the address. The organiser can't see which case
  applied, except for members:**
  - It belongs to an **event member**: they are put in charge at once, as if
    picked, with `task.manager_added`.
  - It belongs to an **account that is not a member**, or to **nobody**: the
    address gets an event invitation (role `member`) linked to the task. The
    response is the same in both cases (`status: "invited"`), so the dialog
    can't be used to find out whether someone has an account. Organisers
    already see members' e-mail addresses, so the "member" case gives nothing
    away.
- **Built on the existing event invitation**, not a parallel mechanism. Same
  table, same token, same `/invite/{token}` page, same accept endpoint, same
  registration gate (`has_valid_invitation` already counts an open targeted
  invitation, so invite-only sites need no change). A new link table
  `event_invitation_tasks` records which tasks an invitation asks the person to
  run. On acceptance they become a member and are put in charge of every task
  still linked.
- **One open invitation per address and event.** If the address already has an
  open, valid targeted invitation in this event (from the event settings or an
  earlier task), the task is added to it instead of creating a second one. Its
  role stays as it was (an organiser invitation stays one). If the open
  invitation has expired, it is revoked, a new one is created, and the old one's
  task links move to the new one. That way "invite again" from any task
  re-invites for all of them.
- **`event_invitations.for_tasks_only`** marks invitations this flow created.
  The flag only matters when the last task link goes (withdrawn, task deleted or
  moved). A task-only invitation is then revoked, because the person was only
  ever invited for those tasks. An invitation that existed before (a plain event
  invitation) stays and just loses the link.
- **The e-mail.**
  - **Account exists:** the existing `event.invitation` notification goes out
    with a task-aware text ("… and would like you to be in charge of “Bar”"),
    through `NotificationService`, so the person's preferences apply as for
    every other invitation.
  - **No account:** a transactional mail, sent directly like the verification
    and reset mails (`logic/auth/emails.py`), because there is no `User` to
    notify. It names the inviter, the event with its dates, the tasks and what
    being in charge means, says to create an account **with this address** (or
    sign in), says until when the invitation is valid, and has one button,
    "View invitation", to `/invite/{token}`. Written in the inviter's
    `preferred_language`, which is the best guess for a stranger. No free-text
    message from the organiser: a personal note would make the mail far more
    useful to spammers.
  - **Plain invitations get the mail too.** The same dispatcher sends every
    targeted invitation, so an invitation from the event settings to an address
    without an account now gets the plain variant of the mail (decided after
    review). This fixes the silent invitations of Problem 2 and is a behaviour
    change worth a line in the changelog.
  - **The link fixes:** `_build_html` uses `/invite/{token}` when `data` has a
    `token`, before it looks at `task_id`/`event_id`, and `NotificationList.vue`
    opens `invite-accept` when `data.token` is set.
- **Re-sending is throttled.** Adding a second task to an open invitation sends
  the mail (or notification) again with all tasks listed, unless one went out
  less than 10 minutes ago (`event_invitations.last_sent_at`). In that case the
  response says `emailed: false` and the dialog says the person will see this
  task too when they open the invitation (the accept page always lists the
  current tasks). A "Send again" action does the same, refusing with
  `429 invitation.resend_too_soon` inside the 10 minutes. Sending again moves
  the expiry to 14 days from now.
- **Expiry: 14 days**, the default of the existing invitations. Not tied to the
  task's dates: someone who accepts late becomes in charge of a task that may
  be over, which harms nobody. Expired invitations stay in the dialog marked
  "Expired", with "Invite again".
- **Acceptance** (`POST /invitations/{token}/accept`, extended):
  1. The checks stay as they are (valid, address matches).
  2. Membership is created if missing.
  3. For a **targeted** invitation: every open, valid targeted invitation to
     this address in this event is collected (normally just this one; two
     organisers inviting at the same moment can leave two). The links of all of
     them are applied: a `TaskManager` row for each linked task that still
     exists and still belongs to this event, skipping tasks the person is
     already in charge of. All of them are marked accepted. Holding a token that
     was sent to that mailbox shows the person controls the address, which
     covers the duplicates too.
  4. A targeted invitation is now marked accepted **even if the person was
     already a member**. Today it stays open forever in that case. A link
     invitation keeps its current behaviour (only counted).
  5. `event.invitation_accepted` goes to the event's admins as today, with the
     tasks named when some were applied.
- **Joining another way does not apply task invitations.** If the invitee
  joins through a share link or a join request, their task invitation stays
  open. E-mail addresses are not verified in this app (`users.email_verified`
  gates nothing), so applying links from the address alone would let someone
  register with the invited address and take over the task without ever seeing
  the mail. Instead, the dialog marks such a row "Already in the event now" with
  an "Add now" action, which goes through the member path.
- **What the invitee sees.** `/invite/{token}` lists the tasks they are asked to
  run (`EventInvitationPreview.tasks`), but only to the addressee: for an
  `email_mismatch` the list is empty. After accepting, a single task opens
  directly; with several, the app opens the dashboard as today.
- **Edge cases:**
  - *Task deleted before acceptance:* the link goes with the task (CASCADE). A
    task-only invitation left without links is revoked first
    (`crud_invitation_task.detach_task`, called from `DELETE /tasks/{id}`), so
    the link in the mail answers "This invitation was withdrawn". A plain
    invitation stays valid.
  - *Task moved to another event:* the move already drops the task's people in
    charge. It now also calls `detach_task`, because the invitation is for the
    old event.
  - *Inviter loses admin rights, leaves, or is demoted before acceptance:* the
    invitation stays valid (decided after review), as every event invitation
    does today. It is the event's invitation, not a personal one, and the
    remaining organisers see it in the dialog and in the event settings and can
    withdraw it. Re-checking the inviter at accept time would fail on a state
    the invitee can't see. If the inviter deletes their account, the invitation
    is deleted with it (`invited_by_id` is CASCADE, existing behaviour), links
    included.
  - *Task turned into a draft or archived:* accepting still puts them in charge
    (people in charge see drafts).
  - *Private vs public event:* no difference. A private event stays a 404 to
    the invitee until they accept. A pending join request for the event is
    deleted on acceptance (existing).
  - *Event is a demo:* inviting by e-mail is refused with
    `403 sandbox.invitations_disabled` (`_refuse_if_sandbox`). Putting a member
    in charge in a demo still works as before.
  - *The organiser types their own address:* they are a member, so they are put
    in charge with no notification.
- **Registration modes** (`logic/auth/registration.py`, no change to the gate):
  - `invite`: the open targeted invitation lets the address register, through
    the token in the link or through the address alone.
  - `approval`: with `REGISTRATION_INVITE_BYPASS` on (the default), the invited
    address skips the queue. With it off, the account waits for approval and the
    invitation can only be accepted once it is approved (`CurrentUser`), so the
    mail does not promise "right away".
  - `REGISTRATION_ALLOWED_DOMAINS`: with bypass on, the invitation gets an
    outside address in. With bypass off, someone without an account can't
    register with that address. The invite response then carries
    `registration_may_fail: true` and the dialog warns "If they don't have an
    account yet, they can't create one with this address on this site". The
    flag is computed from the domain rule alone, never from whether an account
    exists, so it gives nothing away.
- **Abuse limits** (agreed after review). Anyone can create an event and so be
  its organiser, and from now on the server mails addresses that never signed
  up. The limits are counted in the database, so they hold across the four
  worker processes and restarts, unlike `core/rate_limit.py`:
  - per inviter: at most 200 targeted invitations created in 24 hours
    (`429 invitation.rate_limited`);
  - per address, across the whole installation: at most 3 targeted invitations
    created in 24 hours (`429 invitation.address_limited`), so nobody can
    mail-bomb one inbox from several events;
  - per invitation: one mail every 10 minutes (`last_sent_at`).

  They apply to the new endpoint and to the existing single and bulk
  invitation creators. Bulk reports refused addresses in a new
  `skipped_rate_limited` list instead of failing the batch. The platform
  superadmin is exempt. Like `RateLimiter`, the checks are off under
  `settings.TESTING`, because the E2E fixtures invite the same seeded people
  into many events; the backend tests switch them on where they test them.
  Demo events can't invite at all (existing). The mail escapes all
  user-supplied text (existing `_build_auth_html` pattern) and its footer says
  why it arrived and that it can be ignored.
- **Only organisers invite.** Naming people in charge is admin-only, and so is
  inviting them. People in charge can't invite others.

### C. Event setting: who may redeem without a code

- **`events.voucher_manual_redeem`**, `"on_shift"` (default: "Auch alle, die
  gerade an einer Einlösestelle Schicht haben") or `"in_charge"` ("Nur
  Organisator:innen und Verantwortliche"). The default comes from the product
  owner. A string rather than a boolean, so the API reads as what it means.
- **`tasks.is_voucher_desk` goes**, with its team requirement, as agreed. With
  `"on_shift"`, anyone with a confirmed booking on a running shift at a point
  (the existing `on_shift` redeemer kind, ±30 minutes) may also pick a person
  **at that point**. This brings back what the team requirement prevented: a
  member who books a running shift at a point that anyone may book can spend
  other people's vouchers a minute later. The settings card says so under that
  option and suggests a team on such points, and every manual redemption
  records `actor_name` and `method="manual"` in the point's entries, so it can
  be traced. Organisers who don't want this pick `"in_charge"`.
- **`may_redeem_manually`** becomes a plain function of the redeemer kind and
  the event: `admin`/`manager` → yes; `on_shift` → only with `"on_shift"`. No
  team lookup, so it no longer needs the session.
- **Migration:** the column is added with `server_default 'on_shift'`, so every
  existing event gets the default. Nothing is released, so there are no
  organisers whose expectations change.
- **Redeem page hint** (only relevant with `"in_charge"`): when the caller may
  not pick a person, "No phone? Ask {names}." with the point's people in charge
  as today, or, when the point has none, "No phone? Ask an organiser." (new).
  With `"on_shift"` an on-shift redeemer gets the "Pick a person" button and no
  hint.
- The task's voucher dialog does **not** mention this setting (product owner):
  it is configured once, in the event settings.

### D. Event setting: may people in charge change shifts on voucher tasks?

- **`events.managers_edit_voucher_shifts`**, boolean, default `false`.
- **Off:** on a task with `vouchers_per_shift > 0`, a person in charge
  (`task_access == "manager"`) can still edit the task's details (`PATCH
  /tasks/{id}`: name, description, dates, location, category). They get
  `403 task.voucher_shifts_admin_only` on:
  - `POST /shifts/`,
  - `PATCH /shifts/{id}` when the body changes `date`, `start_time`, `end_time`
    or `max_bookings` (compared with the current value, as the admin-only
    fields are). Title, description, location and category stay editable ("meet
    at gate B");
  - `DELETE /shifts/{id}`,
  - `POST /tasks/{id}/add-shifts`,
  - `POST /tasks/{id}/regenerate-shifts`, the dry run included, so the editor
    learns it before the person confirms,
  - `DELETE /tasks/{id}/batches/{batch_id}`.

  Capacity (`max_bookings`) counts as a change to the shift because raising it
  lets more people earn, the same lever as adding a shift.
- **On:** today's rules apply, including the shift history rule.
- **The flag only affects people in charge.** Organisers are never limited.
- **Raising `vouchers_per_shift` from 0** on a task whose person in charge
  already created shifts changes nothing retroactively: the shifts stay, shifts
  already over keep earning nothing (Decision G), and from then on the gate
  applies. The voucher settings dialog says, when the task has people in charge
  and the event setting is off, that they will no longer be able to change its
  shifts. Lowering the rate back to 0 lifts the lock again.
- **`TaskRead.can_manage_shifts`** (viewer-relative, next to `can_manage`) tells
  the frontend whether to show shift actions. It is true for organisers, and for
  people in charge when the task earns no vouchers or the event allows it.
- **One gate**, `require_shift_editor` in `permissions.py`, wraps
  `require_task_manager`, plus a pure `voucher_shifts_locked(access, task,
  event)` for the read flag and for `PATCH /shifts/{id}`.

### E. Small fixes from the review

- **Organiser overview** (`EventVouchers.vue`): with Decision G a balance can't
  go below zero, so "Stand" is always the same number as "Verfügbar". It goes,
  with the red negative display and the "more was handed out than is earned"
  explanation. One column, "Verfügbar" / "Available", remains. "Noch offen"
  becomes "Kommen noch" (English stays "Still to come"), with a short
  explanation for the column header. Sorting stays available descending, then
  name. `VoucherBalance.balance` is removed from the API.
- **Redeem page total:** the header shows what was redeemed at this point
  **today** (event wall-clock day), counted on the server over all entries, not
  just the 20 on screen: "Heute: 4 Marken". On-shift redeemers see their own,
  as with the list. Each row shows "2 Marken" instead of a bare "2", so the
  numbers read as vouchers, not entries. `PointRedemptionList.total_amount`
  goes; `today_amount` and `today_count` replace it.

### F. Bugs

**F1. "0 verfügbar" and only dashes on a task card.**
`/tasks/feed?view=list&focus_mode=today` returns each task's shifts only inside
the shared five-day window starting today (`_build_list_feed`). The card counts
`totalAvailableShifts` over those shifts alone
(`TaskQuickViewCard.vue`). A task whose only shift is, say, ten days out is
still listed, because `has_future_shifts` finds that shift, but the card shows
no shift in the window and says "0 verfügbar". The data is right and the label
is wrong: it claims there is nothing to book.
Fix:
- The list view also returns, per task, counted over every shift that has not
  started yet (event wall clock) and not only the window: `open_shifts`,
  `next_shift_date` (full or not) and `next_open_shift_date`. One grouped query.
- The card label uses them: "{n} freie Schichten", or "Alle Schichten belegt"
  when shifts are coming but all are full, or "Keine kommenden Schichten".
- When the visible days hold no shift (after the hide-full filter, if it is on)
  and the next one lies beyond them, the strip says "Nächste Schicht: Sa.,
  14. Nov." with an "Anzeigen" button that moves the strip there (load that
  window through the existing `shift-window` endpoint). The aligned "today"
  window stays the default, because it lines the cards up by date.
- On the same lines, the feed swaps `dt.date.today()` / `dt.datetime.now()`
  (server clock, UTC in Docker) for `clock.wall_clock_now()`.

**F2. The person in charge did not find Cafétheke.** Checked in the dev
database: Cafétheke is published, has three people in charge, and every shift
still to come (3 and 5 November, 2/2 each) is full. Two server-side filters hide
it, and the hide-full filter is not one of them:
- `/tasks/feed` (list and cards, no custom start date) passes `has_future_shifts`,
  which `crud/task.py::_apply_common_filters` turns into "has a shift still to
  come **with a free place**". A fully booked task drops out for everyone,
  organisers and people in charge included.
- `/dashboard/sidebar` (`_sidebar_tasks`) lists only tasks with an open future
  shift, so it drops out there too.

The hide-full filter is a separate bug. It only hides full shift chips inside
the cards (`WeekDayColumns.vue`) and never removes a task, but it sticks:
`stores/eventFilters.ts` saves `hideFullShifts` to localStorage, and the
dashboard's "find a shift" links (`OPEN_SHIFTS_ROUTE` in `lib/dashboard.ts`)
open `/tasks?hide_full=true`, which `readUrlIntoStore` writes into the store.
One click from the dashboard turns the filter on for good.

Fix:
- **Tasks you can manage always show** while their end date has not passed: in
  the feed, the open-shift condition is OR-ed with "task is one I'm in charge
  of" and "task is in an event I organise". Plain members keep the current
  rule, where fully booked tasks are hidden from the default list (decided after
  review). The superadmin skips the condition.
- **The sidebar lists the tasks you are in charge of**, open shifts or not,
  drafts included, first and marked (`SidebarTask.is_managed`). Organisers'
  other tasks are not added: the sidebar is quick links, not the whole event.
  This was in "Not done" of the original plan.
- **`hideFullShifts` is no longer saved** to localStorage. It lives in the URL
  (the store already mirrors to `?hide_full=true`), so a reload keeps it and
  going to Tasks from the navigation starts without it. `locationId` already
  works this way.

**F3. Squashed search on "Meine Buchungen".** The filter row is `flex flex-wrap`
with the search wrapper as `flex-1` (basis 0) next to the date range picker
and the "Show cancelled" button. With basis 0 all three fit on one line, and the
search gets what is left on a 375 px phone, a few dozen pixels, which shows
"Suchen." (the placeholder is "Suchen..."). The vouchers card above it only
made it more visible. Fix: the search takes a full row on phones (`basis-full
sm:basis-0 sm:flex-1 min-w-0`) and the two controls go on the row below. A
mobile pattern for those two (a filter menu like `TaskFilterMenu` on Tasks) is
the design pass's call. The same row on `TasksView.vue` holds only one other
control and is fine.

### G. Earned vouchers are final ("verdient ist verdient")

This replaces two rules of the original plan: "Balances can go negative, and
we accept that" and "changes also count for shifts already worked".

**The rule.** Once a booking's shift has ended and the booking counts as worked
(`work_hours.counts_as_worked()`), the vouchers it earned are fixed:
- Changing a task's `vouchers_per_shift`, up or down, only affects shifts that
  have not ended. A running shift counts as not ended.
- None of these takes back vouchers already earned: deleting a shift, a batch or
  the task; regenerating shifts; moving a shift, also through the event's "shift
  dates" action; moving the task to another event; an organiser cancelling
  bookings by deleting their shifts; a member leaving; or deleting the account
  that created the task (`tasks.created_by_id` cascades).
- A correction can take away at most what the person can still redeem. Lowering
  or deleting an earlier positive correction is held to the same limit.
- So a balance never goes below zero. `available` is the only number;
  `VoucherBalance.balance`, the negative display and its explanation go
  (Decision E).

Worked hours stay derived as before: deleting a worked shift still removes its
hours. Hours are a record the organisers keep correcting (work logs exist for
that). Vouchers are a promise to volunteers, part of which may already be spent
at a stand.

**The mechanism: settle before a change, derive the rest.** Until something
threatens them, an ended booking's vouchers stay derived exactly as today (the
current rate, for a confirmed booking on an ended shift). Every change that
could alter that derivation for an ended booking first **settles** the affected
bookings. It writes one row per booking into a new table, `voucher_earnings`,
with the amount at that moment and a snapshot of the task and the shift. Reads
add the settled rows to the bookings not settled yet.

It is correct because of one invariant: **every ended, worked booking without
an earning row still derives today exactly what it earned when its shift
ended.** Time passing can't break it. A shift that ends derives at the rate in
force then, which stays the current rate until the next rate change, and that
change settles it. The only other things that could break it are deleting,
moving or re-timing shifts and tasks and changing the rate, and every one of
them settles first (call sites below). A settled booking is left out of the
derivation for good, so a settled shift that is moved into the future and ends
again can't earn twice.

**Details:**
- **Idempotent:** `INSERT … ON CONFLICT (booking_id) DO NOTHING`. Settling the
  same booking twice, or from two requests at once, writes one row.
- **Zero rows:** when the rate changes, every ended booking of the task is
  settled, including at a rate of 0. Otherwise raising the rate from 0 would pay
  for shifts already over. Only a rate change writes zero rows
  (`include_zero=True`). Other settlements skip tasks at 0, whose bookings earn
  nothing whatever happens to them.
- **Reads write nothing.** The earned part is one SQL statement: settled rows
  `UNION ALL` confirmed bookings with no earning row (`NOT EXISTS`). Postgres
  gives one statement one snapshot, so a settlement committing at the same
  moment is counted either as derived or as settled, never both and never
  neither. The ledger (redemptions, corrections) stays a second query, as
  today.
- **No lock for settlement.** Settling never changes a total: it turns a derived
  amount into the same stored amount. So a redemption under `lock_ledger` (a
  one-statement earned figure plus the ledger) stays correct while a
  settlement runs, and settlement needs no ledger lock. Redemptions and
  corrections keep the per-volunteer advisory lock; they are the only writes
  that lower a balance.
- **Clock:** settlement takes `clock.wall_clock_now()` once, the same `now` the
  route uses. A shift that ends in the fraction of a second between that moment
  and the commit of, say, its deletion counts as not ended. Accepted.
- **Moving a task to another event:** the earned vouchers stay in the source
  event (settled with the source's `event_id`), and shifts not yet over move and
  earn in the target. This reverses the original plan's "the task's earned
  vouchers move with it": balances and redemption points are per event, and the
  volunteer may not even be a member of the target.
- **History:** `VoucherAccount.shifts` lists settled rows from their snapshot,
  so a deleted shift or task still shows under its old name and time. Zero rows
  are not listed. `VoucherShift.shift_id` and `task_id` become optional (the
  shift or task may be gone).

**Alternatives considered:**
- *Settle on every read* (a settle step before each balance read and
  redemption): every GET would write, including the code dialog's pass-status
  poll every two seconds and the organisers' overview, which covers everyone.
  It adds conflicts and locking to reads and buys nothing, because by the
  invariant the derivation is already exact for bookings not settled yet.
- *Snapshot the rate per shift* (`shifts.vouchers`, updated by a rate change
  only for shifts not yet over): this handles rate changes but not deletions or
  moves. Deleting a shift sets `bookings.shift_id` to NULL and cuts the booking
  off from its task, deleting the task takes the join with it, and a shift moved
  into the future stops being ended. Each needs its own rule or a per-booking
  record, and that record is the earning row.
- *Effective-dated rate history:* the same gap for deletions and moves.
- *Settle at shift end with the existing poller* (`reminder_poller.py`): a poller
  lags. A rate change a minute after a shift ended, before the poller ran, still
  has to settle first. So settle-before-change is needed anyway, and the poller
  would only shrink the set of bookings not yet settled.
- *Earning rows in `voucher_entries`:* earnings are written by the system, never
  edited, may be zero and carry shift snapshots. The table's CHECKs (`kind IN
  ('redemption', 'adjustment')`, `amount <> 0`) and its "corrections are
  editable" rule would all need exceptions. A table of its own keeps both
  simple.

**Settlement call sites.** Each runs in the route's transaction, before the
change, via `vouchers.settle_earnings(session, now=…, task_ids=… | shift_ids=…,
include_zero=…)`:

| Route | Before | Settles |
|---|---|---|
| `PATCH /tasks/{id}` changing `vouchers_per_shift` | `crud_task.update` | `task_ids=[id]`, `include_zero=True` |
| `PATCH /tasks/{id}` moving to another event | `unlink_task_children` | `task_ids=[id]` |
| `DELETE /tasks/{id}` | `cancel_bookings_for_shifts` | `task_ids=[id]` |
| `PATCH /shifts/{id}` changing `date`, `start_time` or `end_time` | `crud_shift.update` | `shift_ids=[id]` |
| `DELETE /shifts/{id}` | `cancel_bookings_for_shifts` | `shift_ids=[id]` |
| `DELETE /tasks/{id}/batches/{batch_id}` | `cancel_bookings_for_shifts` | the batch's shift ids |
| `POST /tasks/{id}/regenerate-shifts` (real run only) | `cancel_bookings_for_shifts` | `shifts_to_delete` |
| `POST /events/{id}/shift-dates` | the `UPDATE`s | the event's task ids |
| `DELETE /users/me`, `DELETE /users/{id}` | `session.delete(user)` | tasks with `created_by_id` = that user (their own earnings go with the account, by CASCADE) |

Not call sites, with reasons:
- Booking cancel or reactivate on an ended shift is refused for everyone,
  admins included (`booking.shift_over`).
- Leaving or being removed from an event cancels only unfinished bookings; the
  ended ones stay confirmed and derived.
- Event deletion removes the event's ledger anyway.
- The sandbox purge deletes everything.
- The regenerate dry run writes nothing.

Attendance (#177) will change `counts_as_worked()`. Marking an ended booking as
a no-show must settle that booking first, like every other change, so a no-show
noted after the shift does not take vouchers back. Taking them back is an
explicit correction, which can't go below zero. The comment on
`counts_as_worked()` says so.

**Corrections:** `POST`, `PATCH` and `DELETE …/vouchers/adjustments` already
take `lock_ledger`. Under it they compute `available` and refuse with `409
voucher.correction_exceeds_available` (extension `available`) when the result
would go below zero: a negative amount above `available`, a `PATCH` whose new
amount lowers it below zero, or deleting a positive correction worth more than
`available`.

**Existing data:** nothing is released, so the migration only creates the
table. Bookings not settled yet are derived exactly as before, so no backfill
is needed. A dev balance that went negative under the old rules shows as 0
available (the `max(…, 0)` stays as a guard) until an organiser corrects it.

## Data

Three migrations. Revision ids come from the generation date (`env.py`), so if a
package is generated on a later day its id changes, but the chain must stay as
below. Each one starts with the house docstring and needs a round trip
(`upgrade`, `downgrade -1`, `upgrade`, `just check-migrations`).

| Package | Revision | File | down_revision |
|---|---|---|---|
| 3 | `20261102_0001` | `20261102_0001_add_voucher_earnings.py` | `"20261030_0002"` |
| 4 | `20261102_0002` | `20261102_0002_event_voucher_settings.py` | package 3's revision |
| 6 | `20261102_0003` | `20261102_0003_invite_people_in_charge.py` | package 4's revision |

### `voucher_earnings` (package 3, `app/models/voucher.py`, class `VoucherEarning`)

Inherits `Base` (`id`, `created_at` = when it was settled, `updated_at`).

| Column | Type | Null | FK | Notes |
|---|---|---|---|---|
| `event_id` | Uuid | no | `events.id` **CASCADE** | indexed |
| `user_id` | Uuid | no | `users.id` **CASCADE** | the volunteer, indexed |
| `booking_id` | Uuid | no | **no FK** | `unique=True, index=True` → one unique index `ix_voucher_earnings_booking_id`: the idempotency key and the `NOT EXISTS` lookup |
| `amount` | Integer | no | – | the rate when settled; may be 0 |
| `task_id` | Uuid | yes | **no FK** | |
| `task_name` | String | no | – | snapshot |
| `shift_id` | Uuid | yes | **no FK** | |
| `shift_title` | String | no | – | snapshot |
| `shift_date` | Date | no | – | snapshot |
| `shift_start_time` | Time | yes | – | snapshot |
| `shift_end_time` | Time | yes | – | snapshot |

`__table_args__`:
- `sa.Index("ix_voucher_earnings_event_id_user_id", "event_id", "user_id")`
- `sa.CheckConstraint("amount >= 0", name="ck_voucher_earnings_amount_non_negative")`

No FK on `booking_id`, `task_id` or `shift_id`, for the reasons
`voucher_entries` has none. A CASCADE would take earned vouchers away with a
deleted shift, task or booking, which is exactly what Decision G forbids. SET
NULL next to `event_id` is the trap in `app/models/CLAUDE.md`. The snapshots keep
the row readable. Never put SET NULL on any FK in this table. Register it in
`app/models/__init__.py`.

### `events` (package 4)

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `voucher_manual_redeem` | String(16) | no | `"on_shift"`, `server_default="on_shift"` | `on_shift` \| `in_charge`. `sa.CheckConstraint("voucher_manual_redeem IN ('on_shift', 'in_charge')", name="ck_events_voucher_manual_redeem")` in a new `Event.__table_args__` and in the migration |
| `managers_edit_voucher_shifts` | Boolean | no | `False`, `server_default=sa.text("false")` | |

### `tasks` (package 4)

- Drop `is_voucher_desk`. Downgrade adds it back as `Boolean NOT NULL
  server_default false`.

### `event_invitation_tasks` (package 6, `app/models/event_invitation_task.py`, class `EventInvitationTask`)

Inherits `Base` (`id`, `created_at`, `updated_at`).

| Column | Type | Null | FK | Index |
|---|---|---|---|---|
| `invitation_id` | Uuid | no | `event_invitations.id` **ON DELETE CASCADE** | `ix_event_invitation_tasks_invitation_id` |
| `task_id` | Uuid | no | `tasks.id` **ON DELETE CASCADE** | `ix_event_invitation_tasks_task_id` |
| `added_by_id` | Uuid | yes | **no FK** | – |
| `added_by_name` | String | yes | – | – |

- `sa.UniqueConstraint("invitation_id", "task_id", name="uq_event_invitation_task")`.
- No ORM relationships, for the reason `TaskManager` has none (an ORM delete
  would try to NULL a NOT NULL column). The unit of work can't order the
  inserts, so flush the invitation before adding a link
  (`crud_invitation.create` already flushes).
- No SET NULL anywhere in this table, so the trap in `app/models/CLAUDE.md`
  can't fire: a user delete that cascades to their event removes the invitation
  (and with it the link) and, through `tasks.created_by_id`, possibly the task
  (and with it the link). `added_by_id` has no FK, like `TaskManager.added_by_id`.
- Links only ever hang off targeted invitations (`email` set). That is enforced
  in the app, since a CHECK can't look across tables.
- Register it in `app/models/__init__.py`.

### `event_invitations` (package 6)

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `for_tasks_only` | Boolean | no | `False`, `server_default=sa.text("false")` | created by the people-in-charge flow; revoked when its last task link goes |
| `last_sent_at` | DateTime | yes | – | naive UTC, `sa.Column(sa.DateTime, nullable=True)`. When the last mail or notification for it was queued; throttles re-sends |

Quota counts run on `event_invitations.created_at` with `invited_by_id = :me`
(indexed) and `email = :address` (indexed). `crud_invitation.create` already
lowercases addresses, so compare with the lowercased address, not
`lower(email)`, to keep the index.

## Who can do what

Changes against the table in the original plan:

| Action | Who |
|---|---|
| Put an event member in charge (pick, or type their address) | event admins |
| Invite an address to be in charge (non-member or no account) | event admins; not in a demo |
| See, send again and withdraw a task's pending invitations | event admins |
| Accept an invitation to be in charge | the addressee, signed in with that address |
| Change the event's voucher rules | event admins |
| Edit a voucher task's details | its people in charge, event admins (unchanged) |
| Add, re-time, resize, delete or regenerate a voucher task's shifts and batches | event admins; its people in charge only when the event allows it (then within the shift history rule) |
| Redeem without a code (pick the person) | event admins, the point's people in charge; with `voucher_manual_redeem = "on_shift"` (the default) also anyone on a running shift at that point |
| Add, change or delete corrections | event admins (unchanged), never below zero |

### Gates in `app/logic/permissions.py`

```python
def may_redeem_manually(kind: RedeemerKind, event: Event) -> bool:
    """admin/manager always; on_shift only when event.voucher_manual_redeem == "on_shift"."""

async def require_voucher_redeemer(
    user: User, session: AsyncSession, task: Task, *, event: Event,
    now: dt.datetime, manual: bool = False,
) -> RedeemerKind:
    """As today; the manual check calls may_redeem_manually(kind, event)."""

#: Shift fields whose change decides who earns how much.
SHIFT_EARNING_FIELDS = ("date", "start_time", "end_time", "max_bookings")

def voucher_shifts_locked(access: TaskAccess, task: Task, event: Event | None) -> bool:
    """True for a person in charge of a task with vouchers_per_shift > 0 in an event
    without managers_edit_voucher_shifts. Pure: the flag on TaskRead uses it too."""

async def require_shift_editor(user: User, session: AsyncSession, task: Task) -> TaskAccess:
    """require_task_manager, then 403 task.voucher_shifts_admin_only when
    voucher_shifts_locked. Loads the event only for a manager on a voucher task."""
```

Callers of `require_shift_editor` (they call `require_task_manager` today):
`POST /shifts/`, `DELETE /shifts/{id}`, `POST /tasks/{id}/add-shifts`,
`POST /tasks/{id}/regenerate-shifts` (dry run too), `DELETE
/tasks/{id}/batches/{batch_id}`. `PATCH /shifts/{id}` keeps
`require_task_manager` and checks `voucher_shifts_locked` only when the body
changes one of `SHIFT_EARNING_FIELDS`.

Update the module docstring (the desk paragraph goes; the new gate and setting
come in) and the gate list in `backend/app/api/routes/README.md`.

## API

All errors go through `raise_problem`, and every new code gets an entry in
`frontend/src/locales/{en,de}/errorCodes.json`.

### Package 1: fixes

- **`FeedTaskItem`** (`schemas/feed.py`), list view only:
  ```python
  #: Shifts that have not started yet (event wall clock) and still have a free
  #: place, over the whole task rather than the five-day window.
  open_shifts: int | None = None
  #: Date of the next shift that has not started, full or not.
  next_shift_date: dt.date | None = None
  #: Date of the next one of those with a free place.
  next_open_shift_date: dt.date | None = None
  ```
  Filled by a new `_upcoming_stats(session, task_ids, now)` in `tasks/feed.py`:
  one `GROUP BY task_id` over shifts with the booking-count subquery and the
  "not started" condition. Move `dashboard.py::_future_shift_condition` to
  `app/crud/shift.py` as `upcoming_condition(today, now_time)` and use it in the
  feed, the sidebar and `crud/task.py`'s `has_future_shifts`, so all three agree.
- **`crud_task.get_multi_filtered` / `get_count_filtered`** get
  `open_shift_exempt_task_ids` and `open_shift_exempt_event_ids`, OR-ed with
  the open-shift condition inside `if has_future_shifts:`. `task_feed` passes
  the caller's `task_ids_for_user` and `manageable_ids`, and passes
  `has_future_shifts=None` for the superadmin (`visible_event_ids is None`).
- **`SidebarTask.is_managed: bool = False`.** `_sidebar_tasks` takes
  `managed_task_ids` and widens three places with `Task.id IN (...)`: the "has
  an open shift" condition, the status filter (drafts), and a leading sort key
  (`case(..., 0, else_=1)`), selecting `Task.id.in_(...)` as `is_managed`. Limit
  stays 10.
- **`PointRedemptionList`**: `items`, `today_count: int`, `today_amount: int`
  (positive). `total_amount` is removed. New
  `crud_voucher.point_totals_since(session, *, event_id, task_id, actor_id,
  since) -> tuple[int, int]`, with `since =
  vouchers.to_utc(dt.datetime.combine(wall_now.date(), dt.time()))`.

### Package 2: notifications

- `registry.py`: `TASK_MANAGER_ADDED` and `TASK_MANAGER_REMOVED` (Decision A),
  appended to `ALL_NOTIFICATION_TYPES`.
- `triggers.py`:
  ```python
  async def dispatch_task_manager_added(
      *, task_id: uuid.UUID, user_ids: list[uuid.UUID], actor_id: uuid.UUID
  ) -> None
  async def dispatch_task_manager_removed(
      *, task_id: uuid.UUID, user_id: uuid.UUID, actor_id: uuid.UUID
  ) -> None
  ```
  Each opens its own session, loads the task and the event name, drops the
  actor, inactive accounts (as `dispatch_event_cloned` does) and people who are
  no longer members, and calls `NotificationService.notify` once with
  `scope_chain=[("task", id), ("event", event_id)]`. `actor` in the text is
  `actor.name or actor.email`.
- `tasks/managers.py` imports both by name at module level (so tests can
  replace them, as `test_team_notifications.py` does with `teams.py`) and queues
  them through `BackgroundTasks`: `add_task_manager` when `body.user_id !=
  current_user.id`, `remove_task_manager` when removing someone else.
  `create_task_with_shifts` queues one `dispatch_task_manager_added` with all
  `manager_ids` minus the creator.
- `messages.py`: a helper `quoted_list(names: list[str], lang: str) -> str` that
  renders “Bar”, “Grill” and “Café” / „Bar“, „Grill“ und „Café“, for this
  package's texts and package 6's.

### Package 3: earned vouchers are final

- **`app/logic/vouchers.py`:**
  ```python
  async def settle_earnings(
      session: AsyncSession, *, now: dt.datetime,
      task_ids: Sequence[uuid.UUID] | None = None,
      shift_ids: Sequence[uuid.UUID] | None = None,
      include_zero: bool = False,
  ) -> int:
      """Freeze what ended, worked bookings on these tasks or shifts have earned,
      before a change that would alter it (Decision G). Returns rows written.

      Candidates: counts_as_worked(), task.event_id not NULL, shift.date <=
      now.date() (a cheap prefilter; overnight shifts dated yesterday end today),
      no voucher_earnings row yet, and task.vouchers_per_shift > 0 unless
      include_zero. Kept in Python where shift_ends_at(...) <= now. Inserted with
      postgresql insert(...).on_conflict_do_nothing(index_elements=["booking_id"])."""
  ```
  It must not import `app.logic.permissions` (the existing cycle rule).
- **`_voucher_shifts` becomes the one-statement union**: settled rows of the
  event (`amount > 0`, from their snapshot, `completed=True`) `UNION ALL` the
  current query plus `NOT EXISTS (SELECT 1 FROM voucher_earnings e WHERE
  e.booking_id = bookings.id)`. Unsettled rows keep `completed = ends <= now`
  and count as earned or upcoming as today. `_tally`, `available_for`,
  `account` and `balances` read through it unchanged.
- **`schemas/voucher.py`:** `VoucherBalance` loses `balance` (`available` stays,
  computed as `max(earned - redeemed + adjusted, 0)` as a guard).
  `VoucherShift.shift_id` and `task_id` become `uuid.UUID | None`. Add
  `settled: bool = False`, so the client can tell a frozen row (shown from its
  snapshot) from a live one.
- **The call sites** in Decision G's table, each getting `now =
  clock.wall_clock_now()` (most routes already have it).
- **Corrections** (`routes/vouchers.py`): after `lock_ledger`,
  `available_for(...)`, then the checks in Decision G, raising `409
  voucher.correction_exceeds_available` with `extensions={"available": n}`.
- **`work_hours.counts_as_worked()` docstring:** a change to it for an ended
  booking must call `settle_earnings` first (#177).

### Package 4: event voucher settings

- `Event` columns (Data). `schemas/event.py`:
  ```python
  VoucherManualRedeem = Literal["on_shift", "in_charge"]
  class EventUpdate(BaseModel):
      ...
      voucher_manual_redeem: VoucherManualRedeem | None = None
      managers_edit_voucher_shifts: bool | None = None
  class EventRead(EventBase):
      ...
      voucher_manual_redeem: VoucherManualRedeem = "on_shift"
      managers_edit_voucher_shifts: bool = False
  ```
  Not on `EventCreate`: a new event starts with the defaults. `update_event`
  drops an explicit `null` for these two (NOT NULL columns), like
  `_NOT_NULL_VOUCHER_FIELDS` does for tasks. Gate unchanged (`require_event_role`
  admin). Allowed in demos.
- **Remove `is_voucher_desk`** from `TaskBase`, `TaskUpdate`,
  `TaskCreateWithShifts`, the `desk_needs_point` validator, `ADMIN_ONLY_TASK_FIELDS`,
  `_NOT_NULL_VOUCHER_FIELDS`, the desk forcing in `PATCH /tasks/{id}`
  (`tasks/crud.py`), `create_task_with_shifts`, `_clone_task` and the seed. An
  old client that still sends the field is ignored (pydantic's default
  `extra="ignore"`).
- **`VoucherPointRead`**: remove `is_desk`. `can_redeem_manually =
  kind is not None and may_redeem_manually(kind, event)`.
- **`vouchers.py` routes**: `_event_for` already returns the event; pass it to
  `require_voucher_redeemer(..., event=event)` in `check`, `redeem` and
  `points/{task_id}/entries`.
- **`TaskRead.can_manage_shifts: bool = False`** (viewer-relative).
  `logic/task_managers.mark_task_access` loads `managers_edit_voucher_shifts`
  for the distinct event ids in one query and sets `can_manage_shifts =
  can_manage and not voucher_shifts_locked(access, read, event)`. The
  `_TaskAccessEntry` protocol gains `vouchers_per_shift` and `can_manage_shifts`.
  `FeedTaskItem` inherits it.
- **Clone** (`clone_event`): copy both settings onto the new event, next to the
  lines that reset `is_featured`.

### Package 6: inviting people in charge

New routes in `app/api/routes/tasks/managers.py`:

| Method | Path | Gate | Body → Response |
|---|---|---|---|
| POST | `/tasks/{task_id}/managers/invite` | `require_event_role(task.event_id, "admin")`; `_refuse_if_sandbox` before anything is mailed | `TaskManagerInvite {email}` → **201** `TaskManagerInviteResult` |
| GET | `/tasks/{task_id}/managers/invitations` | admin | → `list[TaskManagerInvitationRead]` (open = not revoked, not accepted; expired ones included and flagged) |
| POST | `/tasks/{task_id}/managers/invitations/{invitation_id}/resend` | admin | → `TaskManagerInvitationRead` |
| DELETE | `/tasks/{task_id}/managers/invitations/{invitation_id}` | admin | → **204** |

`_refuse_if_sandbox` moves from `routes/events.py` into `app/logic/sandbox/guards.py`
(or similar) so both routers can import it without importing each other.

```python
# app/schemas/task_manager.py
class TaskManagerInvite(BaseModel):
    email: EmailStr

class TaskManagerInvitationRead(BaseModel):
    id: uuid.UUID                      # the event invitation
    email: str
    invited_by_name: str | None = None
    created_at: dt.datetime
    expires_at: dt.datetime | None = None
    last_sent_at: dt.datetime | None = None
    expired: bool = False
    #: The address now belongs to an event member (they joined another way):
    #: the dialog offers "Add now" (the invite endpoint's member path).
    is_member_now: bool = False

class TaskManagerInviteResult(BaseModel):
    status: Literal["added", "invited", "skipped"]
    manager: TaskManagerBrief | None = None          # added
    invitation: TaskManagerInvitationRead | None = None  # invited
    #: A mail or notification went out with this call (False inside the
    #: 10-minute re-send window, or when added).
    emailed: bool = False
    #: Domain rule with bypass off: someone without an account can't register
    #: with this address. Never depends on whether an account exists.
    registration_may_fail: bool = False
    #: Only from create-with-shifts, which reports instead of failing:
    #: "rate_limited" | "address_limited" | "sandbox".
    skipped_reason: str | None = None
    email: str | None = None           # echoed, so the create form can match results
```

**`POST …/managers/invite`**, in this order:
1. Task exists (`404 task.not_found`), has an event (else `422
   task.manager_not_event_member`), caller is admin (`403 event.forbidden`).
2. Lowercase the address. If it belongs to an account that is a member
   (`crud_user.get_by_email` + membership, locked `FOR KEY SHARE` with
   `lock_member_ids` as the add route does): if already in charge, `409
   task.manager_already`. Otherwise add the row and remove this task's link from
   any open invitation for that address (detach rules apply), then queue
   `dispatch_task_manager_added` unless it is the caller. Return `status:
   "added"`.
3. Otherwise refuse demos (`403 sandbox.invitations_disabled`). Find open
   targeted invitations for the address in this event
   (`find_pending_for_email`).
   - A valid one that is already linked to this task: `409
     task.manager_already_invited`.
   - A valid one: add the link. Mail unless `last_sent_at` is within 10
     minutes.
   - An expired one: `check_new_invitation_quota`, create a new invitation
     (`role="member"`, `expires_in_days=14`, `for_tasks_only` copied from the
     old one), move the old links over, revoke the old one, add this task's
     link, and mail.
   - None: `check_new_invitation_quota`, create (`for_tasks_only=True`), link,
     mail.

   "Mail" means: set `last_sent_at = utc_now`, push `invitation.expires_at` out
   to at least 14 days from now, and queue `dispatch_event_invitation(invitation_id=…)`.
4. Return `status: "invited"`, with `registration_may_fail =
   bool(policy.allowed_domains) and not policy.invite_bypass and not
   email_domain_allowed(email, policy.allowed_domains)`
   (`registration_policy()`).

**`DELETE …/invitations/{invitation_id}`**: `404
task.manager_invitation_not_found` unless the invitation is in the task's event,
open, and linked to this task. Removes the link, then revokes the invitation if
it is `for_tasks_only` and has no links left.

**`POST …/resend`**: same 404 rule. An expired invitation is answered `409
invitation.expired` (the dialog offers "Invite again", which is the invite
endpoint). Within 10 minutes of `last_sent_at`: `429
invitation.resend_too_soon`. Otherwise "mail" as above.

**Create with people in charge by e-mail.** `TaskCreateWithShifts` gets
`manager_emails: list[EmailStr] = Field(default=[], max_length=20)`,
deduplicated case-insensitively. With `new_event` it must be empty (`422
task.manager_not_event_member`, as for `manager_ids`). After the task and the
`manager_ids` rows exist, each address goes through the invite logic above, but
a quota hit or a demo event becomes a `status: "skipped"` entry instead of
an error. Raising would roll back the task the organiser just built. An
address of a member already added through `manager_ids` is skipped silently.
`TaskCreateWithShiftsResponse.manager_invites: list[TaskManagerInviteResult] =
[]`.

**Shared logic** in a new `app/logic/invitations.py`:

```python
INVITATIONS_PER_INVITER_PER_DAY = 200
INVITATIONS_PER_ADDRESS_PER_DAY = 3
RESEND_AFTER = dt.timedelta(minutes=10)
INVITATION_TTL_DAYS = 14

async def check_new_invitation_quota(
    session: AsyncSession, *, inviter: User, email: str, now: dt.datetime
) -> None:
    """429 invitation.rate_limited / invitation.address_limited. No-op for the
    superadmin and under settings.TESTING (tests switch it on where needed)."""

def may_resend(invitation: EventInvitation, now: dt.datetime) -> bool
async def invite_to_task(session, *, task, inviter, email, now) -> TaskManagerInviteResult
    # the invite endpoint's steps 2-4, shared with create-with-shifts
```

**`app/crud/event_invitation_task.py`** (instance `event_invitation_task`):
`add(session, *, invitation_id, task_id, added_by)` (inside `begin_nested`;
`IntegrityError` → `409 task.manager_already_invited`), `is_linked`,
`remove`, `move_links(session, *, from_id, to_id)`,
`tasks_for_invitations(session, *, invitation_ids) -> dict[uuid, list[Task]]`,
`open_invitations_for_task(session, *, task_id) -> list[EventInvitation]`,
`open_for_address(session, *, event_id, email) -> list[EventInvitation]` (open
and valid), and `detach_task(session, *, task_id)`. The last one revokes every
open `for_tasks_only` invitation whose only link is this task, then deletes the
task's links.

**Existing invitation routes:**
- `create_event_invitation` (targeted) and `create_event_invitations_bulk`:
  `check_new_invitation_quota` per address. Bulk collects refusals in
  `EventInvitationBulkResult.skipped_rate_limited: list[str] = []`. Both set
  `last_sent_at` when they queue the mail.
- `list_event_invitations`: `EventInvitationRead` gains
  `tasks: list[InvitationTaskBrief] = []`, `for_tasks_only: bool = False` and
  `last_sent_at: dt.datetime | None = None` (one `tasks_for_invitations` query).
- `preview_invitation`: `EventInvitationPreview.tasks: list[InvitationTaskBrief]
  = []`, filled only when the address matches (valid, or already a member).
- `accept_invitation`: Decision B, steps 1–5. The response stays `EventRead`
  (the E2E `addMember` helper and the accept page use it); the page reads the
  tasks from the preview it already has.
- `DELETE /tasks/{id}` (`tasks/crud.py`) calls `detach_task` before deleting;
  the move branch of `PATCH /tasks/{id}` calls it next to
  `remove_all_for_task`.

```python
# app/schemas/event_invitation.py
class InvitationTaskBrief(BaseModel):
    task_id: uuid.UUID
    name: str
    start_date: dt.date
    end_date: dt.date
```

**Dispatch** (`triggers.py::dispatch_event_invitation`, reworked):
- Load the invitation, its task names (`tasks_for_invitations`), the event and
  the inviter.
- If an account has the address: `NotificationService.notify` with type
  `event.invitation`, message key `event.invitation.tasks` when there are tasks
  (else `event.invitation`), `data={"event_id", "token"}`, scope `("event",
  id)`.
- Else: `invitation_emails.send_event_invitation_email(...)`, for task and
  plain invitations alike.
- Fix the docstring ("picked up at first sign-in" is not true).

**`app/logic/invitation_emails.py`** (new):
`send_event_invitation_email(*, email, inviter_name, event, task_names, token,
expires_at, language) -> bool`. It builds the title and body from the message
keys `invite.email` / `invite.email.tasks` / `invite.email.expiry` and sends one
call to action, "View invitation", to `{FRONTEND_HOST}/invite/{token}`. Factor
the delivery out of `logic/auth/emails.py::_send_action_email` into a reusable
`send_action_mail(*, to, language, title, text_body, action_url, action_label,
footer)`, keeping its behaviour: `emails_configured` only, log the link when
SMTP is missing, never raise. The auth mails keep `transactional_footer`; this
mail uses the new `email.invite_footer`.

**Email button and in-app link** (`channels/email.py::_build_html`): `if "token"
in data: action_link = f"{frontend_url}/invite/{data['token']}"`, first.

**`event.invitation_accepted`**: `dispatch_event_invitation_accepted` gets
`task_ids: list[uuid.UUID] = []` and uses `event.invitation_accepted.tasks`
when it is not empty.

### Error codes

| Status | Code | Raised by | Package |
|---|---|---|---|
| 409 | `voucher.correction_exceeds_available` (`available`) | creating, changing or deleting a correction that would take the balance below zero | 3 |
| 403 | `task.voucher_shifts_admin_only` | `require_shift_editor`, `PATCH /shifts/{id}` | 4 |
| 403 | `voucher.manual_not_allowed` | existing; new wording (the desk is gone) | 4 |
| 409 | `task.manager_already_invited` | invite | 6 |
| 404 | `task.manager_invitation_not_found` | withdraw, resend | 6 |
| 429 | `invitation.rate_limited` | quota per inviter | 6 |
| 429 | `invitation.address_limited` | quota per address | 6 |
| 429 | `invitation.resend_too_soon` | resend | 6 |
| 409 | `invitation.expired` | resend of an expired one (also existing as 410 on accept) | 6 |
| 403 | `sandbox.invitations_disabled` | invite by e-mail in a demo (existing code) | 6 |

Existing codes with no entry in `errorCodes.json` today, which the new screens
surface, so package 7 adds them: `event.already_member`, `event.already_invited`,
`event.invitation_not_found`, `invitation.not_found`, `invitation.event_gone`,
`invitation.revoked`, `invitation.already_used`, `invitation.email_mismatch`.

## Side effects handled

- **Leaving or being removed from an event** deletes the person's task rows
  (existing). Their open task invitations don't exist, because they were a
  member. Their ended bookings stay confirmed, so what they earned stays.
- **User deletion:** the tasks the user created are settled before the delete
  (Decision G), so other volunteers keep what they earned on them. The user's
  own bookings, ledger and earnings go with the account (CASCADE). The inviter's
  invitations cascade (existing), and their links with them. Covered in
  `TestUserDeletionCascades`.
- **Event deletion:** invitations cascade from the event, links from the
  invitations, and `voucher_earnings` with the rest of the event's voucher rows.
  Tasks survive with `event_id` NULL (existing), and their links are already
  gone.
- **Event clone:** invitations, links and earnings are not copied (as before).
  The two event settings are copied.
- **Sandbox purge** (`logic/sandbox/cleanup.py`): step 3 deletes
  `event_invitation_tasks` by task ids before `tasks`. Step 4 deletes
  `voucher_earnings` by event next to `voucher_passes` and `voucher_entries`.
  Both would cascade but are spelled out, as the teams are. Update the order
  diagram in `docs/SANDBOX.md` and the table count in
  `test_sandbox_cleanup.py`'s docstring (27 → 29). The seed never creates
  links or earnings.
- **Notifications to demo guests** are already skipped by `NotificationService`.

## Seeds (`logic/sandbox/seed.py`)

- `_TaskSpec.voucher_desk` goes, with `is_voucher_desk=` in the task insert. The
  Welcome desk stays a point.
- `_seed_redemption` picks the point as `spec.voucher_point and spec.in_charge`
  (the Café counter) instead of "point but not desk".
- The seeded event keeps the defaults: `on_shift`, so on-shift staff at the
  Welcome desk and the Café counter can pick a person; and `false`, so the
  teammate in charge of the Café counter (2 vouchers per shift) can't change its
  shifts, which shows that default. Check that no tour step asks a person in
  charge to add a shift on a voucher task.
- Earnings stay derived for the seeded bookings; no `voucher_earnings` rows.
- `docs/SANDBOX.md` seed paragraph: drop "(the volunteer desk)".

## Frontend

Paths are relative to `frontend/src/`. Each backend package ends with `just
generate-client`, and each frontend package starts by checking that it leaves
no diff. The viewer's id is `authStore.profile?.id`. Event admins are
"organisers" / "Organisator:innen" in the UI.

### Package 1: fixes

- `components/tasks/quick-view/TaskQuickViewCard.vue`:
  - remove `totalAvailableShifts`. The label shows
    `duties.tasks.quickView.openShifts` (count `task.open_shifts`), or
    `allTaken` when `open_shifts === 0 && next_shift_date`, or `noUpcoming`;
  - the empty-window hint: when every day in `days` has no shift after the
    hide-full filter, and `nextDate = hideFullShifts ? next_open_shift_date :
    next_shift_date` lies on or after `rangeEnd`, show `nextShiftOn` with a
    `jumpTo` button. `jumpTo(date)` sets `rangeStart = date`, `rangeEnd =
    date + numDays` and calls `fetchDays(date, numDays)`; swiping back still
    works (`hasMorePrevious`). Pass the state into `WeekDayColumns.vue` or
    render it over it; layout is the design pass's.
  - Add `components/tasks/quick-view/__tests__/TaskQuickViewCard.spec.ts`
    (label cases, the hint appears and `jumpTo` requests the right window).
- `stores/eventFilters.ts`: drop `hideFullShifts` from `PersistedFilters` and
  `persistable`, initialise it to `false`. Update
  `stores/__tests__/eventFilters.spec.ts` (the restore and cross-instance cases
  that expect `hideFullShifts: true`).
- `components/navigation/AppSidebar.vue` (+ `stores/sidebar.ts` type): a task
  with `is_managed` gets an "in charge" marker: a `ShieldCheck` icon badge with
  the tooltip `navigation.sidebar.badges.inCharge`, plus the open-shift count
  when it is above 0. Drafts keep their status badge. Update
  `stores/__tests__/sidebar.spec.ts` if it pins the payload shape.
- `views/bookings/MyBookingsView.vue`: the search wrapper becomes `relative
  basis-full sm:basis-0 sm:flex-1 min-w-0` (F3).
- `views/vouchers/RedeemVouchersView.vue`: the header shows
  `vouchers.redeem.recentToday` with `recent.today_amount`, shown whenever
  `recent` is loaded (also at 0). Each row's amount reads
  `vouchers.redeem.rowAmount`.

### Package 2: notifications

- `locales/{en,de}/notifications.json`: `types.task.manager_added` and
  `types.task.manager_removed` (`name`, `description`). The preference screen
  picks them up by category. No other UI: the in-app list already opens
  `task_id`.

### Package 3: earned vouchers are final

Part of the package, because removing `VoucherBalance.balance` breaks the
type-check of the screens that read it:
- `components/events/EventVouchers.vue`: drop the `colBalance` column, the
  `anyNegative` notice and the red negative styling (table, phone cards and the
  person dialog). `colAvailable` stays the big number. `colUpcoming` gets the
  header hint `colUpcomingHint`.
- `components/events/VoucherAdjustmentDialog.vue`: "Take away" is capped at what
  the person can still redeem (when editing: plus the correction's own current
  effect). The amount field's maximum and the message `admin.takeAwayMax`
  replace the "balance will be {n}" warning (`admin.belowZero`). A server refusal
  arrives as `voucher.correction_exceeds_available`.
- The delete-correction confirm shows the server's refusal through
  `toastApiError`; no extra pre-check.
- `components/vouchers/VoucherHistory.vue`: settled rows (`settled: true`) look
  like other earned shifts. `shift_id`/`task_id` may be null, so no link to the
  task for those.
- `components/tasks/vouchers/TaskVoucherSettingsFields.vue`: `settings.retroHint`
  is replaced by `settings.rateHint`.
- `lib/api-errors.ts`: `voucher.correction_exceeds_available` builds its message
  with `available` (`…_with`), as `voucher.insufficient` does; add a spec case.

### Package 4: event voucher settings, frontend lines forced by the backend

Removing `is_voucher_desk` and `is_desk` breaks the type-check of the files that
use them, so this package removes them:
- `components/tasks/vouchers/TaskVoucherSettingsFields.vue`: remove the desk
  switch, the `isDesk` model, the `teamId` prop and the `deskNeedsTeam`
  warning. Nothing replaces them: the dialog does not mention who may redeem
  without a code (Decision C).
- `components/tasks/vouchers/TaskVoucherSettingsDialog.vue` and
  `views/tasks/TaskCreateView.vue`: drop `isDesk` / `isVoucherDesk` and
  `is_voucher_desk`.

### Package 5: event voucher settings, the new screens

- New `components/events/EventVoucherSettings.vue`: a card in the **Details**
  tab of `views/events/EventSettingsView.vue`, under `EventEditForm`, shown when
  `canManage && usesVouchers`. A `RadioGroup` (`components/ui/radio-group`) for
  `voucher_manual_redeem` with the warning under the `on_shift` option, and a
  switch row for `managers_edit_voucher_shifts` whose hint changes with the
  state. Save with `PATCH /events/{id}` (only these two fields), toast
  `vouchers.eventSettings.saved`, then `authStore.refreshSelectedEvent(id)`.
- `components/tasks/vouchers/TaskVoucherSettingsDialog.vue`: show
  `settings.managersLockedHint` when `perShift > 0`, `task.managers.length > 0`,
  and the selected event is the task's event with
  `managers_edit_voucher_shifts === false`.
- `views/vouchers/RedeemVouchersView.vue`: `askManagers` stays for a point with
  people in charge; a point without them shows `redeem.askOrganisers`. Both only
  when `!point.can_redeem_manually`.
- `views/tasks/TaskDetailView.vue`: `canManageShifts = computed(() =>
  task.value?.can_manage_shifts ?? false)` replaces `canManageTask` on the
  add-shifts dropdown (`btn-add-shifts`), the phone menu's add-batch and
  add-shift items (the Edit item stays `canManageTask`), per-batch Edit/Delete,
  and the delete icon on each shift card. When `canManageTask &&
  !canManageShifts`, a one-line note `duties.tasks.managers.voucherShiftsLocked`
  under the info row.
- `views/tasks/TaskEditView.vue`: the schedule card (`section-schedule`) only
  when `task.can_manage_shifts`. In batch mode, `!can_manage_shifts` redirects
  to `task-detail`, as the existing `can_manage` guard does.
- `views/tasks/TaskAddShiftsView.vue`: the guard checks `can_manage_shifts`.

### Package 7: inviting people in charge

- `components/events/EventMemberPicker.vue`: new optional prop `allowEmail`
  (default false) and emit `invite: [email: string]`. When `allowEmail` and the
  trimmed search passes `looksLikeEmail` and equals no member's e-mail
  (case-insensitive), the list shows one extra item,
  `duties.tasks.managers.inviteOption`. Picking it emits `invite` and clears
  the field. Other users of the picker (teams, corrections, redeem) are
  unchanged.
- New `lib/email.ts` with `looksLikeEmail(text)` (one `@`, a dot in the domain,
  no spaces; the server validates properly) and
  `lib/__tests__/email.spec.ts` (90 % per-file coverage gate).
- `components/tasks/managers/TaskManagersEditor.vue`:
  - the picker gets `allow-email`, `label` `addOrInvite` and `placeholder`
    `searchPlaceholder`. `invite(email)` posts to `…/managers/invite`. Then for
    `added` it toasts `added`; for `invited`, `invited` (or `invitedNoMail` when
    `emailed` is false); with `registration_may_fail` it adds a
    `domainWarning` toast. Then it reloads the task and the pending list;
  - below the people in charge, an "Invited" list (`pendingTitle`, hint
    `pendingHint`) from `GET …/managers/invitations`: e-mail, "Valid until
    {date}" or "Expired", and "Already in the event now" when `is_member_now`.
    The row's ⋮ menu: "Add now" (`is_member_now`), "Send again" (valid), "Invite
    again" (expired), "Withdraw invitation" (`confirmDestructive`);
  - `dialogDescription` gets the second sentence `inviteHint` (separate key).
- `views/tasks/TaskCreateView.vue`: the people-in-charge picker gets
  `allow-email`. Invited addresses show as chips (`createInvitedChip`) and go
  out as `manager_emails`. After the create, toast the count of `invited`
  results (`duties.events.invitations.sent`) and list `skipped` ones
  (`createSkipped`).
- `views/events/InviteAcceptView.vue`: when `preview.tasks.length`, a block
  `invite.tasksTitle` with the task names and `invite.tasksHint`. After
  accepting with exactly one task, toast `invite.joinedInCharge` and open that
  task; otherwise as today.
- `components/events/EventInvitations.vue`: a pending row shows
  `invitations.forTasks` when `invitation.tasks.length`; the bulk result shows
  `skipped_rate_limited` with `invitations.skippedRateLimited`.
- `components/navigation/NotificationList.vue`: `data.token` first →
  `{ name: 'invite-accept', params: { token } }`. Add a unit spec for the
  navigation branches (`components/navigation/__tests__/NotificationList.spec.ts`).

## i18n

Both locales, same keys (`node ../scripts/pre-commit/check_locale_parity.js`).
German uses "du". Plurals are written with `\|` here and plain `|` in the JSON.

### Package 1

**`duties.json` → `duties.tasks.quickView.*`** (remove `availableShifts`)

| Key | en | de |
|---|---|---|
| `openShifts` | `No open shifts \| 1 open shift \| {count} open shifts` | `Keine freie Schicht \| 1 freie Schicht \| {count} freie Schichten` |
| `allTaken` | All shifts taken | Alle Schichten belegt |
| `noUpcoming` | No shifts coming up | Keine kommenden Schichten |
| `nextShiftOn` | Next shift: {date} | Nächste Schicht: {date} |
| `jumpTo` | Show | Anzeigen |

**`navigation.json`**: `sidebar.badges.inCharge` "You're in charge" / "Du bist
verantwortlich".

**`vouchers.json`** (remove `redeem.recentTotal`)

| Key | en | de |
|---|---|---|
| `redeem.recentToday` | `Today: {n} voucher \| Today: {n} vouchers` | `Heute: {n} Marke \| Heute: {n} Marken` |
| `redeem.rowAmount` | `{n} voucher \| {n} vouchers` | `{n} Marke \| {n} Marken` |

### Package 2

**Backend `logic/notifications/locales/{en,de}.json`**

| Key | en | de |
|---|---|---|
| `task.manager_added` title | You're in charge of a task | Du bist jetzt verantwortlich |
| `task.manager_added` body | {actor} put you in charge of “{task_name}” in “{event_name}”. You can now edit the task and its shifts and see who has booked. | {actor} hat dich bei „{task_name}“ in „{event_name}“ als verantwortlich eingetragen. Du kannst die Aufgabe und ihre Schichten jetzt bearbeiten und sehen, wer gebucht hat. |
| `task.manager_removed` title | No longer in charge | Nicht mehr verantwortlich |
| `task.manager_removed` body | {actor} took you off “{task_name}” in “{event_name}”. You can no longer edit it. | {actor} hat dich bei „{task_name}“ in „{event_name}“ als verantwortlich ausgetragen. Du kannst die Aufgabe nicht mehr bearbeiten. |

**`notifications.json` → `notifications.types.task.*`**

| Key | en | de |
|---|---|---|
| `manager_added.name` | Put in charge of a task | Als verantwortlich eingetragen |
| `manager_added.description` | When an organiser puts you in charge of a task | Wenn dich jemand für eine Aufgabe als verantwortlich einträgt |
| `manager_removed.name` | No longer in charge | Nicht mehr verantwortlich |
| `manager_removed.description` | When an organiser takes you off a task you were in charge of | Wenn dich jemand bei einer Aufgabe als verantwortlich austrägt |

### Package 3

**`vouchers.json`** (remove `admin.colBalance`, `admin.balanceNegative`,
`admin.belowZero`, `settings.retroHint`)

| Key | en | de |
|---|---|---|
| `admin.colAvailable` (unchanged) | Available | Verfügbar |
| `admin.colUpcoming` | Still to come | Kommen noch |
| `admin.colUpcomingHint` | Vouchers for booked shifts that aren't over yet. | Marken für gebuchte Schichten, die noch nicht vorbei sind. |
| `admin.takeAwayMax` | At most {n}: that's what {name} can still redeem. | Höchstens {n}, so viele kann {name} noch einlösen. |
| `settings.rateHint` | Applies to shifts that aren't over yet. Vouchers already earned stay. | Gilt für Schichten, die noch nicht vorbei sind. Schon verdiente Marken bleiben. |

**`errorCodes.json`**

| Key | en | de |
|---|---|---|
| `voucher.correction_exceeds_available` | That would take away more than they can still redeem. | Das wäre mehr, als noch eingelöst werden kann. |
| `voucher.correction_exceeds_available_with` | That would take away more than they can still redeem: {n} at most. | Das wäre mehr, als noch eingelöst werden kann: höchstens {n}. |

### Packages 4 and 5

**`vouchers.json`** (remove `settings.isDesk`, `settings.isDeskHint`,
`settings.deskNeedsTeam` in package 4)

| Key | en | de |
|---|---|---|
| `eventSettings.title` | Vouchers | Marken |
| `eventSettings.description` | Rules for every task in this event. | Regeln für alle Aufgaben dieser Veranstaltung. |
| `eventSettings.manualTitle` | Who can redeem without a code? | Wer kann ohne Code einlösen? |
| `eventSettings.manualHint` | For people whose phone isn't working: their name is picked from the member list instead of scanning a code. | Für Leute, deren Handy nicht geht: Statt einen Code zu scannen, wird der Name aus der Mitgliederliste ausgewählt. |
| `eventSettings.manualOnShift` | Also everyone who is on shift at a place that takes vouchers | Auch alle, die gerade an einer Einlösestelle Schicht haben |
| `eventSettings.manualOnShiftWarning` | Anyone who books a shift there can then use other people's vouchers. If that worries you, let only a team book those shifts, or choose the other option. | Wer dort eine Schicht bucht, kann dann auch die Marken anderer einlösen. Wenn dir das zu offen ist, lass diese Schichten nur von einem Team buchen oder wähl die andere Möglichkeit. |
| `eventSettings.manualInCharge` | Only organisers and the people in charge | Nur Organisator:innen und Verantwortliche |
| `eventSettings.shiftsTitle` | People in charge may change shifts on tasks with vouchers | Verantwortliche dürfen Schichten bei Aufgaben mit Marken ändern |
| `eventSettings.shiftsOff` | Off: only organisers add, move or delete shifts on tasks that earn vouchers. People in charge can still edit the task's details. | Aus: Bei Aufgaben mit Marken fügen nur Organisator:innen Schichten hinzu, verschieben oder löschen sie. Verantwortliche können die Angaben zur Aufgabe weiter bearbeiten. |
| `eventSettings.shiftsOn` | On: people in charge can add, move and delete shifts there too. Every extra shift earns vouchers, so check the overview now and then. | An: Verantwortliche können dort auch Schichten hinzufügen, verschieben und löschen. Jede zusätzliche Schicht bringt Marken, schau also ab und zu in die Übersicht. |
| `eventSettings.saved` | Voucher rules saved. | Marken-Regeln gespeichert. |
| `settings.managersLockedHint` | The people in charge of this task can then no longer add, move or delete its shifts. | Die Verantwortlichen dieser Aufgabe können ihre Schichten dann nicht mehr hinzufügen, verschieben oder löschen. |
| `redeem.askOrganisers` | No phone? Ask an organiser. | Kein Handy? Frag eine:n Organisator:in. |

The `on_shift` option is listed first, since it is the default.

**`duties.json`**: `duties.tasks.managers.voucherShiftsLocked` "This task earns
vouchers, so only organisers add, move or delete its shifts." / "Für diese
Aufgabe gibt es Marken. Schichten hinzufügen, verschieben oder löschen können
deshalb nur Organisator:innen."

**`errorCodes.json`**

| Key | en | de |
|---|---|---|
| `task.voucher_shifts_admin_only` | This task earns vouchers, so only organisers can add, move or delete its shifts. Ask an organiser, or ask them to allow it in the event settings. | Für diese Aufgabe gibt es Marken. Deshalb können nur Organisator:innen Schichten hinzufügen, verschieben oder löschen. Frag eine:n Organisator:in oder bitte darum, es in den Einstellungen der Veranstaltung zu erlauben. |
| `voucher.manual_not_allowed` (new text) | Only organisers and the people in charge can redeem without a code here. | Ohne Code einlösen können hier nur Organisator:innen und Verantwortliche. |

### Package 6

**Backend `locales/{en,de}.json`** (message keys; the type code stays
`event.invitation` / `event.invitation_accepted`)

| Key | en | de |
|---|---|---|
| `event.invitation.tasks` title | Invitation to be in charge | Einladung als Verantwortliche:r |
| `event.invitation.tasks` body | {inviter} invited you to “{event_name}” and would like you to be in charge of {tasks}. | {inviter} hat dich zu „{event_name}“ eingeladen und möchte, dass du für {tasks} verantwortlich bist. |
| `event.invitation_accepted.tasks` title | Invitation Accepted | Einladung angenommen |
| `event.invitation_accepted.tasks` body | {name} joined “{event_name}” and is now in charge of {tasks}. | {name} ist „{event_name}“ beigetreten und jetzt verantwortlich für {tasks}. |
| `invite.email` title | {inviter} invites you to “{event_name}” | {inviter} lädt dich zu „{event_name}“ ein |
| `invite.email` body | {inviter} invites you to take part in “{event_name}” ({dates}).⏎⏎To accept, create an account with this e-mail address, or sign in if you already have one. Then confirm the invitation.{expiry} | {inviter} lädt dich ein, bei „{event_name}“ ({dates}) mitzumachen.⏎⏎Um die Einladung anzunehmen, leg mit dieser E-Mail-Adresse ein Konto an oder melde dich an, falls du schon eins hast. Bestätige danach die Einladung.{expiry} |
| `invite.email.tasks` title | Invitation: in charge at “{event_name}” | Einladung: verantwortlich bei „{event_name}“ |
| `invite.email.tasks` body | {inviter} would like you to be in charge of {tasks} at “{event_name}” ({dates}). As the person in charge you can edit the task and its shifts and see who has booked.⏎⏎To accept, create an account with this e-mail address, or sign in if you already have one. Then confirm the invitation.{expiry} | {inviter} möchte, dass du bei „{event_name}“ ({dates}) für {tasks} verantwortlich bist. Als Verantwortliche:r kannst du die Aufgabe und ihre Schichten bearbeiten und sehen, wer gebucht hat.⏎⏎Um die Einladung anzunehmen, leg mit dieser E-Mail-Adresse ein Konto an oder melde dich an, falls du schon eins hast. Bestätige danach die Einladung.{expiry} |
| `invite.email.expiry` body | ␣The invitation is valid until {date}. | ␣Die Einladung gilt bis {date}. |
| `email.invite_cta` | View invitation | Einladung ansehen |
| `email.invite_footer` | You received this e-mail because {inviter} entered this address on {project_name}. If you don't know them, you can ignore it. | Du bekommst diese E-Mail, weil {inviter} diese Adresse bei {project_name} eingegeben hat. Wenn du die Person nicht kennst, kannst du die E-Mail ignorieren. |

`⏎⏎` is `\n\n` in the JSON and `␣` a leading space (the expiry sentence is
appended to the body). `{dates}` is `dd.mm.yyyy` or `dd.mm.yyyy – dd.mm.yyyy`
(the format `booking.confirmed` uses), `{tasks}` comes from `quoted_list`, and
`{inviter}` is the inviter's name or else their address. Package 2 adds a
backend test that both locale files have the same keys, including inside
`email` (nothing checks the backend files today, as `auth/emails.py::_chrome`
notes).

### Package 7

**`duties.json` → `duties.tasks.managers.*`**

| Key | en | de |
|---|---|---|
| `addOrInvite` | Add a person or invite by e-mail | Person hinzufügen oder per E-Mail einladen |
| `searchPlaceholder` | Name or e-mail address | Name oder E-Mail-Adresse |
| `inviteHint` | Not in the event yet? Enter their e-mail address. They get an invitation and are in charge once they accept. | Noch nicht in der Veranstaltung? Gib die E-Mail-Adresse ein. Die Person bekommt eine Einladung und ist verantwortlich, sobald sie annimmt. |
| `inviteOption` | Invite {email} by e-mail | {email} per E-Mail einladen |
| `invited` | Invitation sent to {email}. | Einladung an {email} gesendet. |
| `invitedNoMail` | {email} is invited. They'll see this task too when they open the invitation. | {email} ist eingeladen. Diese Aufgabe sehen sie mit, wenn sie die Einladung öffnen. |
| `domainWarning` | If they don't have an account yet, they can't create one with this address on this site. | Falls sie noch kein Konto haben, können sie mit dieser Adresse hier keins anlegen. |
| `pendingTitle` | Invited | Eingeladen |
| `pendingHint` | They are in charge once they accept the invitation. | Sie sind verantwortlich, sobald sie die Einladung annehmen. |
| `pendingExpires` | Valid until {date} | Gültig bis {date} |
| `pendingExpired` | Expired | Abgelaufen |
| `pendingIsMember` | Already in the event now | Ist inzwischen dabei |
| `addNow` | Add now | Jetzt hinzufügen |
| `resend` | Send again | Erneut senden |
| `resent` | Invitation sent again. | Einladung erneut gesendet. |
| `inviteAgain` | Invite again | Erneut einladen |
| `withdraw` | Withdraw invitation | Einladung zurückziehen |
| `withdrawConfirmTitle` | Withdraw the invitation for {email}? | Einladung für {email} zurückziehen? |
| `withdrawConfirmText` | They won't be put in charge of this task when they accept. | Wenn sie die Einladung annehmen, werden sie nicht für diese Aufgabe verantwortlich. |
| `withdrawn` | Invitation withdrawn. | Einladung zurückgezogen. |
| `invitationActions` | Actions for the invitation to {email} | Aktionen für die Einladung an {email} |
| `createInvitedChip` | {email} (invitation) | {email} (Einladung) |
| `createSkipped` | Not invited, try again later: {emails} | Nicht eingeladen, versuch es später noch einmal: {emails} |

**`duties.json` → `duties.events.*`**

| Key | en | de |
|---|---|---|
| `invite.tasksTitle` | You're asked to be in charge of | Du sollst verantwortlich sein für |
| `invite.tasksHint` | As the person in charge you can edit the task and its shifts and see who has booked. | Als Verantwortliche:r kannst du die Aufgabe und ihre Schichten bearbeiten und sehen, wer gebucht hat. |
| `invite.joinedInCharge` | Welcome to {name}. You're now in charge of {task}. | Willkommen bei {name}. Du bist jetzt verantwortlich für {task}. |
| `invitations.forTasks` | In charge of: {tasks} | Verantwortlich für: {tasks} |
| `invitations.skippedRateLimited` | Not sent, too many invitations today: {emails} | Nicht gesendet, heute schon zu viele Einladungen: {emails} |

**`errorCodes.json`**

| Key | en | de |
|---|---|---|
| `task.manager_already_invited` | That address is already invited to be in charge of this task. | Diese Adresse ist schon eingeladen, für diese Aufgabe verantwortlich zu sein. |
| `task.manager_invitation_not_found` | That invitation could not be found. It may have been accepted or withdrawn. | Diese Einladung wurde nicht gefunden. Vielleicht wurde sie schon angenommen oder zurückgezogen. |
| `invitation.rate_limited` | You have sent a lot of invitations today. Try again tomorrow. | Du hast heute schon sehr viele Einladungen verschickt. Versuch es morgen noch einmal. |
| `invitation.address_limited` | This address has already received several invitations today. Try again tomorrow. | An diese Adresse gingen heute schon mehrere Einladungen. Versuch es morgen noch einmal. |
| `invitation.resend_too_soon` | An e-mail went out a few minutes ago. Wait a little before sending it again. | Vor ein paar Minuten ging schon eine E-Mail raus. Warte etwas, bevor du sie noch einmal sendest. |
| `invitation.expired` | This invitation has expired. Send a new one. | Diese Einladung ist abgelaufen. Schick eine neue. |
| `invitation.revoked` | This invitation was withdrawn. | Diese Einladung wurde zurückgezogen. |
| `invitation.already_used` | This invitation has already been used. | Diese Einladung wurde schon benutzt. |
| `invitation.email_mismatch` | This invitation was sent to a different e-mail address. | Diese Einladung ging an eine andere E-Mail-Adresse. |
| `invitation.not_found` | This invitation link doesn't work. | Dieser Einladungslink funktioniert nicht. |
| `invitation.event_gone` | The event of this invitation no longer exists. | Die Veranstaltung dieser Einladung gibt es nicht mehr. |
| `event.already_member` | That person is already taking part in this event. | Diese Person ist schon bei dieser Veranstaltung dabei. |
| `event.already_invited` | That address already has an open invitation. | An diese Adresse ging schon eine Einladung, die noch offen ist. |
| `event.invitation_not_found` | That invitation could not be found. | Diese Einladung wurde nicht gefunden. |

## Tests

Run one pytest at a time (memory note on the pre-commit venv sync).
Time-dependent tests patch `app.logic.clock.wall_clock_now`.

### Package 1

| File | Cases |
|---|---|
| `tests/api/routes/test_tasks_feed.py` | A published task whose shifts still to come are all full: a member doesn't get it from `/tasks/feed` (list and cards); its person in charge and an event admin do. A task with no shift still to come and an end date in the past: nobody gets it. Its draft for its person in charge (existing). List view: a task whose only shift is 10 days out has `shifts == []`, `open_shifts == 1`, `next_shift_date` set; a full task has `open_shifts == 0` and `next_shift_date` set, `next_open_shift_date` None; a shift today that started an hour ago doesn't count (clock patched). Update any existing assertion that an organiser does not see a fully booked task |
| `tests/api/routes/test_dashboard.py::TestDashboardSidebar` | A full task the caller is in charge of is listed with `is_managed: true`, before other tasks; a managed draft is listed; a plain member doesn't get the full task; a stale row in an event the person left gives nothing |
| `tests/api/routes/test_vouchers.py` | Point entries: `today_amount`/`today_count` count today's redemptions (wall-clock day; an entry from 23:50 yesterday Berlin time is excluded), over more entries than `limit`; an on-shift redeemer gets their own totals. Replace the `total_amount` asserts (around lines 1373 and 1381) |
| `frontend/src/stores/__tests__/eventFilters.spec.ts` | `hideFullShifts` is not written to and not restored from storage |
| `frontend/src/components/tasks/quick-view/__tests__/TaskQuickViewCard.spec.ts` (new) | The three label cases; the next-shift hint and its jump request (`shift-window` with `start_date` = that date); no hint when the window has shifts |
| `frontend/e2e/tests/mobile/my-bookings.spec.ts` (new, mobile project) | At phone width the search field is at least 200 px wide |

### Package 2

| File | Cases |
|---|---|
| `tests/api/routes/test_task_manager_notifications.py` (new, recorder pattern from `test_team_notifications.py`) | Admin adds a member: one call with that user and the admin as actor. Admin adds themselves: none. Person steps down: none. Admin removes someone: one removed call. A refused add (non-member, 409): none. `with-shifts` with three `manager_ids` including the creator: one call with the other two. Clone with `copy_members`: none |
| `tests/logic/test_notification_triggers.py` | `dispatch_task_manager_added` writes a `task.manager_added` notification whose body names task and event, with `data.task_id`; leaves out the actor and inactive accounts; muting the event silences it. `dispatch_task_manager_removed` on a draft carries `event_id` and no `task_id` |
| `tests/logic/test_notification_locales.py` (new) | en and de have the same keys, top level and inside `email` |

### Package 3

| File | Cases |
|---|---|
| `tests/logic/test_vouchers.py` | **Rate:** replace `test_lowering_the_rate_after_spending_goes_negative` with `test_a_rate_change_leaves_ended_shifts_alone`: 2 → 0 keeps 2 for the ended shift and gives 0 for the one still to come; 0 → 3 gives 0 for the ended shift (zero row) and 3 for the one to come; a shift running during the change counts at the new rate. **Deleting and moving:** replace `test_deleting_a_past_shift_lowers_what_was_earned` with `…keeps_what_was_earned` (through the API); deleting the task, a batch, or regenerating away an ended shift keeps it, and the history shows the old task name and time from the snapshot; moving an ended shift into the future keeps it, and when it ends again it does not count twice; `POST /events/{id}/shift-dates` keeps it; moving the task to another event keeps it in the source event and moves the upcoming part; deleting the account that created the task keeps other volunteers' earnings. **Members:** a member who left keeps what ended shifts earned. **Idempotence:** `settle_earnings` twice writes one row per booking; tasks at 0 write nothing unless `include_zero`. **Reads:** a booking settled at 2 whose task is now at 5 counts 2; `upcoming` leaves settled bookings out. `VoucherShift.ends_at` from a snapshot is UTC like the rest |
| `tests/logic/test_voucher_concurrency.py` | Add case (4) on two committed sessions: redeeming the full balance while another session lowers the rate (and so settles): exactly one balance results, the redemption succeeds, `available` ends at 0, and there is one earning row per booking |
| `tests/api/routes/test_vouchers.py` | Corrections: taking away more than available → 409 `voucher.correction_exceeds_available` with `available`; exactly available → 201 and available 0; deleting a +5 correction after 5 were redeemed → 409; changing −1 to −10 beyond available → 409. `people` and `people/{id}` carry no `balance`. Rewrite the negative-balance assert (around line 1174) as "the balance stays" |
| `tests/api/routes/test_event_members.py::TestUserDeletionCascades` | Deleting a volunteer removes their earnings; deleting the event owner cascades the event's earnings; no FK errors |
| `tests/logic/test_sandbox_cleanup.py` | Inventory and `_remaining` include `voucher_earnings` (with a helper so the census isn't vacuously zero) |
| `frontend/src/lib/__tests__/api-errors.spec.ts` | `voucher.correction_exceeds_available` with `available` |

### Package 4

| File | Cases |
|---|---|
| `tests/api/routes/test_vouchers.py` | Replace the desk fixture (around line 160) and the desk tables (around 966 and 1308–1333): by default (`on_shift`) an on-shift redeemer at any point redeems by `user_id` (no team needed); with `in_charge` they get `403 voucher.manual_not_allowed` while admin and person in charge get 201; a member not on shift there gets `403 voucher.not_allowed` either way; `points` `can_redeem_manually` per role and setting; `is_desk` gone. Delete the `is_voucher_desk` PATCH tests (around 1514–1601) |
| `tests/api/routes/test_events.py` | A new event reads `voucher_manual_redeem: "on_shift"` and `managers_edit_voucher_shifts: false`; PATCH by admin 200 and `EventRead` reflects it; member 403; `"desk"` → 422; explicit `null` leaves the value |
| `tests/api/routes/test_voucher_shift_lock.py` (new) | Parametrised over the six writes (`POST /shifts/`, `PATCH /shifts/{id}` with `start_time`, with `max_bookings`, `DELETE /shifts/{id}`, `add-shifts`, `regenerate-shifts` dry run and real, `DELETE` batch): person in charge on a task with 2 per shift, setting off → `403 task.voucher_shifts_admin_only` and nothing changed; setting on → allowed; task with 0 → allowed; admin → allowed either way. `PATCH /shifts/{id}` with only `title`/`location` while locked → 200; with `max_bookings` sent unchanged → 200. `PATCH /tasks/{id}` details while locked → 200. Raising `vouchers_per_shift` from 0 flips `can_manage_shifts` and leaves the shifts as they were |
| `tests/logic/test_task_access.py` | `voucher_shifts_locked`: admin never; manager on 0 never; manager on 2 with the setting off yes, on no; event None (orphan task) yes for a manager |
| `tests/api/routes/test_task_managers.py` | `can_manage_shifts` on get, list, feed and the PATCH response, for admin / person in charge / member |
| `tests/api/routes/test_event_clone.py` | Both settings are copied; remove the `is_voucher_desk` asserts (around 1154, 1186) |
| `tests/logic/test_sandbox_seed.py` | Remove the desk assertion (around 1657); the seeded event has `on_shift` and `false`; the redemption is still at the Café counter |

### Package 5

- `e2e/tests/multi-user/task-managers.spec.ts`: a person in charge of a task
  with vouchers sees no add-shifts button and the locked note; the organiser
  turns on the event setting in event settings → after reload the person sees
  the button. Check that the existing cases use a task with 0 vouchers
  (API-created tasks default to 0).
- `e2e/tests/multi-user/vouchers.spec.ts`: still green (it never touched the
  desk switch). Run `pnpm generate-e2e-coverage`.

### Package 6

| File | Cases |
|---|---|
| `tests/api/routes/test_task_manager_invitations.py` (new) | **Invite:** a member's address (any case) → 201 `added`, row exists, `dispatch_task_manager_added` queued; the caller's own address → `added`, nothing queued; an account that isn't a member and an unknown address both → 201 `invited` with identical response shape, `dispatch_event_invitation` queued, `for_tasks_only` true, `last_sent_at` set; already in charge → 409 `task.manager_already`; same address and task again → 409 `task.manager_already_invited`; same address for a second task within 10 min → linked to the same invitation, `emailed: false`; after 10 min (clock) → `emailed: true`, expiry pushed out; an open plain invitation → link added, `for_tasks_only` stays false; an expired one → new invitation, old revoked, old links moved; member / person in charge / outsider → 403 `event.forbidden`; demo event → 403 `sandbox.invitations_disabled`. **Quotas** (switch the TESTING bypass off): a 4th invitation to one address within 24 h across events → 429 `invitation.address_limited`; inviter cap (patch the constant to 2) → 429 `invitation.rate_limited`; superadmin exempt; bulk returns `skipped_rate_limited`. **Domain:** with `allowed_domains=["example.org"]` and bypass off, `registration_may_fail` true for `x@other.com` whether or not an account exists; false with bypass on. **List:** admin 200 with `expired` and `is_member_now`; person in charge and member 403. **Withdraw:** removes the link; a task-only invitation with no links left is revoked; a plain one stays; unknown id → 404 `task.manager_invitation_not_found`. **Resend:** within 10 min → 429 `invitation.resend_too_soon`; expired → 409 `invitation.expired`. **Accept:** the addressee accepts → member, in charge of every linked task of every open targeted invitation to that address in the event, all marked accepted; already a member → links applied and invitation marked accepted; a linked task deleted first → task-only invitation revoked, accept → 410 `invitation.revoked`; a linked task moved to another event → no row for it; already in charge of one linked task → no error. **Preview:** `tasks` for the addressee, empty on `email_mismatch`. `GET /events/{id}/invitations` carries `tasks`. **Create:** `with-shifts` with `manager_emails` mixing a member and a stranger → one row, one invitation, `manager_invites` reports both; a demo event → `skipped` / `sandbox`, task still created |
| `tests/logic/test_notification_triggers.py` | `dispatch_event_invitation`: no account → `send_event_invitation_email` called (monkeypatched) with the inviter's language, the task names and the token; account → `event.invitation` notification with `data.token` and the tasks text; a plain invitation to an address without an account → the plain mail |
| `tests/logic/test_invitation_emails.py` (new) | The mail escapes an inviter name and event name containing `<b>`; the button and the fallback link are `/invite/{token}`; German and English; no expiry sentence without `expires_at`; no SMTP → returns False and logs the link |
| `tests/logic/test_notification_channels.py` | `_build_html` with `{"event_id", "token"}` links to `/invite/{token}` |
| `tests/api/routes/test_event_members.py::TestUserDeletionCascades` | Deleting the event owner who invited an address to be in charge of a task: no FK error, the invitation and link are gone |
| `tests/api/routes/test_registration_modes.py` | `invite` mode: an address with an open task-only invitation can register |
| `tests/logic/test_sandbox_cleanup.py` | Inventory and `_remaining` include `event_invitation_tasks`; table count 29 |

### Package 7

- `lib/__tests__/email.spec.ts`: `looksLikeEmail` accepts and rejects.
- `components/events/__tests__/EventMemberPicker.spec.ts` (new): with
  `allowEmail`, a typed unknown address shows the invite item and emits
  `invite`; a member's address shows the member, not the invite item; without
  `allowEmail` no invite item.
- `components/navigation/__tests__/NotificationList.spec.ts` (new): `token` →
  `invite-accept`; `task_id`, team, event and booking branches as today.
- `e2e/tests/multi-user/task-managers.spec.ts`: the organiser enters a
  disposable user's address (`joinWorkerEvent: false`) in the dialog → an
  "Invited" row; the test reads the token from `GET /events/{id}/invitations`
  as the organiser; the invitee opens `/invite/{token}`, sees the task name,
  accepts, lands on the task with "You're in charge". The organiser withdraws a
  second invitation and the row goes. Navigate in-app, not by reload (CI
  cookie note). `pnpm generate-e2e-coverage`.
- The whole local gate in `frontend/CLAUDE.md` before pushing.

## Docs to update

- `CLAUDE.md`, "Auth Pattern":
  - the vouchers paragraph: earned vouchers are derived until something would
    change them, then frozen in `voucher_earnings` by
    `vouchers.settle_earnings` (rate changes, shift and task deletes and moves,
    shift dates, user deletion); a balance never goes below zero; corrections
    are capped. The desk sentence is replaced by `events.voucher_manual_redeem`
    (default `on_shift`);
  - people in charge get the voucher-shift gate (`require_shift_editor`,
    `403 task.voucher_shifts_admin_only`, event setting
    `managers_edit_voucher_shifts`);
  - invitations: a targeted invitation can carry tasks
    (`event_invitation_tasks`), applied on acceptance; invitation mails now
    reach addresses without an account, with daily limits.
- `docs/AUTH.md`, "Who may register": task invitations count like any
  targeted invitation; addresses without an account now get the invitation by
  e-mail; the limits.
- `docs/SANDBOX.md`: order diagram (steps 3 and 4), seed paragraph.
- `backend/app/api/routes/README.md`: gate list.
- `app/logic/permissions.py` module docstring;
  `triggers.py::dispatch_event_invitation` docstring;
  `work_hours.counts_as_worked` docstring (settle first, #177);
  `logic/vouchers.py` and `models/voucher.py` module docstrings ("earned is
  never stored" is no longer true).
- `docs/plans/2026-10-30-task-managers-and-vouchers.md`: one line each at
  "Balances can go negative", the `is_voucher_desk` passages and "Open
  question", pointing here.
- The changelog entry written when the branch is released describes the
  defaults: earned vouchers stay earned; people in charge get a notification
  and can be invited by e-mail; whoever is on shift at a place that takes
  vouchers can redeem without a code unless the event says otherwise; only
  organisers change shifts on voucher tasks unless the event allows it.

## Not done

- Freezing worked hours the way vouchers are frozen (open question).
- Attendance (#177) itself. It must call `settle_earnings` before it changes
  whether an ended booking counts (Decision G).
- Applying a pending task invitation when the person joins some other way
  (share link, join request). The dialog offers "Add now" instead (Decision B
  says why).
- A personal message in the invitation mail.
- A per-person daily cap on vouchers earned (still in the original plan's list).
- Notifying people in charge when their task is deleted or moved.
- Bulk "put this person in charge of several tasks" with one combined
  notification.
- Showing fully booked tasks to plain members in the default list.
- People in charge per location, help alerts, CSV export and the rest of the
  original plan's "Not done".

## Implementation order

Seven packages, built and reviewed one after another. Each ends green on its own
checks. Each package that changes the OpenAPI schema ends with `just
generate-client` and commits `frontend/src/client` together with its last
backend change (`frontend/CLAUDE.md`, "Generated files are committed and
diffed"). A backend package that removes or renames a field the frontend reads
also makes the matching frontend edit in the same package, so the frontend
type-check never goes red between packages (packages 3 and 4 do this).

Dependencies: 1, 2 and 3 are independent of each other. 4 comes after 3 (the
migration chain, and both touch `PATCH /tasks` and the task voucher fields). 5
needs 4. 6 needs 2 (the member path queues `dispatch_task_manager_added`) and 4
(the migration chain). 7 needs 6.

### Package 1: fixes (backend + frontend)

1. `crud/shift.upcoming_condition`, used by the feed, the sidebar and
   `crud/task`; feed on `clock.wall_clock_now()`.
2. Open-shift exemption for manageable tasks in `crud/task` and `task_feed`.
3. `FeedTaskItem.open_shifts` / `next_shift_date` / `next_open_shift_date` and
   `_upcoming_stats`.
4. `SidebarTask.is_managed` and `_sidebar_tasks`.
5. `PointRedemptionList.today_*` and `crud_voucher.point_totals_since`.
6. Backend tests; `just generate-client`.
7. Frontend: quick-view card label and next-shift hint, filter store, sidebar
   marker, My Bookings search row, redeem header and row amounts; i18n; specs;
   mobile E2E; local gate.

### Package 2: notifications for people in charge (backend + i18n)

1. Registry types, backend locale texts, `quoted_list`, the locale parity test.
2. `dispatch_task_manager_added` / `_removed`.
3. Queue them from `tasks/managers.py` and `create_task_with_shifts`.
4. Tests.
5. Frontend `notifications.json` keys (no client change).

### Package 3: earned vouchers are final (backend + frontend)

1. `VoucherEarning` model, migration `20261102_0001` (down_revision
   `"20261030_0002"`), registered. Round trip, `just check-migrations`.
2. `settle_earnings` and the one-statement union in `_voucher_shifts`;
   `VoucherBalance` without `balance`; optional ids and `settled` on
   `VoucherShift`.
3. The nine call sites in Decision G's table.
4. Correction caps and `voucher.correction_exceeds_available`.
5. Sandbox purge step 4, SANDBOX.md, CLAUDE.md, the docstrings.
6. Tests, including the concurrency case; `just generate-client`.
7. Frontend: `EventVouchers` (one available column, "Kommen noch", no negative
   display), `VoucherAdjustmentDialog` cap, `VoucherHistory` null ids,
   `rateHint`, `api-errors`; i18n; local gate.

### Package 4: event voucher settings (backend + forced frontend edits)

1. Migration `20261102_0002`: the two `events` columns (`voucher_manual_redeem`
   default `on_shift`), drop `tasks.is_voucher_desk`. Round trip.
2. `Event` model, `EventUpdate` / `EventRead`, null handling in `update_event`,
   clone copy.
3. Remove `is_voucher_desk` everywhere (schemas, admin-only list, PATCH forcing,
   with-shifts, `_clone_task`, seed).
4. `may_redeem_manually(kind, event)`, `require_voucher_redeemer(..., event=)`,
   `VoucherPointRead` without `is_desk`.
5. `voucher_shifts_locked`, `require_shift_editor`, the six call sites,
   `PATCH /shifts/{id}` field check.
6. `TaskRead.can_manage_shifts` in `mark_task_access`.
7. Docstrings, CLAUDE.md, routes README, SANDBOX.md.
8. Tests; `just generate-client`.
9. Frontend: remove the desk switch and `is_voucher_desk` from the voucher
   fields, dialog and create form; delete the desk i18n keys; local gate.

### Package 5: event voucher settings (frontend)

1. `EventVoucherSettings.vue` in the Details tab.
2. The locked hint in the task voucher dialog.
3. Redeem view hint (`askOrganisers`).
4. `can_manage_shifts` in TaskDetailView, TaskEditView, TaskAddShiftsView.
5. i18n, E2E, local gate.

### Package 6: inviting people in charge (backend)

1. Migration `20261102_0003` (`event_invitation_tasks`, `for_tasks_only`,
   `last_sent_at`), model registered. Round trip.
2. `crud/event_invitation_task.py`; `_refuse_if_sandbox` moved to a shared
   module.
3. `logic/invitations.py` (quotas, re-send rule, `invite_to_task`).
4. `logic/invitation_emails.py` and the `send_action_mail` factoring in
   `auth/emails.py`; backend locale texts.
5. `dispatch_event_invitation` rework (plain invitations included),
   `_build_html` token link, `dispatch_event_invitation_accepted(task_ids=)`.
6. The four task routes; `manager_emails` on with-shifts.
7. Existing invitation routes: quotas, `last_sent_at`, `tasks` on read and
   preview, accept steps; `detach_task` on task delete and move.
8. Sandbox purge step 3, SANDBOX.md, AUTH.md, CLAUDE.md.
9. Tests; `just generate-client`.

### Package 7: inviting people in charge (frontend)

1. `lib/email.ts` with spec; `EventMemberPicker` `allowEmail` with spec.
2. `TaskManagersEditor`: invite, pending list and its actions.
3. `TaskCreateView` e-mail chips and results.
4. `InviteAcceptView` tasks block and landing; `EventInvitations` task names
   and skipped list; `NotificationList` token branch with spec.
5. i18n (`duties`, `errorCodes`), E2E, local gate.

## Decided after review

The product owner answered the first draft's open questions:

1. **Plain event invitations to addresses without an account get the new
   mail** (Decision B).
2. **The desk removal is a new migration**, not folded into `20261030_0002`
   (package 4).
3. **Plain members keep not seeing fully booked tasks** in the default task
   list; organisers and people in charge always see theirs (F2).
4. **A task invitation stays valid when its inviter stops being an organiser**
   (Decision B, edge cases).
5. **The removal notice goes in-app and by push only**, e-mail off by default
   (Decision A).
6. **The invitation limits stay as proposed:** 200 per organiser per day, 3 per
   address per day, one re-send per 10 minutes, superadmins exempt (Decision B).
7. **The column question is gone:** balances can't go negative (Decision G), so
   the overview keeps one "Verfügbar" column (Decision E).

Further answers worked in:
- **Earned vouchers are final** (Decision G, a new package 3).
- **`on_shift` is the default** for who may redeem without a code, for new
  events and in the migration (Decision C).
- **The task's voucher dialog does not mention the event-wide redeem rule**
  (Decision C, package 4).

## Open question

**Should worked hours become final the same way?** Today, and after this plan,
deleting a worked shift or moving it into the future removes its hours while
its vouchers stay. *Recommendation: no.* Hours are a record organisers keep
correcting, with work logs for what the shifts don't show, and nothing has been
handed out against them. If they should freeze too, the same settlement can
store the minutes next to the amount.
