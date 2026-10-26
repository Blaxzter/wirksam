# Event teams: restricted teams that gate booking (#179)

## Problem

Any event member can book any shift. Some shifts need someone trusted or
qualified (cash desk, kitchen, driving, sound desk, childcare), and the only
grouping we had was the free-text `category`.

## Teams or skill tags?

One model covers both. A **team** belongs to one event and has a name, a
description, a contact line and `requires_approval`:

- `requires_approval = true` is a *restricted* team (Engelsystem's
  `restricted` angel type). Joining opens a request; a team lead or an event
  admin approves it.
- `requires_approval = false` is a self-declared skill tag. Joining is
  immediate.

A task names at most one team (`tasks.team_id`). If it does, booking any of
its shifts needs an **approved** membership of that team, or an event admin
role. Without a team nothing changes.

Skill tags as a separate concept (many tags per user, many per task, AND/OR
matching) were not built: one team per task covers every example in the issue,
and a second mechanism next to teams would make "why can't I book this?"
harder to answer.

## Requirements and checks

Some teams need proof before someone joins: an extended police certificate
for childcare (§72a SGB VIII), a first-aid course for the medics, a class B
licence for the drivers. A restricted team can list up to ten
**requirements**:

| Field | Meaning |
|---|---|
| `label` | Free text, e.g. "Erweitertes Führungszeugnis" |
| `description` | Optional note for the requester and the decider |
| `ask_issue_date` | The decider records the document's issue date |
| `valid_for_years` | The check expires that many years after the issue date (or after the day of the check, without one) |
| `accepts_document` | The requester may attach one file to their request |

The team form offers presets (labels in en and de): the police certificate
(issue date, 5 years, **no file**, with a "don't keep a copy" note), a
first-aid course (issue date, 2 years, file allowed) and a class B driving
licence (no date, no file), plus free text. Requirements only make sense with
approval, so a team with requirements cannot be open
(`422 team.requirements_need_approval`).

**Approving** a request — or placing someone directly — needs one tick per
requirement, with `issued_on` where the requirement asks for it. The server
enforces it (`422 team.checks_missing`, naming the missing requirement ids)
and refuses an issue date in the future or one so old the check would
already have expired. Each tick becomes an `event_team_checks` row: the
requirement, the member row, `checked_by_name` (denormalised, see below),
`checked_at`, `issued_on` and the computed `expires_on`. That is everything we
keep. **We never store a copy of a police certificate.**

**Reuse.** A valid check for a requirement with the same label (compared
ignoring case and spacing) by the same person in another team of the *same
event* is returned with the request as `reusable_checks`, so the review dialog
can show "already checked" and prefill the date. The decider still ticks it;
nothing is approved implicitly. Checks are never reused across events — a
certificate seen by one organiser has not been seen by the next, so cloning an
event copies requirements and carried members but no checks.

**Expiry** does not revoke access. A member whose check has expired, or who
joined before a requirement was added, reads `needs_recheck: true` in the
roster (and `my_needs_recheck` on their own team card); a manager renews it
with `PUT …/members/{user_id}/checks`. Pulling someone off a team at midnight
because a date passed helps nobody.

## Documents

There is no file server in the stack, so attached files live in Postgres
(`event_team_documents`, like avatars and venue plans) and are kept as short
as possible:

- Upload is a separate call after the JSON join request:
  `PUT /events/{id}/teams/{team_id}/join/documents/{requirement_id}`
  (multipart, one file per requirement, a second upload replaces the first;
  `DELETE` takes it back). Joining stays a plain JSON call, and a failed
  upload never loses the request.
- Only for a pending request and a requirement with `accepts_document`.
  PDF, PNG, JPEG or WebP by magic bytes, at most 5 MB. Photos are re-encoded
  to WebP, which drops their EXIF data. Refused in a demo event.
- Readable at `GET …/members/{user_id}/documents/{requirement_id}` by the
  team's managers and the requester; everyone else gets the same 404 as for a
  missing file. Served `inline`, `nosniff`, `private, no-store`.
- **Deleted** when the request is approved or declined, when it is withdrawn,
  and with the member row (leaving or being removed from the team or the
  event, account deletion). The check record is what remains.

## Data

| Table | Notes |
|---|---|
| `event_teams` | `event_id` CASCADE, unique index on `(event_id, lower(name))` |
| `event_team_requirements` | `team_id` CASCADE, ordered by `position` |
| `event_team_members` | `team_id` CASCADE, `user_id` CASCADE, `status` pending/approved/declined, `role` member/lead, `decided_by_id` **without a foreign key** plus `decided_by_name` |
| `event_team_checks` | `member_id` CASCADE, `requirement_id` CASCADE, unique per pair, `checked_by_id` (no FK) + `checked_by_name` |
| `event_team_documents` | `member_id` CASCADE, `requirement_id` CASCADE, unique per pair, bytes inline |
| `tasks.team_id` | SET NULL, **deferrable initially deferred**, like `tasks.location_id`: a user delete cascades to the event, and the events->tasks SET NULL would otherwise re-check `team_id` against a team the same statement removed |

`decided_by_id` and `checked_by_id` deliberately have no foreign key. A
CASCADE would delete a membership when the person who approved it deletes
their account; SET NULL is the trap described in `app/models/CLAUDE.md`. The
name is kept for display and the id is only ever compared.

Requests and memberships share a row, unlike `event_join_requests`. A team
always sits inside an event the user is already in, so a pending row grants
nothing on its own; every access decision filters on `status = 'approved'`.

## Who can do what

| Action | Who |
|---|---|
| List teams, join / ask to join, leave, attach files to their own request | event members |
| Create, edit, delete a team and its requirements | event admins |
| See the roster and requests, decide, add or remove members, record checks, read attached files | the team's leads and event admins |
| Appoint or remove a lead, change a role | event admins |
| Book a gated task's shifts | approved team members and event admins |

The gates live in `app/logic/permissions.py` next to the event ones:
`require_team_manager` and `require_team_for_booking`. Booking a gated shift
without access answers `403 booking.team_required` with `team_id` and
`team_name` in the problem body. Adding someone who is already approved is
`409 team.already_member`, so a lead cannot change a co-lead's role through
the add endpoint.

## What the API tells the client

- `EventRead.team_count` (members only) and `pending_team_request_count`
  (requests the caller may decide) drive the Teams sidebar / More entry and
  its badge.
- `GET /events/{id}/teams/requests`: every pending request the caller may
  decide, across teams, with documents, reusable checks, the requester's other
  teams and their bookings in the event.
- `EventTeamRead`: requirements, task names, open shifts, lead names, the
  caller's status, request date, attached files and recheck flag.
- `ShiftRead`, `LocationShiftRead`, `TaskRead` and the task feed carry
  `team_name`, `team_requires_approval`, `my_team_status` and
  `locked_by_team` (shifts also `event_id`), so a locked task can offer
  "Join" or "Ask to join" in place. `GET /tasks/feed?bookable_only=true`
  leaves out tasks the caller cannot book.

## Side effects handled

- **Leaving or being removed from an event** deletes the user's team rows (and
  with them checks and files), so re-joining the event later does not silently
  restore approved access.
- **Moving a task to another event** clears `team_id` (teams do not cross
  events); setting a team from another event is `422 task.team_not_in_event`.
- **Deleting a team** opens its tasks to the whole event again (SET NULL).
- **Turning approval off** approves every waiting request; a pending row on an
  open team is approved when its owner joins again.
- **Cloning an event** copies its teams and requirements and remaps `team_id`
  on cloned tasks. With `copy_members`, approved memberships of carried-over
  members come along (without checks); pending requests never do.
- **Leaving a team** keeps existing bookings: it stops new ones only.
- **Re-confirming a cancelled booking** through `PATCH /bookings/{id}` is
  refused (`422 booking.rebook_required`); `POST /bookings/` reactivates it
  with every check, the team gate included.
- **Sandbox cleanup** deletes teams explicitly after the tasks.

## UI

- A **Teams** page on its own route (`teams/:eventId?`), in the sidebar after
  Availability and in the phone More sheet, shown when the event has teams or
  the viewer can manage it. Managers see the waiting requests at the top; a
  request with requirements opens a review dialog (sheet on phones) with a
  tick and issue date per requirement and any attached file next to it.
- Task create / edit: "Who can book" picker.
- Tasks view, task page, shift dialog and venue map sheet show the lock and
  join in place.

## Not done (follow-ups)

- `shift_self_signup = false` (only leads/admins place people into shifts).
- Qualifications stored on the user profile across events.
- A join link / QR code per team.
