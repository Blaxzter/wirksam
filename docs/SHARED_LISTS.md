# Shared lists

A shared list is a public link, `/l/<code>`, that offers shifts of one or more
tasks of one event to people without an account. They pick a shift, type their
name, and an email address and phone number if the list asks for them, and are
booked. Event admins and people in charge create and manage lists. Nobody who
signs up through one gets an account. The German UI says "Geteilte Listen".

The code:

- `app/models/shared_list.py`: the tables;
- `app/logic/shared_lists/`: one module per job, listed in its `__init__.py`;
- the gates in `app/logic/permissions.py`;
- three routers:

| Router | Tag | For |
|---|---|---|
| `app/api/routes/shared_lists.py` | `shared-lists` | organisers: the tables, the wizard's choices, the list a printed notice reuses, create, edit, pause, resume, end, rotate |
| `app/api/routes/shared_list_guests.py` | `shared-list-guests` | organisers: who signed up, removing sign-ups, the preview. The operator: `/list-guests` |
| `app/api/routes/public_shared_lists.py` | `public-shared-lists` | anyone: the public page, signing up, the guest's manage link |

Design notes: [`plans/2026-11-10-shared-lists.md`](plans/2026-11-10-shared-lists.md),
amended by [`plans/2026-11-12-shared-lists-guest-vouchers.md`](plans/2026-11-12-shared-lists-guest-vouchers.md)
(guests earn vouchers, and one guest account per confirmed address). The first
plan's "Decisions taken before implementation" defer claiming, so there is no
way to move a guest's sign-ups into a real account: everyone who signs up
through a list stays a guest. Where the plans and the code disagree, the code
is right.

## The model

| Table | Holds |
|---|---|
| `shared_lists` | One link: `event_id` (CASCADE), `code`, `title`, `intro`, `share_note` (organisers only), the stored `status`, how it closes (`ends_mode`, `ends_on`), what the form asks (`ask_email`, `ask_phone`), `show_names`, `max_per_person` (NULL is unlimited), `view_count`, and `created_by_id` / `created_by_name` (a snapshot, no foreign key) |
| `shared_list_tasks` | The tasks on a list, with `position`, their order in the share message |
| `shared_list_excluded_shifts` | Shifts of those tasks the list leaves out |
| `shared_list_guests` | The contact side of one guest user: the address, the list's event, the list the chain started on, `manage_nonce`, `last_signup_at`, `erased_at`, and `confirmed_at` for a [guest account](#guest-accounts) |
| `shared_list_guest_aliases` | A chain merged into a guest account: its former user id (no foreign key, that user is gone) and nonce, and the account's user (CASCADE), so its old mail links still open the account |
| `guest_activity_log` | Append-only, one row per guest sign-up and per guest mail. The daily ceilings count it |
| `guest_mail_suppressions` | Addresses that said "Das war ich nicht" |

Plus columns on existing tables: `users.is_list_guest`,
`events.managers_share_lists`, and on `bookings` the list it came through
(`shared_list_id`) and [the sign-up's person](#a-sign-ups-person)
(`show_first_name`, `guest_name`, `guest_phone`). All of it comes in migration
`20261110_0001`. Its downgrade drops what later versions of the file added with
`IF EXISTS`, so a dev database that ran an earlier version goes down and up
again with `alembic downgrade 20261104_0004` and `just migrate`.

### A guest is a `users` row

`crud.shared_list_guest.create` makes every new guest a user with exactly these
values:

- `subject = "listguest|<uuid4 hex>"` (`GUEST_SUBJECT_PREFIX`) and
  `is_list_guest = true`;
- `email = NULL` and `password_hash = NULL`;
- the name, phone number and `preferred_language` from the form;
- `default_reminder_offsets = []`, every `notify_*` off, `roles = []`,
  approved and active.

A user row, and not a nullable `bookings.user_id` or a sign-up table of its own,
because then capacity, `uq_booking_shift_user`, the overlap check
(`find_conflicting_booking`), reminders and their `reschedule`, rosters, print
views and reporting work on guest bookings unchanged. With no address in
`users.email` and no password, a guest never meets login, password reset,
`sync_superadmin_role`, the `auth.email_taken` check or an invitation lookup.
The address lives in `shared_list_guests.email`, normalised, and never in
`users.email`.

A guest is never an event member, so `GET /events/{id}/members`, the publish
fan-out and the team pickers never see one.

### One guest per sign-up chain

A chain is everything signed up from one visit to one list. The first sign-up
creates the guest user. "Noch eine Schicht eintragen" sends the `guest_token`
from the first answer and adds to the same user. A chain never leaves the list
it started on (`shared_list_guests.shared_list_id`): another list's token is
`403 shared_list.guest_token_invalid`.

A guest is **never** found by a typed address, because anyone can type anyone's.
So one person who signs up on two visits is two guests, even with the same
address, until they confirm the address from their mail: then the chains
become one [guest account](#guest-accounts). Lookups and locks identify a guest
by its guest user id.

### Attribution and missing foreign keys

`bookings.shared_list_id` names the list a booking was signed up through. It has
an index and no foreign key. A SET NULL beside `user_id` CASCADE is the trap in
[`backend/app/models/CLAUDE.md`](../backend/app/models/CLAUDE.md), and a list
only ever goes together with its event, so a dangling id joins nothing.
`shared_list_guests.shared_list_id` and `shared_lists.created_by_id` have no
foreign key either, and `guest_activity_log` and `guest_mail_suppressions` have
none at all (see [the ceilings](#the-daily-ceilings)).

No ORM relationship points at these tables from `Event`, `Task` or `Shift`.
Those are deleted through the ORM, and a relationship without
`passive_deletes` would load the rows first. Every CASCADE lives in the
database.

### What a list offers

A list stores tasks and excluded shifts, never days. `logic/shared_lists/offer.py`
works out the rest on every read:

- A shift is **included** when its task is on the list, still in the list's
  event, published, and has no `team_id`, and the shift is not excluded.
- It is **offered** when, in addition, it has not started:
  `offer.starts_at(date, start_time) > now`, on the event's wall clock. An
  untimed shift starts at 00:00, the same rule `booking.shift_started` uses.
  Guests never take a running shift, whatever the task.

A shift added later to a listed task is offered without anyone editing the
list. Regenerated shifts get new ids, so they come in included, and the
exclusion rows of deleted shifts cascade away. The public page and the sign-up
read shifts only through `offer.list_shifts`. A team-gated task is never
offered: a guest can never be an approved team member.

## Status and closing

`shared_lists.status` stores `live`, `paused` or `ended`, and `ended` is final.
"Expired" is never stored. `offer.effective_status` derives it on every read, so
moving shifts, changing the event's zone or `POST /events/{id}/shift-dates` can
never leave it stale. A `live` list is expired when:

- its event is not published (any more);
- `ends_mode = "date"` and the event's wall-clock date is past `ends_on`, which
  counts inclusively;
- `ends_mode = "last_shift"` (the default) and its last included shift
  (`offer.last_start`, started or not) has started, or there is none.

A list with `ends_mode = "manual"` stays live even with nothing left to offer.
`POST /events/{id}/shift-dates` moves `ends_on` along with the shifts
(`crud_shared_list.shift_ends_on`). A zone change needs nothing.

The transitions are `manage.change_status` and `manage.transition`, each under
the list's row lock:

| Action | Does | Refusals |
|---|---|---|
| pause | live becomes `paused` | Paused already: no change. Expired: `409 shared_list.not_live`. Ended: `409 shared_list.ended` |
| resume | paused or expired becomes `live`. A list whose `ends_on` is over switches to `last_shift` | Live already: no change. Ended: `409 shared_list.ended`. Event not published: `409 shared_list.event_not_published`. Still nothing to offer: `409 shared_list.nothing_to_offer` |
| end | anything becomes `ended` | Ended already: no change |
| rotate | a new `code` and `rotated_at`. The old link answers 404 | Ended: `409 shared_list.ended` |
| edit (`PATCH`) | the fields sent; the code stays | Ended: `409 shared_list.ended` |

None of them touches a booking. Whoever signed up stays signed up.

**Creating and editing** check the selection in `manage.validate_selection`, in
this order:

1. the event is published, else `409 shared_list.event_not_published`;
2. every task is in the event, published and not team-locked, else `422
   shared_list.task_not_in_event`, `shared_list.task_not_published` or
   `shared_list.task_team_locked`, each naming the tasks in `task_ids`;
3. at least one shift is offered (`422 shared_list.no_shifts`) and one of them
   has a free place (`422 shared_list.no_free_places`);
4. with `ends_mode = "date"`, `ends_on` lies between today and the date of the
   last offered shift, else `422 shared_list.ends_on_invalid` with
   `last_shift_date`.

Excluded ids of other shifts are dropped without a word. Create also caps an
event at `SHARED_LISTS_PER_EVENT` lists, ended ones included (`409
shared_list.too_many` with `max`): every management view evaluates all of them.
An edit is checked again only when it changes the tasks, the exclusions or the
closing. A private event can have lists: the link is the permission, as an
invitation link is.

**The code** comes from `crud.shared_list.generate_code`: twelve characters from
`CODE_ALPHABET` (55 symbols, no i, l, o, I, O, 0 or 1, and no "."), about 69
bits, drawn with `secrets.choice` and retried up to five times on a collision.
It is stored in plain text, like `event_invitations.token`, because organisers
copy the link again later, and the link is public by design.

## Who may do what

Event admins, the owner and the superadmin manage every list of their event. A
person in charge of tasks ([`PEOPLE_IN_CHARGE.md`](PEOPLE_IN_CHARGE.md#shared-lists))
may share their own tasks, manages a list whose **current** tasks are all
theirs, and sees, read-only, a list that holds some of them. "Current" means the
linked tasks still in the list's event, asked afresh on every call, because
being in charge ends when someone leaves, is removed, or the task moves. A list
with no current task is the admins' alone. A member in charge of nothing gets
403 from the event's list pages, and 404 for any one list.

The gates are in `app/logic/permissions.py`. Grepping for them finds every
check, so do not inline an equivalent condition.

| Gate | Used for | Refusal |
|---|---|---|
| `shared_list_scope` | The event-wide views (lists, overview, tasks, candidates) and bulk; the first check of pause-all | `404 event.not_found` without a role; `403 shared_list.forbidden` for a member in charge of nothing |
| `shared_list_access` | `"admin"`, `"manager"`, `"viewer"` or None for one list | |
| `require_shared_list_visible` | Reading one list, its sign-ups and its preview; removing sign-ups | `404 shared_list.not_found` |
| `require_shared_list_manager` | Editing, pausing, resuming, ending and rotating one list | `403 shared_list.forbidden` for a viewer; `403 shared_list.managers_disabled` |
| `require_shared_list_tasks` | Putting tasks on a list (create, and `PATCH` with `task_ids`) and reading their shifts (`candidate-shifts`) | `403 shared_list.managers_disabled`; `403 shared_list.tasks_forbidden`, naming the other tasks in `task_ids` |

`SharedListScope.access_to` is the rule of `shared_list_access` applied to a
snapshot, so a table of many lists needs no query per list.
`shared_list_change_refusal` is the rule of `require_shared_list_manager` as a
return value: `manage.bulk` asks it list by list and reports a refusal in
`skipped` with the code the single action would have answered.

Each gate tests for a sandbox event the caller did not create **before** the
role, because `get_event_role` reports the superadmin as owner of every event
(see [`SANDBOX.md`](SANDBOX.md#invisibility)).

`SharedListScope.managed_task_ids` is the set of the event's tasks the caller is
in charge of. Filter on it with an explicit branch on `is_admin`, never on
whether the set is empty. For a person in charge an empty set means "nothing",
and reading it as "unrestricted" would hand them every list of the event.

**`events.managers_share_lists`** is on by default. Event admins set it through
`PATCH /events/{id}`, and cloning an event copies it. While it is off, a person
in charge who is not an event admin may only pause and end their lists. Create,
edit, resume and rotate are `403 shared_list.managers_disabled`. They still read
their lists and sign-ups.

**The emergency stop.** `POST /events/{id}/shared-lists/pause-all` is for event
admins. It pauses every list whose stored status is `live`, expired ones
included, because a shift added later or the event published again would
otherwise reopen them. With `lock_managers: true` it also switches
`managers_share_lists` off, so nobody in charge can resume their own list
afterwards.

**Sign-ups.** An event admin sees every sign-up through a list. A person in
charge sees those on their own tasks, and how many others there are
(`hidden_count`). Only event admins may erase guests while removing sign-ups
(`can_erase`).

**Navigation.** `EventRead.managed_task_count`, filled in `decorate_events`
through `crud_task_manager.count_by_event_for_user`, tells the client whether
the caller is in charge of anything. `canUseSharedLists` in
`frontend/src/lib/shared-lists.ts` shows the pages to event admins and people
in charge, in a demo too ([In a demo](#in-a-demo)), and only while the switch
is on.

**A list's page.** `/app/shared-lists/:eventId/:listId`
(`SharedListDetailView.vue`) shows one list: its link and settings beside who
signed up through it and what it offers, with its actions under the heading.
The overview's `?list=<id>`, where the details used to open as a dialog,
redirects there, keeping the sign-ups table's `signups_` keys.

## Signing up

`POST /public/shared-lists/{code}/signups`. Before a row is read, the route
checks the kill switch, the rate limits `shared_list_signup_limiter` (keyed
`<ip>|<code>`) and `shared_list_signup_ip_limiter` (keyed by IP), and Turnstile
when `TURNSTILE_SECRET_KEY` is set (`verify_turnstile(...,
expected_action="shared-list-signup")`, `403 auth.captcha_failed`). Then
`signup.sign_up` refuses, in this order:

1. an unknown code: `404 shared_list.not_found`;
2. a paused list: `409 shared_list.paused`. An expired or ended one: `409
   shared_list.closed`;
3. an address or phone number the list requires and the body lacks: `422
   shared_list.email_required` or `422 shared_list.phone_required`. A field the
   list does not ask for (`off`) is dropped;
4. a shift the list does not include: `404 shared_list.shift_not_offered`. One
   that has started: `409 shared_list.shift_started`;
5. a `guest_token` that is not a live chain of this list: `403
   shared_list.guest_token_invalid`. A chain's stored address wins over the
   body. A token its chain's confirmation retired, or one of a guest account,
   starts a new chain from the typed fields instead (`signup._chain`), so
   "Noch eine Schicht eintragen" keeps working in a tab whose chain was
   confirmed meanwhile, and a sign-up never continues an account;
6. the daily ceilings of the address and of the list: `429
   shared_list.too_many_for_address`, `429 shared_list.daily_limit`;
7. the list's `max_per_person`: `409 shared_list.max_per_person` with `max`. It
   counts the confirmed bookings through this list by address, or by chain when
   there is no address; a new chain without an address holds none yet;
8. under the shift's capacity lock: the same address already confirmed on the
   shift, through any list and any chain, or this chain already confirmed there:
   `409 shared_list.already_signed_up`. An overlap with the chain's other
   shifts: `409 booking.time_conflict`. A full shift: `409 booking.slot_full`.

Then it writes:

- for a new chain, the guest user and its contact row;
- the booking, or the chain's cancelled booking on that shift, reactivated,
  with this sign-up's person: `show_first_name` true only when the body's
  `show_names` (what the form showed) and the list's both say `first`, and
  `guest_name` and `guest_phone` from the chain's user;
- the reminder, through `crud_reminder.replace_for_booking`: `GUEST_REMINDER`
  (by mail, 1440 minutes before) when `remind` is set and there is an address,
  otherwise none;
- the `signup` row in `guest_activity_log`;
- for the first sign-up of a chain with an address, the confirmation's
  reservation, with `GUEST_DATA_RETENTION_DAYS` and whether a phone is stored.
  The route sends the mail as a background task after the commit.

No member notice is sent, and nobody else is told.

The answer is a `PublicSignupResult`: the booking, the shift as the public page
shows it, `guest_token` (the manage token, see below), `mail_queued`,
`show_manage_link` and `remaining` (None for no limit). `show_manage_link` is
set on the first sign-up of a chain that got no mail. The page must then show
the manage link, which is the guest's only way back.

**Duplicates.** An address is compared with other guests' addresses only, never
with a member's `users.email`: that would tell a stranger whether account X
booked shift S. Without an address two chains cannot be told apart, so the
organisers' table marks `possible_duplicate` when another confirmed guest with
the same name (ignoring case) is on the same shift.

**Normalising.** What a guest types goes through
`logic/shared_lists/normalize.py` (`normalize_name`, `normalize_email`,
`normalize_phone`, `first_name`), which `PublicSignupRequest` runs as pydantic
validators. Anything that stores or compares guest data must use these
functions.

**Capacity.** `booking_capacity.lock_shifts` is a transaction-scoped advisory
lock per shift (`shift-capacity:{id}`). The guest sign-up and the member
`create_booking` both take it before they count, so a member and a guest cannot
both take the last place. It is not `FOR UPDATE` on the shift, which would also
block the `FOR KEY SHARE` every booking insert takes for its foreign key.

## Locks

Every path takes its locks in this order, so no two requests wait for each other
in a circle. Three rules hold throughout:

- guest rows are locked before advisory locks, with one exception,
  `guest-account:{event_id}:{hash}`: only a confirmation takes it, right after
  the event row and before any guest row;
- several guest rows are locked in one statement, in user-id order;
- a merge locks the chain's `users` row last, after every ledger lock it takes.

| Path | Locks, in order |
|---|---|
| Guest sign-up (`signup.sign_up`) | event `FOR KEY SHARE` (`crud_event.lock`), then the list `FOR KEY SHARE`, then the chain's guest row `FOR UPDATE` (continuing a chain), then `guest-address:{hash}` (with an address), then `shared-list-day:{list id}`, then `shift-capacity:{shift id}` |
| Member booking (`create_booking`) | membership `FOR KEY SHARE` (`_lock_membership`), then `shift-capacity:{shift id}` |
| Confirm, promote (`guest_account.confirm`) | event `FOR KEY SHARE`, then `guest-account:{event_id}:{hash}`, then the chain's guest row `FOR UPDATE`, then the chain's unused pass rows (their `DELETE`). No ledger lock, no shift lock |
| Confirm, merge | event `FOR KEY SHARE`, then `guest-account:{event_id}:{hash}`, then the chain's and the account's guest rows `FOR UPDATE` in one statement in user-id order, then `vouchers:{event}:{user}` for each event of `guest_vouchers.ledger_event_ids(chain)` and both users, sorted, then the chain's `users` row `FOR UPDATE`, then the rows the moves touch. No shift lock: a merge only moves or frees places |
| Manage link (`guest_tokens.resolve`: read, cancel, reminders, erase) | the guest row `FOR UPDATE`; a merged chain's mail token locks its account's row. No shift lock: cancelling only frees places |
| "Das war ich nicht" (chains only) | the guest row `FOR UPDATE`, then `guest-address:{hash}` (only when it suppresses) |
| A guest's code: issue or status | the guest row `FOR UPDATE` (resolve), then the user's `users` row `FOR KEY SHARE` when issuing (the pass insert). No ledger lock, as for members |
| Redeem (`vouchers.redeem`) | `vouchers:{event}:{holder}`, then the pass row (`consume_pass`), then the holder's `users` row `FOR KEY SHARE` (the entry insert). A guest's row is read without a lock |
| Check (`vouchers.check`) | the pass row (`hold_pass`) only |
| Correction | `vouchers:{event}:{user}`, then the user's `users` row `FOR KEY SHARE` (the entry insert) |
| Settling (`settle_earnings`, inside organiser changes) | nothing of its own; each earning insert takes its user's `users` row `FOR KEY SHARE` |
| Organiser removal (`removal.remove_signups`) | every guest row touched `FOR UPDATE`, in one statement in id order, then `guest-address:{hash}` per mail, in the order of the hashes |
| Edit, pause, resume, end, rotate one list (`manage.lock_for_change`) | event `FOR SHARE`, then the list `FOR UPDATE` |
| Create, bulk (`manage.bulk`) | event `FOR SHARE`, then, for bulk, the lists `FOR UPDATE` in id order |
| Pause-all (`manage.pause_all`) | event `FOR NO KEY UPDATE`, then the live lists `FOR UPDATE` in id order |
| Deleting the event (existing) | event `FOR UPDATE`, then the lists and guest rows by CASCADE |
| Retention sweep (`retention.sweep_guest_data`) | the due guests' rows `FOR UPDATE SKIP LOCKED` in one statement (`crud_shared_list_guest.lock_unheld`), never waiting; a held one waits for the next run |
| Guest mail from a notice (`guest_mail.deliver_notice`) | `guest-address:{hash}` only, in a short transaction of its own |
| Reminder poller (`reminder_poller`) | the due reminders `FOR UPDATE SKIP LOCKED` (`crud_reminder.fetch_due_reminders`), released at once; each is then read again without a lock (`crud_reminder.get_pending`) and sent to whoever holds it now, so one a merge handed to the account in between reaches the account. Nothing is held while the mail goes out |
| Opening the public page (`public_page.count_view`) | the list row, through the `view_count` increment, as the last statement |

Why these modes:

- The sign-up holds the list `FOR KEY SHARE`, which conflicts with the `FOR
  UPDATE` of a pause or an end. A pause therefore waits for the sign-ups in
  flight, and once it has committed, no sign-up that read "live" can complete.
  `FOR KEY SHARE` does not conflict with the row lock of the `view_count`
  increment, so a crowd opening a popular list never queues behind sign-ups.
- The sign-up and the confirmation take the event before anything else,
  because deleting the event takes the event row before the list and guest
  rows its CASCADE reaches.
- A change to a list holds the event `FOR SHARE`, which conflicts with
  pause-all's `FOR NO KEY UPDATE`. A person in charge resuming a list beside an
  emergency stop either finishes first or reads the switch the stop turned off.
  Neither mode conflicts with the sign-up's `FOR KEY SHARE` on the event.
- Two removals may share addresses. Taken in request order, each could hold one
  address and wait for the other's; the hash order makes the second wait its
  turn.
- The account lock is taken only by a confirmation, as the first waitable lock
  after the event row, so nobody holding a guest row ever waits for it. The
  only multi-row lockers (confirm, removal) sort.
- Ledger holders (redeem, correction) never wait for a guest row. They may wait
  for a chain's `users` row, which a merge takes only once it holds every
  ledger lock it needs. A settling organiser holds nothing the merge needs
  before that row; the merge touches bookings only after it.
- Paths that hold a guest row and then wait for `guest-address` (sign-up,
  not-me, removal) are never waited for by a confirmation, which does not take
  it.

The retention sweep never waits for a guest row: it skips one that another
transaction holds, and judges the rows it locked again, since a confirmation
or a sign-up may have committed a later shift since its first look. Without
that, a sweep beside a merge would anonymise the account and leave the merged
chain's future booking under it, named and without a manage link. An operator
deleting a guest user by hand (`DELETE /users/{id}`) updates guest rows without
ordering; a collision with a confirmation is left to Postgres's deadlock
detection.

`tests/logic/test_shared_list_signup_concurrency.py`,
`test_shared_list_change_concurrency.py`,
`test_shared_list_guest_account_concurrency.py`, `test_voucher_concurrency.py`
and `test_booking_capacity.py` run these on committed connections.

## The public page

`GET /public/shared-lists/{code}` returns the title, the intro, the event (name,
dates, zone), the form settings, `retention_days` (`GUEST_DATA_RETENTION_DAYS`,
so no page writes the number into its text) and a status of `live`, `paused`
or `closed`. Expired and ended both read as `closed`: strangers are not told
why. While the list is live, `days` holds the offered shifts with the task
name, place, times, `capacity`, `free`, `full` and `vouchers` (what the task
earns a shift, 0 for none), and, only while the list's `show_names` is
`first`, `names` and `others_count`.

It never returns full names, addresses, phone numbers, user ids, task
descriptions, people in charge, other lists, `share_note`, `created_by_name` or
`view_count`. It sets `Cache-Control: no-store`. The organisers' `GET
/shared-lists/{id}/preview` builds the same page (`public_page.build_public_list`)
and is never counted as a view.

The title and intro are organiser text shown to strangers. Render them as plain
text, never as HTML or Markdown.

The page narrows its shifts in the browser, to one task, one day or those with
a place left (`filterDays` in `lib/guest-signup.ts`, `PublicShiftFilters.vue`).
Each filter shows only when it can narrow anything, and nothing is kept: the
next visit, or "Fertig – nächste Person", starts with every shift.

`view_count` is approximate: `public_page.count_view` adds one atomically, only
while the list is live, as the last statement of the request so its row lock
lasts only until the commit.

**First names.** `public_page.first_names` names a guest's booking only when the
booking has `show_first_name`, under the booking's own `guest_name`, and only
while the guest's contact row exists and is not erased (a guest whose event was
deleted is never named, even where a moved task took the booking to another
event); whichever list they came through, and only on a list that currently
shows names. The consent is stored on each booking at its sign-up and never
changes. Switching a list to `first` therefore cannot publish a guest who
signed up when it showed no names, and switching it back to `none` hides
everyone. Members are never named publicly.

The frontend routes `shared-list-public` (`/l/:code`) and `guest-signup-manage`
(`/guest-signup`) carry `meta.noindex`, which `src/lib/page-head.ts` turns into
a robots meta tag. In the frontend container, nginx (`frontend/nginx/default.conf`)
also answers both with `X-Robots-Tag: noindex, nofollow` and
`Referrer-Policy: same-origin`, so a list's address never leaves the site in a
`Referer`. The prerendered `robots.txt` disallows `/guest-signup` but not `/l/`
on purpose: a crawler that may not fetch a page never sees its noindex.

## Printing a notice

For whoever may share the tasks, a task's "Drucken" and the event's "Alle
Aufgaben drucken" print a shared list's notice, so the paper's QR code leads to
`/l/<code>` and anyone can sign up without an account. There is one sheet
layout (`components/print/PrintSheet.vue` with `PrintShiftDays.vue`, the rules
in `lib/print-sheet.ts`): a task's own
sheet lists every shift with a line per place, a list's sheet only the shifts
the list offers, with their free places, their vouchers and a line per free
place. The routes:

| Route | View | Prints |
|---|---|---|
| `/print/lists/:listId` | `PrintListView` | A list's notice: title, intro, QR code, the offered shifts by task and day. Read through `GET /shared-lists/{id}` and its preview, so it has the read gate (`require_shared_list_visible`) |
| `/print/tasks/:taskId` | `PrintTaskView` | A task's own sheet, without a QR code. What members and people in charge while `managers_share_lists` is off print |
| `/print/events/:eventId?mode=all&list=<id>` | `PrintEventView` | One sheet per task; the tasks the list offers carry its QR code and only its shifts |

The overview (`?mode=overview`) keeps its QR code to `/app/events/<id>`, and old
sheets' codes to `/app/tasks/<id>` still open the task.

**Which list.** `lib/shared-list-print.ts` mirrors the server's rules so the
dialog can say why a sheet goes without a QR code: `canShareTask` is
`require_shared_list_tasks` (event admins any task, a person in charge their
own while the switch is on, never with the kill switch off). One
task goes on a list by `manage.validate_selection` for a list of only that
task (`taskOfferProblem`: published, no team, a shift that has not started
with a free place). A whole event's print (`planEventPrint`) takes every task
the viewer can share that is published, has no team and has a shift that has
not started, full or not, and needs a free place only somewhere among them,
as `validate_selection` does for the whole list; at most `MAX_TASKS` (50), the
dialog names the others, and above 50 every sheet prints without a QR code.
A task's fill level never decides which tasks are asked for, so the list
found stays the same while shifts fill and empty.

`composables/useSharedListPrint.ts` then asks
`GET /events/{id}/shared-lists/reusable?task_id=…` (the same gate as creating,
so it answers what a create would refuse; any 403 or 404 there makes the plain
sheet). It returns `{list}` (`overview.reusable`): a list the caller manages
that has not ended and whose current tasks are exactly the ones asked for, or
with `covering=true` (a whole event's print) include them all, so a task that
has nothing left to come does not cost the event its list. The newest live
one wins, else the newest paused or expired one, whose notice then offers to
resume or reopen it instead of a second list for the same shifts. Without one,
`SharedListPrintDialog` asks once and creates a list through the ordinary
create with the wizard's defaults (`noticeListBody`: the task's name, or
"<event> – alle Aufgaben", every shift ahead, the address required, no phone,
no names, no limit, closing with the last shift), or opens the wizard with
`?tasks=`. "Anlegen und drucken" looks once more first, since the dialog may
have stood open while someone else made the list.

A list that is not live prints nothing: the print toolbar (`PrintListStatus`)
says why and offers the management page's fix (resume, reopen, extend, share
again), without the button the server would refuse a viewer or a locked person
in charge. After a fix the sheet keeps the viewer's display choices and names.
"Aushang drucken" on a list's page and in the wizard's last step opens
`/print/lists/<id>`. Every way out of the wizard's last step replaces the
wizard in the history, so Back returns to where the sharing began rather than
to an empty wizard that would share the tasks twice.

## Guest tokens

`logic/shared_lists/guest_tokens.py` derives every token from the guest row and
stores none:

```
token = "<guest user id hex>.<tag>"
tag   = base64url(HMAC-SHA256(key, "<guest user id hex>:<manage_nonce>"))
key   = HMAC-SHA256(SECRET_KEY, label)
```

`manage_nonce` is `secrets.token_hex(16)`, 128 bits, set when the chain starts.
Every mail can rebuild the link, and a database dump does not reveal one.

| Function | Label | Who holds it | May |
|---|---|---|---|
| `manage_token` | `wirksam/guest-manage/v1` | whoever submitted the form: it is the sign-up's `guest_token` | read, cancel, switch reminders, erase, show a voucher code, continue the chain, until the chain's address is confirmed |
| `mail_token` | `wirksam/guest-mail/v1` | whoever reads the mailbox: every mail links to it | all of that, "Das war ich nicht", and confirming the address |
| `address_hash` | `wirksam/guest-address/v1` | nobody; it stands for an address in `guest_activity_log` and `guest_mail_suppressions` | |

Two tokens, because "Das war ich nicht" stops all mail to the address for good,
and anyone can type someone else's address into a form. With the sign-up's
token, `POST /public/guest-signups/not-me` is `403
guest_signup.mail_link_required`. `GuestSignupManage.can_reject` tells the page
which token it holds.

- `resolve` compares in constant time and locks the guest row `FOR UPDATE`.
  On the manage routes any failure (malformed, forged, revoked, retired, an
  erased guest) is the same `404 guest_signup.not_found`; continuing a chain
  with one is `403 shared_list.guest_token_invalid`. What each token opens
  once a guest account exists is in [Guest accounts](#guest-accounts).
- `peek` accepts what `resolve` accepts, without taking a lock, and returns
  nothing unverified or dead. A confirmation looks first, so a forged token
  takes no lock, and a retired response token counts as a miss.
- Setting `manage_nonce` to NULL revokes every token of the chain at once. Erasing,
  "Das war ich nicht" and the retention sweep do.
- `manage_url` puts the token in the URL fragment, `/guest-signup#<token>`,
  which a browser never sends to a server or puts in a `Referer`. The frontend
  sends it in POST bodies. It never appears in a path or a query: the request
  log (`RequestLoggingMiddleware`) writes the path, and nginx the query too.
- Rotating `SECRET_KEY` invalidates every manage link, and changes every
  address hash: the suppressions and the day's counts in the log stop matching
  any address, so an address that said "Das war ich nicht" can be mailed again.

## The manage link

All under `/public/guest-signups` with the token in the body. They stay up while
the kill switch is off, because guests already signed up still get mail that
links here. [Rate limits](#rate-limits): per guest once the token resolves,
per IP only for a token that does not.

| Route | Function | Does |
|---|---|---|
| `POST /manage` | `read_guest_signups` | `GuestSignupManage`: the wallet holder's name, the address, every booking (confirmed and cancelled, each with its own event, since a moved task takes its bookings to another event, its `vouchers`, `show_first_name` and `name`), what the page may offer (`confirmed`, `can_confirm`, `can_reject`, `reject_suppresses`), `has_phone`, `retention_days`, `erase_on` and `vouchers` per event. Read-only |
| `POST /cancel` | `cancel_guest_signup` | Takes the guest off one shift until it is over (`409 booking.shift_over`), as members can. Cancels its reminders. Nobody is told |
| `POST /reminders` | `set_guest_reminders` | Writes the reminder on or off for every shift still ahead, through `replace_for_booking`. `409 guest_signup.no_email` without an address |
| `POST /erase` | `erase_guest_data` | [Erasure](#erasure) of the chain or the account behind the token. 204 |
| `POST /not-me` | `reject_guest_signup` | Mail token of an unconfirmed chain only: `403 guest_signup.mail_link_required` for the sign-up's token, `409 guest_signup.reject_confirmed` on an account. Suppresses the address unless it has a live guest account at any event, then erases the chain. 204 |
| `POST /confirm` | `confirm_guest_address` | "Ja, das bin ich". 200 `GuestConfirmResult`: the account's mail `token`, which the page uses from then on, and `manage` ([Guest accounts](#guest-accounts)) |
| `POST /vouchers/pass` | `issue_guest_voucher_pass` | `{token, event_id}` → 201 `VoucherPassRead` ([Vouchers for guests](#vouchers-for-guests)) |
| `POST /vouchers/pass-status` | `read_guest_voucher_pass` | `{token, event_id, pass_id}` → `VoucherPassStatus` |

`erase_on` is `retention.erase_on`: the guest's last day plus
`GUEST_DATA_RETENTION_DAYS` plus one, the first day the sweep counts them due.
`reject_suppresses` tells the page which "Das war ich nicht" text to show. It
is asked only where the page offers the choice (`can_reject`) and is false
otherwise: whether an address has an account at some other event is nobody's
business who merely typed it into a form.

## Guest accounts

A guest account is a `shared_list_guests` row with `confirmed_at`: at most one
per event and address, enforced by `uq_shared_list_guests_account`, unique on
`(event_id, lower(email))` where `confirmed_at IS NOT NULL`. An erased account
has no address, and NULLs are distinct, so erasing frees the slot.
`guest_account.confirm` is the only code that promotes or merges guest users.

**Confirming.** Only a mail link can confirm, and only from a button: `POST
/confirm` is "Ja, das bin ich" on the manage page, which offers it
(`can_confirm`) when the page was opened from a mail, the chain is not
confirmed yet and has an address. The page's automatic `/manage` stays
read-only, so link scanners confirm nothing. The route verifies the token with
`guest_tokens.peek` before any lock: a miss, a response token the
confirmation retired included, counts against the IP, a hit against the
guest.

- The **first** confirmation of an address at an event **promotes** the chain in
  place: `confirmed_at` is set and the chain's unused voucher codes are deleted.
  Nothing moves.
- Every **later** one **merges** the chain into the account
  (`guest_account.merge_guest`): the chain's unused codes are deleted, a
  booking on a shift both have is resolved (the source's goes, unless only it
  is confirmed), then bookings, reminders (`user_id`), earnings, ledger entries
  and used codes move to the account's user; an alias row is written and the
  chain's user is deleted, its contact row by CASCADE. The account keeps its
  name, phone and language (the first confirmed chain's, for the wallet only):
  each booking carries its own person.
- The same address at another event is another account.
- Confirming an account again, or a merged chain's mail link, answers with the
  account. `403 guest_signup.mail_link_required` for a live chain's response
  token, `404 guest_signup.not_found` for a retired one and for a chain without
  an address (a list with `ask_email = off`).

**What each token opens:**

| Token | Found | Opens |
|---|---|---|
| mail, unconfirmed chain | guest row | the chain, `from_mail` |
| response, unconfirmed chain | guest row | the chain |
| mail, account | guest row | the account, `from_mail`. For a promoted chain, the link in its own confirmation mail |
| response, account | guest row | nothing: retired by the promotion. `retired_response_token` reports it |
| mail, merged chain | alias | the alias's account, `from_mail` |
| response, merged chain | alias | nothing: retired by the merge |

So an unconfirmed chain sees only itself, and an account is only reached
through mail tokens. Whoever merely typed someone's address loses the chain at
its confirmation, together with every code shown from it. Every later mail to
an account links its mail token.

**The residual risk.** A mail link is a key to the wallet: every mail link of a
confirmed address opens the whole account, through its alias if the chain was
merged, and people forward sign-up mails. Whoever gets one can show a code and
spend the pooled vouchers, cancel shifts, or erase. The link is the only key a
guest has, so this is not closed; every guest mail says the link is private
(`link_private`, `link_private_vouchers`), and so must the done page.

## A sign-up's person

A guest account pools sign-ups from different lists, forms and possibly people
(a family sharing one address). One `users` row cannot say "Tom on this shift,
Maria on that one", so each guest booking carries its own person, written at
every sign-up, a reactivated row included: `bookings.show_first_name` (the
form's and the list's `show_names` both `first`), and `bookings.guest_name` and
`guest_phone` (the chain user's at that moment). Member bookings keep false,
NULL and NULL; their person is the member's profile.

**The rule.** Wherever a booking's person is shown, a list guest's booking shows
`guest_name` and `guest_phone`, never the guest user's `name` and
`phone_number`. Read it through `app.crud.booking.person_name` and
`person_phone`, or `person_name_sql()` in a query. The readers: the public
page's first names, the shift tiles (`crud_booking.confirmed_bookers`), `GET
/shifts/{id}/bookings`, `GET /tasks/{id}/bookings`, the preview of a shift
regeneration, the bookings CSV, the organisers' table of sign-ups (name, phone,
search, sort and the duplicate hint), the operator's search (which also matches
the snapshots, so the operator finds Tom inside Maria's account), and guest
mail about bookings, which greets their name (`greeting_name`: one name, or
nobody by name when they differ).

Hours belong to a person too. `work_hours.event_hours`, the hours CSV and
reporting's top volunteers count a list guest's bookings per `guest_name`, so
a guest account gives one row per name, all with its `user_id`; `user_id` and
`name` together tell the rows apart. `GET /events/{id}/hours/{user_id}` takes
the row's `name` for a guest (`?name=`), and without it counts the sign-ups
made under the guest user's own name.

A guest user's own `name` and `phone_number` belong to the wallet holder: the
manage page's header, the organisers' voucher overview, the redeemer's check
sheet and the top fields of the operator's export. A merge therefore changes no
name or phone anywhere. `erase.anonymise` nulls the snapshots with the user's
name, so they follow the user's retention clock.

## Vouchers for guests

Guests earn like members ([`VOUCHERS.md`](VOUCHERS.md#guests-of-shared-lists)).
`logic/shared_lists/guest_vouchers.py` holds what is theirs only:

- `voucher_event_ids`: the events in which the guest has, or will have,
  vouchers (confirmed bookings on tasks that earn, earnings worth something,
  entries, unused codes). It drives `GuestSignupManage.vouchers`, own event
  first, and which events a code may be asked for;
- `ledger_event_ids`: wider, every event whose ledger lock a merge must hold,
  including bookings on tasks without vouchers, where a correction is allowed;
- `guest_vouchers`: `vouchers.account` per event, with every entry's
  `actor_name` and `note` and the summary's `email` blanked: a guest page shows
  no member's name and no organiser's free text. The operator's export uses it
  too;
- `issue_pass` and `pass_status`: the members' code, through the token.

Redeeming takes a guest by code only (`vouchers._holder_or_404`): their manage
link must be alive and they must have a part in the event. The overview
(`/vouchers/people`) lists guests with `is_guest` and the address from their
contact row, and the redeemer's check sheet tags them (`VoucherCheckResult.
is_guest`). A confirmation deletes the chain's unused codes, so a code shown
from a token that typed the address can never spend what the confirmation
pools; `check` reads its pass again after the hold for the same reason.

## Guest mail

A guest gets five mails, each written by `logic/shared_lists/guest_mail.py` and
each linking to the mail token:

| Mail | When | Log kind |
|---|---|---|
| confirmation | the first sign-up of a chain with an address | `confirmation` |
| reminder | a day before, if they asked for it | `reminder` |
| moved | an organiser moved their shift | `moved` |
| cancelled | an organiser removed their shift | `cancelled` |
| removed | an organiser took them off ([removal](#removing-sign-ups)) | `removed` |

The middle three are member notices too. `NotificationService.notify` hands a
guest's notice to `guest_mail.deliver_notice` before it resolves a title or a
body, and then `continue`s: no in-app row, no push, no SSE. Of the notices,
only `GUEST_MAIL_TYPES` (`booking.reminder`, `shift.time_changed`,
`booking.cancelled_by_admin`) become mail; every other notice is dropped for
guests. `UNDELIVERABLE_SUBJECT_PREFIXES` in
`logic/notifications/channels/base.py` lists `listguest|` as the second line.

Every guest mail is written from database rows only: the event's and the task's
name, the date, the times, the place and the vouchers a shift earns. Never the
list's title or intro, never a cancellation reason (which people in charge can
type), and nothing from `logic/notifications/locales`. Everything interpolated
is escaped. The texts are their own, in English and German, in the guest's
`preferred_language`.

- A mail about bookings greets the name of those sign-ups (`guest_name`), or
  nobody by name when a pooled account's sign-ups differ.
- A confirmation or a reminder about one shift that earns says how many
  vouchers and how to redeem them.
- The confirmation also says how to confirm the address (`confirm_hint`; only
  `confirm_hint_vouchers`, for a shift that earns, adds that the vouchers are
  added up), and how long the data is kept (`GUEST_DATA_RETENTION_DAYS`,
  naming the phone number only when one is stored), and that unredeemed
  vouchers expire then, when the shift earns.
- Every mail says that whoever has the link can change the sign-ups
  (`link_private`), and redeem the vouchers when a shift in it earns some
  (`link_private_vouchers`).
- Its line on "Das war ich nicht" says what the page will do
  (`guest_mail.not_me_offer`, the rule of `reject_suppresses`): delete the
  sign-up and never write to the address again (`not_me_suppresses`), only
  delete it while the address has a guest account at any event
  (`not_me_erases`), or nothing in a mail to a guest account, whose page does
  not offer it.
- A confirmation itself sends no mail and writes no `guest_activity_log` row.

- `data` is only a key into the database: the reminder's `booking_id`, the
  moved shift's `slot_id`, and the cancellation's `booking_ids`, which
  `dispatch_booking_cancelled_by_admin` fills with exactly that person's
  bookings of the action on shifts not over yet. The cancelled shifts are gone,
  so the mail reads them from the booking's snapshot and names the event from
  the notice's scope: a task moved to another event took its bookings there.
- **Every guest mail is reserved through `guest_quota.reserve_mail` first.** It
  refuses when SMTP is not configured, about a demo event ([In a demo](#in-a-demo)),
  for a suppressed address, and over a daily ceiling, and otherwise writes the one log row the mail counts as,
  however many shifts it names.
- Without SMTP nothing is reserved or sent, and only the kind is logged. The
  transactional mail path would log the link instead, which is fine for a
  one-time auth token but not for a manage link that reads, cancels and erases
  until retention. The sign-up then answers `mail_queued=false`, and the page
  shows the manage link. Locally, the mailcatcher counts as configured.
- `send_guest_mail` sends a reserved mail and never raises. `deliver_notice`
  reserves in a short transaction of its own, so the address lock is not held
  while the notice goes on to other recipients.

## The daily ceilings

Anyone can create an event, so the names in a guest mail are chosen by whoever
shares a list, and the address it goes to is whatever an anonymous visitor
typed. The invitation limits work because the inviter is signed in; here nobody
is. So `logic/shared_lists/guest_quota.py` counts `guest_activity_log` over the
last 24 hours:

| Setting | Default | Counts | Over it |
|---|---|---|---|
| `GUEST_SIGNUPS_PER_ADDRESS_PER_DAY` | 20 | sign-ups by the address | `429 shared_list.too_many_for_address` |
| `GUEST_SIGNUP_EVENTS_PER_ADDRESS_PER_DAY` | 3 | other events the address signed up for | `429 shared_list.too_many_for_address` |
| `SHARED_LIST_SIGNUPS_PER_LIST_PER_DAY` | 500 | sign-ups through the list | `429 shared_list.daily_limit` |
| `GUEST_MAILS_PER_ADDRESS_PER_DAY` | 10 | mails of every kind to the address | the mail is not sent |
| `GUEST_MAILS_PER_EVENT_PER_DAY` | 1000 | mails about the event | the mail is not sent |
| `GUEST_MAILS_PER_ORGANISER_PER_DAY` | 2000 | mails about events of the organiser (`events.created_by_id` when the mail goes out) | the mail is not sent |

- **Nothing resets them.** The log has no foreign keys, so erasing a guest,
  rotating a list or deleting the event removes no row. Rows go after
  `ACTIVITY_LOG_DAYS` (7) days, in the [retention sweep](#retention).
- **No address in clear text.** The log and the suppressions hold only
  `address_hash`.
- **Exact where it matters.** The per-address counts run under the advisory
  lock `guest-address:{hash}` (`guest_quota.lock_address`), and the per-list
  count under `shared-list-day:{list id}`, both held until commit. The per-event
  and per-organiser counts are not serialised across addresses and may
  overshoot by the number of senders at the same moment, which a coarse fence
  can afford.
- **Mail an organiser triggers** (moving a shift again and again, deleting
  shifts) meets the same per-address ceiling, which is why there is no separate
  debounce. A refused mail logs its kind and the event, never the address.
- **Under `TESTING`** the counting is skipped, as for the invitation limits; the
  locks are taken and the rows written all the same.

**Suppression.** "Das war ich nicht" stores the address hash in
`guest_mail_suppressions` (`guest_quota.suppress`). A suppressed address may
still sign up; it is only never mailed, and the sign-up answers
`mail_queued=false` exactly as without SMTP, so the answer reveals nothing. The
table is never pruned. Only the operator lifts a suppression
(`guest_quota.lift_suppression`, [below](#data-subject-requests)).

## Who sees a guest

| What | Who |
|---|---|
| The name | wherever member names show: rosters, shift tiles, print views, hours. Each booking under its own sign-up's name ([A sign-up's person](#a-sign-ups-person)) |
| That someone signed up without an account | the same people: `is_guest` on `ShiftBookingEntry`, `ShiftBooker`, `TaskBookingEntry` and `VolunteerHours` |
| Address and phone number | event admins and the people in charge of that task, the same rule as for members. The address comes from `crud_shared_list_guest.contact_emails` |
| Which list a guest came through | the same, as `ShiftBookingEntry.via_list_title` (`crud_booking.shared_list_titles`, lists of the task's event only) |
| The first name on a public page | anyone, only with the guest's consent ([above](#the-public-page)) |

## Where guests are excluded or tagged

New code that lists users must decide what to do with `is_list_guest`, as it
does with `is_sandbox`. These are the places today:

| Where | What happens to a guest |
|---|---|
| `api/deps.py::_refuse_list_guest` | `403 auth.guest_account` on every dependency that loads a user: `CurrentUser`, `CurrentSuperuser`, `AnyUser`, `QueryTokenUser` and the `X-Test-User-Email` path. Unconditional, unlike `_refuse_unusable`. A guest has no password and no session, so this is the second wall. `AccessClaimsDep` loads no row and cannot check |
| `crud/user.py::search` | left out of the admin user list and its counts. The operator finds guests through `/list-guests` |
| `logic/notifications/service.py` | notices become guest mail or nothing ([above](#guest-mail)) |
| `logic/notifications/channels/base.py` | `listguest\|` is undeliverable on every channel |
| `logic/vouchers.py` | earn like everyone ([`VOUCHERS.md`](VOUCHERS.md#guests-of-shared-lists)). Listed in `balances` with `is_guest` and their contact address; redeemed by code only (`_holder_or_404`), never offered in the picker (`available_for_members`) |
| `logic/work_hours.py::event_hours` | listed among the former members, with `is_guest`, one row per name their sign-ups were made under. Their hours count |
| `api/routes/shifts.py` (`GET /shifts/{id}/bookings`, the tiles), `api/routes/tasks/crud.py` (`GET /tasks/{id}/bookings`) | tagged `is_guest`; contact data as in the table above |
| `api/routes/reporting.py::reporting_export` | the address from the contact row, and a last column "Booked Via" with the title of the list, if it belongs to the task's event |
| `api/routes/testing.py::reset_test_data` | deletes every guest without a contact row (their test event went with its test owner) |

Unchanged on purpose: capacity, `uq_booking_shift_user`, the overlap check,
`crud_membership.list_members` (guests are never members), and the volunteer
counts in reporting, where each guest user is one volunteer.

## Removing sign-ups

`POST /shared-lists/{id}/signups/remove` (`removal.remove_signups`) serves the
row action "Austragen", a selection, and the clean-up after a wave of fake
sign-ups. It is the only way an organiser cancels someone else's booking;
members' bookings stay out of it. The caller must see the list
(`require_shared_list_visible`).

- **Exactly one selector**, else `422 shared_list.remove_selector`:
  `booking_ids` (1 to 100), or `created_since` (naive UTC): every confirmed
  sign-up through the list from that moment on, at most `CREATED_SINCE_MAX`
  (500) per call, on tasks still in the list's event.
- **`notify`** (default true) sends each guest taken off one `removed` mail
  listing their shifts. Turn it off for spam, so typed addresses are not
  written to again.
- **`erase`** (default false, event admins only, else `403
  shared_list.forbidden`) erases every guest touched instead, and mails nobody.
  It is how organisers honour a guest who asks them to delete their data,
  which matters most for guests without an address, who have no mail with a
  manage link. A guest is erased whole: a chain with its other sign-ups, a
  guest account with everything pooled under its address, perhaps other
  people's. The table gives each sign-up of an account `pooled_signups`, so
  the dialog says how many go along before anyone ticks the box, and the
  result counts the sign-ups taken off beyond the selection in `also_removed`.
- **Per booking**, a refusal goes to `skipped` with a code and never fails the
  rest: not through this list, not confirmed, on a task that moved away, or
  handed to a guest account by a confirmation while the removal waited for the
  chain's row (`shared_list.signup_not_found`; a retry locks the account's
  row, so `erase` never erases an account without its lock); a task the
  caller is not in charge of
  (`shared_list.forbidden`); a booker who is not a guest
  (`shared_list.signup_not_guest`); a shift that is over (`booking.shift_over`:
  what was worked stays worked). With `erase`, the guest of an ended booking is
  still erased, and the booking stays without a name.
- Removed bookings are cancelled and their reminders cancelled in one statement
  (`crud_reminder.cancel_by_bookings`), so cleaning up 500 costs no more
  statements than one.

## Erasure

`erase.erase_guests` is the one rule for every way it happens: the guest's own
erase and "Das war ich nicht", an event admin removing sign-ups with `erase`,
and the operator's `POST /list-guests/{id}/erase`. The retention sweep uses its
anonymising half, `erase.anonymise`.

- **Deleted**: every booking whose shift is not over, which frees the place at
  once, and every cancelled booking. Their reminders cascade.
- **Kept**: confirmed bookings of shifts that are over, without a name, so fill
  rates and hours stay true. Whether a shift is over is judged on the clock of
  its own event (`crud.shift.wall_clocks`).
- **Anonymised**: `users.name` and `users.phone_number`, the kept bookings'
  `guest_name` and `guest_phone`, the contact row's `email` and `manage_nonce`
  set to NULL, and `erased_at` set. The aliases of chains merged into an
  account are deleted, and so are the guest's unused voucher codes. The notes
  of their corrections are cleared (the natural one names the person); the
  amounts stay. Unredeemed vouchers expire: no code can be shown any more. The
  organisers' table of sign-ups marks such a row `erased`.
- A guest with no booking left is deleted outright; the contact row cascades.
  Never one with ledger entries or earnings worth something, which a CASCADE
  would take from the stand's history: it stays, anonymous.
- **Erasing an account** erases everything pooled in it, and nothing else. A
  chain with the same address that nobody confirmed stays; it is erased
  through its own link, or by the operator on request.
- **"Das war ich nicht"** is for unconfirmed chains opened from their mail. It
  suppresses the address only while the address has no live guest account at
  any event (the suppression is global, and would silently stop the mail about
  the sign-ups its owner confirmed); then it only erases the chain.
- Only a guest's: an account that is not `is_list_guest` is left alone whatever
  id is passed.
- `guest_activity_log` is never touched, so erasing cannot reset a ceiling.

## Retention

`retention.sweep_guest_data` runs from the reminder poller every
`_GUEST_SWEEP_EVERY_N_CYCLES` (120) cycles, about once an hour, under the
poller's advisory lock, in one transaction. There is no other scheduler.

Retention is decided per guest **user**, from that user's own bookings, and
never from `shared_list_guests.event_id`: a moved task takes its bookings to
another event, and deleting an event leaves its tasks and their bookings
behind. A guest's last day is the latest date among their bookings (a booking
whose shift was removed keeps its date in the cancellation snapshot), else the
day of their last sign-up, else the day the user was created. A guest is due
once that day plus `GUEST_DATA_RETENTION_DAYS` (default 30) is before today on
the clock of the guest's event, the one their manage page names `erase_on` in
(`EVENT_TIMEZONE` once the event is gone): shift dates are wall dates, and
counted on UTC a guest west of it would lose their data the evening before the
day they were told. The sweep locks the due guests' rows without waiting
([Locks](#locks)); a guest whose row is held waits for the next run.

1. Due guests that still hold a name or a phone number (their own, or a
   booking's), or a cancelled booking, lose their cancelled bookings and are
   anonymised (`erase.anonymise`). No shift of theirs is ahead any more, so
   what stays are worked shifts without a name. Guests whose event was deleted
   have no contact row left and are anonymised all the same.
2. Guests without a name and without a booking are deleted. Never one with
   bookings: a booking in the event a task moved to outlives the event the guest
   signed up in. Nor one with ledger entries or earnings worth something.
3. `guest_activity_log` rows older than `ACTIVITY_LOG_DAYS` (7) go.

A guest account's clock is its latest pooled shift, for the names and phones on
its pooled bookings too. Unredeemed vouchers expire with the anonymisation. The
poller logs the counts (`SweepResult`). Running it twice changes nothing more.
Any text that tells guests how long their data is kept, the privacy policy
included, must state this rule and this number, say that unredeemed vouchers
expire then, and name only the data that list stores. The API returns the
number (`PublicSharedList.retention_days`, `GuestSignupManage.retention_days`
and `erase_on`), so no guest page writes it into its text.

## When things are deleted or moved

| What happens | Effect on lists and guests |
|---|---|
| Event deleted (by its owner, through `events.created_by_id` CASCADE, or a sandbox purge) | The lists, their task and exclusion rows, and the contact rows cascade, so the addresses and manage links go at once. The tasks survive with `event_id` NULL, and with them the bookings and the guest users. The sweep anonymises those guests by their own shift dates, and deletes them once no booking is left. `guest_activity_log` keeps its rows |
| Demo purged (`sandbox/cleanup.py::purge_sandbox`) | Unlike an event's delete, everything goes: the bookings and tasks, the lists and contact rows, the demo's `guest_activity_log` rows, and the guest users, found by their contact rows first since they hold no membership |
| Task deleted | Its link rows cascade. Guest bookings are cancelled through `cancel_bookings_for_shifts`, so the guests get the `cancelled` mail |
| Task moved to another event | `crud_shared_list.detach_task_from_lists` takes it off every list and drops its shifts' exclusions. The guest bookings move with the task, keep `shared_list_id` and keep working (manage link, reminders, mail). They leave the old list's sign-ups and counts. Retention follows their shift dates. If the source event is deleted later, those guests lose their address and manage link with it, while their bookings in the target event stay until the sweep finds them over |
| Task unpublished, archived, or given a `team_id` | It drops out at read time. The list's detail shows the task as not offered, with `not_offered_reason` |
| Shift deleted or regenerated away | The exclusion rows cascade. Bookings are cancelled with their snapshot, and guests get the `cancelled` mail |
| Shift moved | Reminders are rescheduled as for anyone, and guests get the `moved` mail |
| `POST /events/{id}/shift-dates` | `ends_on` moves with the shifts |
| Event zone changed | Nothing: expiry is derived |
| Guest user deleted (erasure or the sweep with nothing left, a merge) | The contact row, bookings, reminders, voucher rows and, for an account, its aliases cascade. Erasure and the sweep never delete one with ledger entries or earnings worth something; a merge moves everything first |
| List creator deleted | Nothing: `created_by_id` has no foreign key, and `created_by_name` is a snapshot. Event admins keep managing the list |

## Data-subject requests

Guests are absent from the admin user search, and their address is not in
`users.email`, so the operator answers a request about guest data through
`/list-guests` (`app/api/routes/shared_list_guests.py`, `CurrentSuperuser`).
There is no UI for these routes. They stay up while the kill switch is off. They
live under `/list-guests` because the catch-all `GET /users/{user_id}` would
shadow a path under `/users`.

```bash
API=https://api.example.org/api/v1
TOKEN=$(curl -s -X POST "$API/auth/login" -H 'Content-Type: application/json' \
  -d '{"email": "admin@example.org", "password": "…"}' | jq -r .access_token)

# Find guests: the address exactly (once normalised), or part of a name or a
# phone number. q is 3 to 100 characters.
curl -s -H "Authorization: Bearer $TOKEN" "$API/list-guests?q=anna@example.org"

# Everything stored about one guest (Art. 15): contact data, consent, and every
# booking with its event, task and times.
curl -s -H "Authorization: Bearer $TOKEN" "$API/list-guests/<guest_user_id>"

# Erase one guest (Art. 17), as their own "Meine Daten löschen" does. 204.
curl -s -X POST -H "Authorization: Bearer $TOKEN" "$API/list-guests/<guest_user_id>/erase"

# Mail an address again after "Das war ich nicht", when its owner asks.
# 204, or 404 guest_signup.not_suppressed when nothing stops mail to it.
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"email": "anna@example.org"}' "$API/list-guests/mail-suppressions/lift"
```

One person may be several guests: one per sign-up chain, even with the same
address, unless they confirmed it into one account. Erase every row the search
returns that the request covers. The export (`ListGuestExport`) holds the
contact data, `confirmed_at`, every booking with its own `name`, `phone` and
`show_first_name`, and `vouchers` per event (earned, redeemed, corrections,
without who redeemed or corrected and without notes). It leaves out
`manage_nonce` and aliases, which are credentials and not data about the
person. An unknown id, or one that is not a guest, is `404
guest_signup.not_found`, and so is an erase that waited for a confirmation
merging that guest into its address's account: the sign-ups are the
account's now, and the search finds them there by their names.

## In a demo

A demo event (`events.is_sandbox`) shares like any other, so a visitor trying
the organiser's side finds "Shared lists" with a list already on it
(`sandbox/seed.py::_seed_shared_list`, the manager variant only). Its guest is
`owner`, so every gate passes; the sandbox test in the gates still answers 404
to everyone else, the superadmin included.

What a demo cannot do is mail. Its owner is anonymous, and a list is a public
link that anyone signs up through with any address, so
`guest_quota.reserve_mail` refuses every guest mail about a demo event. The
sign-up then answers `mail_queued=false` and `show_manage_link=true`, as
without SMTP, and the page shows the guest their link. `PublicEventRef.is_sandbox`
lets the public page and the guest's page say it is a demo, with a "Demo"
pill in the header that opens the full note (`GuestDemoNotice.vue`), and the
wizard's last step says the same. Nothing
confirms an address there (confirming needs the mail's link), so a demo has no
guest accounts. The purge takes the lists, the guests and their log rows with
the demo ([When things are deleted or moved](#when-things-are-deleted-or-moved)).

## The kill switch

`SHARED_LISTS_ENABLED` (default true) is read twice, like `SANDBOX_ENABLED`.

- **Backend.** `require_shared_lists_enabled` in `app/api/deps.py` answers `404
  shared_list.disabled`. It is a router dependency on `shared_lists.py`, and a
  route dependency on the two list routes of `public_shared_lists.py` and the
  three organiser routes of `shared_list_guests.py`. It runs before the body is
  validated, so a sign-up with a broken body gets the 404, not a 422.
- **Not switched off:** the guests' `/public/guest-signups/*` routes and the
  operator's `/list-guests`. Guests already signed up still get reminders and
  mail about their shifts, and each mail sends them to the manage link. The
  retention sweep runs as well.
- **Frontend.** `frontend/docker-entrypoint.sh` serves the same value as
  `window.__APP_CONFIG__.SHARED_LISTS_ENABLED`, read with `isSwitchOn()`
  through `canUseSharedLists`. It is not in the prerender `TOGGLES`.

`REGISTRATION_MODE` does not gate shared lists: nobody who signs up through one
gets an account.

## Settings

All in `backend/app/core/config.py`, documented in `.env.example` and
[`deployment.md`](deployment.md).

| Setting | Default | Notes |
|---|---|---|
| `SHARED_LISTS_ENABLED` | `true` | [The kill switch](#the-kill-switch) |
| `GUEST_DATA_RETENTION_DAYS` | `30` | Days after a guest's own last shift until they are anonymised and their unredeemed vouchers expire. The API returns it (`retention_days`, `erase_on`), and the guest pages print no number of their own. The privacy policy belongs to no list, so no API answer carries it there: the frontend container serves the same variable as runtime config (`guestRetentionDays()` in `useAppConfig.ts`, default 30) |
| `GUEST_SIGNUPS_PER_ADDRESS_PER_DAY`, `GUEST_SIGNUP_EVENTS_PER_ADDRESS_PER_DAY`, `GUEST_MAILS_PER_ADDRESS_PER_DAY`, `GUEST_MAILS_PER_EVENT_PER_DAY`, `GUEST_MAILS_PER_ORGANISER_PER_DAY`, `SHARED_LIST_SIGNUPS_PER_LIST_PER_DAY` | 20, 3, 10, 1000, 2000, 500 | [The daily ceilings](#the-daily-ceilings) |
| `SHARED_LISTS_PER_EVENT` | `200` | Lists per event, ended ones included |
| `TURNSTILE_SECRET_KEY` | unset | Optional, so a deployment without Cloudflare keeps the lists. Outside `ENVIRONMENT=local`, `_recommend_turnstile_for_shared_lists` warns at boot while the lists are on without it |

## Rate limits

In-process counters in `app/core/rate_limit.py`, per worker and off under
`TESTING`, like the auth limits in [`AUTH.md`](AUTH.md#rate-limiting). They are
speed bumps; the fence is Turnstile and the ceilings above.

| Limiter | Limit | Key | On |
|---|---|---|---|
| `shared_list_view_limiter` | 120 / 10 min | IP | opening a list page |
| `shared_list_miss_limiter` | 20 / 10 min | IP | an unknown code only, so a scan meets it long before a crowd opening one link |
| `shared_list_signup_limiter` | 120 / hour | `<ip>\|<code>` | signing up |
| `shared_list_signup_ip_limiter` | 240 / hour | IP | signing up |
| `guest_ip_limiter` | 6000 / 10 min | IP | every `/public/guest-signups/*` call, before any database work: a flood guard only |
| `guest_link_miss_limiter` | 30 / 10 min | IP | a manage token that does not resolve, a retired response token included |
| `guest_manage_limiter` | 30 / 10 min | `guest:<user id>:<kind>` | `/manage`, `/cancel`, `/reminders`, `/erase`, `/not-me`, `/confirm` |
| `guest_pass_status_limiter` | 120 / min | `guest:<user id>:<kind>` | `/vouchers/pass-status`, which a code screen asks every two seconds |
| `voucher_pass_limiter` | 20 / min | `guest:<user id>:<kind>` | `/vouchers/pass`, the members' bucket for issuing a code |

The shared-list ones answer `429 shared_list.rate_limited`, the guest ones `429
guest_signup.rate_limited`, issuing a code `429 voucher.rate_limited`. The
sign-up limits are sized for a tablet at a stand, or one venue behind one
address, signing up a queue of people. The manage token is the real key, an
HMAC tag nobody guesses, so the guest routes count per guest once it resolves
(`_guest` in the router) and per IP only when it does not: a queue of guests
showing codes behind one venue NAT never shares a bucket, and a code screen on
a dead link stops asking. The kind is `mail` for a mail link and `response`
for the token the sign-up answered with (`_bucket`): whoever typed someone
else's address holds the latter, and must not use up the calls the mailbox's
owner needs for "Das war ich nicht", erasing or confirming.

## Error codes

Every code needs an entry in `frontend/src/locales/{en,de}/errorCodes.json`, or
the raw backend string shows on screen.

| Code | Status | Extensions |
|---|---|---|
| `shared_list.not_found`, `shared_list.disabled`, `shared_list.shift_not_offered` | 404 | |
| `shared_list.forbidden`, `shared_list.managers_disabled`, `shared_list.guest_token_invalid` | 403 | |
| `shared_list.tasks_forbidden` | 403 | `task_ids` |
| `shared_list.task_not_in_event`, `shared_list.task_not_published`, `shared_list.task_team_locked` | 422 | `task_ids` |
| `shared_list.no_shifts`, `shared_list.no_free_places`, `shared_list.email_required`, `shared_list.phone_required`, `shared_list.remove_selector` | 422 | |
| `shared_list.ends_on_invalid` | 422 | `last_shift_date` |
| `shared_list.event_not_published`, `shared_list.ended`, `shared_list.not_live`, `shared_list.nothing_to_offer`, `shared_list.paused`, `shared_list.closed`, `shared_list.shift_started`, `shared_list.already_signed_up` | 409 | |
| `shared_list.too_many`, `shared_list.max_per_person` | 409 | `max` |
| `shared_list.too_many_for_address`, `shared_list.daily_limit`, `shared_list.rate_limited` | 429 | |
| `shared_list.signup_not_found`, `shared_list.signup_not_guest` | | only as `skipped` codes of a removal |
| `voucher.rate_limited` | 429 | issuing a guest's code, as a member's |
| `voucher.pass_not_found` | 404 | the status of a guest's code that was replaced or deleted |
| `guest_signup.not_found`, `guest_signup.not_suppressed` | 404 | |
| `guest_signup.mail_link_required` | 403 | |
| `guest_signup.no_email`, `guest_signup.reject_confirmed` | 409 | |
| `guest_signup.rate_limited` | 429 | |
| `auth.guest_account` | 403 | |

Reused: `booking.slot_full`, `booking.time_conflict`, `booking.shift_over`,
`auth.captcha_failed` and `event.not_found`.

## Gotchas

- **Adding a confirmed booking** on any new path takes
  `booking_capacity.lock_shifts` before it counts, and after any lock on a
  guest row or a membership.
- **Writing reminders for a booking that may have had some** goes through
  `crud_reminder.replace_for_booking`, never a plain insert:
  `uq_reminder_booking_offset` turns a reactivated booking's leftover rows into
  a 500.
- **Every guest mail** goes through `guest_quota.reserve_mail`, and is written
  from database fields only.
- **A booking's person** is `bookings.guest_name` / `guest_phone`, its consent
  `bookings.show_first_name`. Never show a list guest's `users.name` for a
  booking, nor count a guest account's hours under it; use
  `crud.booking.person_name`. A list of people may hold one guest user under
  several names, so key such rows by `user_id` and `name` together.
- **Rate-limit keys of a guest** go through `_bucket` in the router: one per
  guest and kind of token, so whoever typed an address never spends the
  mailbox owner's calls.
- **Promoting or merging guest users** happens only in `guest_account.confirm`,
  under the [lock order](#locks). A future claim into a real account reuses
  `merge_guest` and takes `guest-account:{event_id}:{hash}` before any guest
  row, as confirm does.
- **One clock per request.** Every management route reads
  `clock.wall_clock_now(event.timezone)` once. A view across events judges each
  booking on its own event's clock (`crud.shift.wall_clocks`). Tests patch
  `app.logic.clock.wall_clock_now`.
- **Patching in tests.** The routes import `verify_turnstile` and
  `send_guest_mail` by name, so tests replace
  `app.api.routes.public_shared_lists.verify_turnstile` and the like. Fixtures:
  `make_shared_list`, `test_shared_list` and `make_list_guest` in
  `tests/fixtures/shared_lists.py`, helpers in `tests/fixtures/guest_signups.py`
  (`confirm_address` among them; see `tests/fixtures/README.md`). The E2E
  helpers `createSharedList`, `getSharedList` and `publicSignup` are in
  `frontend/e2e/helpers/api.ts`. E2E has no mailbox: `POST
  /testing/guest-mail-link` (`{token}` → `{token}`) gives the mail token of
  the guest behind a sign-up's token.
- **The organisers' views** compute over every list of the event in Python
  (`overview.load`, a fixed number of queries), then filter, sort and page.
  That is affordable because of `SHARED_LISTS_PER_EVENT`, and needed because
  the status and the issues depend on the clock and on every other list. Keep
  new aggregates in `crud/shared_list_overview.py`, not in a loop.
- **A search** escapes `%`, `_` and `\` through `crud.search.like_pattern`.
