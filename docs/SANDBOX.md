# The demo sandbox

The landing page offers a visitor a way to see the application working before
they register: one click hands them a throwaway account and an event already
full of plausible shifts, bookings and teammates, dated around today.

The whole design follows from one constraint. This writes to the production
database on behalf of someone who has not identified themselves, so the
feature is only acceptable if the rows it creates reliably go away again. Every
decision below is downstream of that.

## What a sandbox is

Two rows and everything hanging off them:

- a **guest account** — `users.is_sandbox = true`, `subject = 'sandbox|<uuid4hex>'`,
  no email address, no password hash;
- a **demo event** — `events.is_sandbox = true`, private, with
  `events.sandbox_expires_at` set to now plus `SANDBOX_TTL_MINUTES`.

Seeded into it: eight published tasks, each with a real `ShiftBatch` and stored
generation config; shifts before, on and after today; five more guest accounts
as teammates, with availabilities; bookings that leave the rota deliberately
uneven; a notification inbox for the visitor; the tasks' locations as real
`locations` rows with a short description each, plus two venue plans (the
building and the outdoor area) drawn as shapes, with markers on them; five
teams (an open Setup crew the visitor is in; the Cash desk, which needs
approval and locks the wristband check; Shuttle drivers behind a class B
driving licence; Childcare behind an extended police certificate, which locks
the kids' games; and First aid behind a first-aid course, with one member whose
check has expired); and — for the manager role only — one pending invitation,
one pending join request, the notification telling them about it, the lead of
the Cash desk, and five team requests to review from four made-up people: Vera
for the Cash desk and the Shuttle drivers, Jordan for the Cash desk (no note),
Carla for Childcare (police certificate, no file by design) and Sven for First
aid with a sample certificate attached.

The sample certificate is a PNG drawn at seed time by
`logic/sample_document.py`, because a sandbox may not upload a file
(`sandbox.upload_disabled`). It reads MUSTER / SAMPLE, carries a diagonal
watermark, names a made-up provider and says it is not a valid certificate.
Everyone the rota puts on a locked task is an approved member of its team,
and the visitor is never booked onto one, so the demo shows no booking the team
gate would have refused.

### The same content as the local dev seed

`just seed` (`app/scripts/seed_demo.py`, run by `just dev` on every start)
builds this event for the dev login `dev@example.com` through
`seed.py::seed_dev_event`: the manager variant, but as an ordinary permanent
event. Nothing in it is a sandbox row — `is_sandbox` is false on the event, its
tasks and every made-up person, and `sandbox_expires_at` is NULL — so the TTL
sweep never touches it and the visibility filters below treat it like any other
event. The made-up people carry the `demo|` subject prefix instead of
`sandbox|` and have no email address, so they stay undeliverable. The script
skips while the dev login already owns an event with the seeded name
(`--force` adds another, dated around today; `--lang de` seeds it in German)
and refuses to run outside `ENVIRONMENT=local`.

The venue plan exists for the same reason as the inbox: a sandbox may not
upload an image (`PUT /venue-plans/{id}/image` answers 403
`sandbox.upload_disabled`, because it would store an anonymous visitor's file),
so without a seeded plan the map would be an empty state the visitor can do
nothing about. Both plans are blank canvases made of `venue_shapes` rows
(rooms, areas, paths, captions), exactly what an organiser would draw in the
editor, so they are vectors that follow the light and dark theme rather than
pictures. `logic/sandbox/venue_plan_shapes.py` lists them shape by shape,
language-free; the seeder resolves the captions. Every marker is placed from its
`SPOTS` table, the same numbers the shapes are built from, so a pin always sits
on the feature it names, and the demo rooms that stand for a place (main hall,
café counter, food stalls, ...) are linked to it through the same spots. Both
plans also carry decoration (trees, gazebos, benches, hedges, a fence, ...),
drawn as `prop` shapes and decorative line styles; a prop is never a place, and
`test_decor_keeps_clear_of_the_pins` keeps it at least 40 px from every pin
unless it is marked `under_pin` (a gazebo under its stall's pill). Today's
shifts at the pinned places are filled to fixed shares rather than at random
(`today_fill` in `seed.py`), so the map's staffing colours always show a mix of
full, partly staffed and short. Every other map edit (plans, markers,
locations, drawing shapes through `POST /venue-plans/{id}/shapes/batch`, and
removing a picture) stays allowed, so a manager can still try the editor. Only
the upload is refused. Saving a plan as a venue template and starting a plan
from one are allowed too: a template is owned by the guest account rather than
the event, so the purge removes it with the guest (see the teardown below), and
a guest's templates can carry no picture because the guest could never upload
one.

The inbox is the one part of the seed that exists because of a guard rather
than in spite of one. `NotificationService` drops a sandbox recipient *before*
it writes a row (see the invisibility table below), so nothing the visitor does
during the tour can ever reach their bell. `logic/sandbox/seed.py::_seed_notifications`
therefore writes the rows directly — never through the service, so no channel
is ever asked to send anything, and `channels_sent` stays empty because nothing
was sent. The shape is dictated by the screen: one entry under each of the four
classification tabs the notifications view offers, some read and some not so
the bell carries a badge, timestamps spread over minutes, hours and days, and
every `data` payload pointing at a row from this same demo so that clicking an
entry opens the task or booking it is about.

The caller picks a role, and that is the entire configuration of the demo:

| role | membership | what they see |
|---|---|---|
| `helper` | `member` | the volunteer side; every management screen is hidden by the router's `requiresEventManager` guard |
| `manager` | `owner` | the organiser side: task creation, shift generation, staffing, members, reporting |

The response is an ordinary `TokenResponse` with three extra fields. That
matters: **the demo is not a rendering mode**, it is a real session belonging to
an account that will shortly be deleted, which is what lets every screen in the
application work against it unmodified.

## Two flags, and why neither is redundant

`users.is_sandbox` sits next to the `sandbox|` subject prefix, and
`tasks.is_sandbox` sits next to `events.is_sandbox`. Both pairs look like
duplication and neither is.

**The prefix versus the column.** `sandbox|` joins `demo|` and `test|` as a
behavioural prefix — it is what the notification channels test, through the
shared `is_undeliverable()` predicate in
`app/logic/notifications/channels/base.py`. The column is what every `WHERE`
clause filters on, because a prefix match cannot use an index and the exclusion
has to live in the query, not in a post-filter a future caller could forget.

**`tasks.is_sandbox` versus `events.is_sandbox`.** `tasks.event_id` is
`ON DELETE SET NULL` and `Event.tasks` carries no `delete-orphan` cascade. A
task can therefore outlive its event with a NULL `event_id` — and a NULL matches
no `IN (...)`, which is the shape of every event-scoped filter in this
application. Such a row would be visible to everyone and manageable by nobody,
permanently. The denormalised flag survives the SET NULL.

## Teardown, and why the order is what it is

`app/logic/sandbox/cleanup.py::purge_sandbox` deletes children first, the event
next, and the guest accounts **last**. Getting this wrong does not raise; it
leaves the orphans described above.

```
1. booking_reminders, then bookings          — bookings.shift_id is SET NULL, so
2. shifts                                       a shift removed first strands the
                                                booking instead of removing it
3. shift_batches, then tasks (by event_id)   — never by cascade from the event
4. user_availabilities, event_memberships,
   then event_team_documents, event_team_checks,
   event_team_members, event_team_requirements,
   event_teams                               — after the tasks (tasks.team_id);
                                                leaf first, so a request's
                                                attached file visibly goes
5. venue_markers (by plan, then by location),
   venue_shapes, venue_plan_images,
   venue_plans, locations                    — all cascade from the event too;
                                                explicit so the drawing and any
                                                image visibly go, and the
                                                locations go after the rows
                                                pointing at them
6. events                                    — invitations and join requests cascade
7. venue_template_images, venue_templates
   (by guest), auth_sessions, then users     — last, always; notifications,
                                                avatars and tokens cascade from
                                                the guest. Templates belong to
                                                the account, not the event, so
                                                steps 1-6 never reach them; their
                                                FK cascades from the user too,
                                                deleted explicitly so they
                                                visibly go
```

The stored files (the seeded team document, a plan picture, an avatar) need no
step of their own. Every row that owns one carries a trigger that queues its
`storage_key` in `storage_deletions` when the row goes, whether it is deleted
here or by a cascade, inside the purge's own transaction. With the Postgres
storage backend the bytes go in that same statement; with S3 the purge wakes
`app/logic/storage_gc.py` after its commit, which deletes the objects. A purge
that rolls back queues nothing. See [`STORAGE.md`](STORAGE.md).

Two traps are worth stating explicitly:

- **Never delete the guest first.** `events.created_by_id` is `ON DELETE CASCADE`,
  so deleting the account removes the event underneath you at the database
  level, which fires the `tasks.event_id` SET NULL before any Python runs.
- **Never reuse `DELETE /users/{id}`.** It raises 409 `user.owns_content` for
  anyone who owns an event, which is every sandbox guest.

`purge_sandbox` is filtered on `is_sandbox` at every step, so calling it with a
real event's id does nothing rather than something catastrophic. It does not
commit; `api.deps.get_db` owns the transaction, so a purge that fails half way
rolls back whole rather than leaving the exact mess it exists to prevent.

## How the rows actually get reclaimed

There is no scheduler. `sweep_expired` runs at the top of **every** sandbox
creation, before the new one is counted. The only way to accumulate sandboxes is
to keep creating them, and creating one is precisely when the old ones are
collected. The sweep takes at most `limit` (default 20) per call, so a long-idle
deployment does not turn one visitor's click into a hundred cascading deletes.

Three fences sit in front of the endpoint, and they are not interchangeable:

| fence | where | what it stops |
|---|---|---|
| `SANDBOX_ENABLED` | `create_sandbox`, first line | anonymous writes on deployments that do not want them — 404, not a polite failure |
| `sandbox_limiter` (3/hour/IP) | the route | casual repeat clicking |
| `SANDBOX_MAX_ACTIVE` (25) | counted in SQL | everything else |

The rate limiter **cannot** be the ceiling. Its counters live in a single worker
process — the image runs `fastapi run --workers 4`, so it permits four times its
nominal rate — and it returns immediately when `TESTING` is set. The database
count is the only number that is actually true.

## Invisibility

A sandbox belongs to exactly one account. It is hidden from every other user
**including the platform superadmin**, which is deliberate: showing a stranger's
throwaway data in the admin screens offers no action worth taking on it, and the
`get_event_role` short-circuit that reports the superadmin as `owner` of
everything is exactly what would otherwise leak it.

This is the checklist. Each row is one guard, individually testable, covered in
`backend/tests/logic/test_sandbox_visibility.py`.

| where | guard |
|---|---|
| `crud/event.py::_apply_scope` | `all` excludes sandboxes; `discover`/`featured` exclude them too. `mine` is membership-scoped and so already correct for the guest's own demo. |
| `logic/permissions.py::require_event_visible` | 404 for a sandbox the caller did not create — placed **before** the role check, because that check reports the superadmin as owner |
| `crud/task.py::_apply_common_filters` | unrestricted (superadmin) queries exclude `Task.is_sandbox` |
| `crud/shift.py::_apply_event_scope` | shifts are scoped through their task; unrestricted still excludes sandboxes |
| `api/routes/shifts.py::get_shift` | ran no permission check at all before this feature; now resolves the task and runs the visibility gate |
| `api/routes/dashboard.py::_sidebar_events` | excludes sandboxes unless the viewer created them — `visible_event_ids` is `None` for the superadmin and so cannot do this job |
| `api/routes/reporting.py` | every query excludes sandbox tasks when there is no event filter, via `_non_sandbox_tasks()` |
| `api/routes/events.py::set_event_featured` | 422 `event.sandbox_not_featurable` |
| `api/routes/events.py` invitation creators | 403 `sandbox.invitations_disabled` — a guest is `owner`, so `require_event_role` would let them mail a real address |
| `api/routes/users.py::update_selected_event` | 404 for someone else's sandbox |
| `crud/user.py::search` | guests never appear in the superadmin user list |
| `logic/notifications/service.py` | a sandbox recipient gets **no notification row**, not merely no delivery — which is why the demo inbox is seeded directly instead |
| `logic/notifications/triggers.py::dispatch_task_published` | hard stop — that fan-out reaches every active account on the installation |
| `api/routes/auth.py` | change-password and resend-verification return 403 `sandbox.not_available` |
| `api/routes/venue_map.py` | plan image upload returns 403 `sandbox.upload_disabled`. Locations, plans, markers and shapes need no guard of their own: every one of them belongs to one event and is only reachable through `require_event_visible` |
| `api/routes/venue_templates.py` | venue templates belong to one account and answer 404 to everyone else, the superadmin included, so a guest's templates are invisible without a guard of their own |

Note what is deliberately **not** blocked: member role changes and join-request
decisions. The manager tour walks a visitor through both, and neither sends mail
to anyone real — the seeded requester is itself a guest with no email address.

## Endpoints

| Method | Path | Auth | Result |
|---|---|---|---|
| POST | `/auth/sandbox` | — | 201 `SandboxSessionResponse`, sets the refresh cookie |
| DELETE | `/auth/sandbox` | `CurrentUser` | 204, purges everything, clears the cookie |

**Both must stay in `app/api/routes/auth.py`.** The refresh cookie is scoped to
`REFRESH_COOKIE_PATH`, which is that router's prefix. Mounted anywhere else,
the endpoint would set a cookie the browser never returns to `/auth/refresh`,
and the demo would die at the first fifteen-minute token renewal — long after
the visitor stopped watching, with nothing in any log to explain it.

Error codes: `sandbox.disabled` (404), `sandbox.capacity_reached` (503),
`sandbox.forbidden` (403), `sandbox.not_available` (403),
`sandbox.invitations_disabled` (403), `sandbox.upload_disabled` (403),
`event.sandbox_not_featurable` (422). Each
needs an entry in the frontend's `errorCodes` i18n namespace; a code without one
renders as the raw backend string on screen.

## Settings

| setting | default | notes |
|---|---|---|
| `SANDBOX_ENABLED` | `true` | off means the endpoint 404s. The frontend reads the same value through `window.__APP_CONFIG__` so the landing page does not render a button that cannot work. |
| `SANDBOX_TTL_MINUTES` | `60` | how long a demo lives, and the only thing standing between this feature and a growing table |
| `SANDBOX_MAX_ACTIVE` | `25` | the real ceiling. Raise it for the E2E stack, which runs several Playwright workers at once. |

## What is deliberately not built

- **No conversion.** A visitor who decides to sign up gets a normal empty
  account; their demo data is thrown away. Migrating it would mean promoting a
  passwordless, address-less row into a real credential, which is a larger
  security surface than the feature is worth.
- **No sharing.** A sandbox is private to one session. Two people cannot look at
  the same demo.
- **No background scheduler.** See above — the sweep rides on creation, which is
  sufficient precisely because sandboxes only accumulate when people create them.
