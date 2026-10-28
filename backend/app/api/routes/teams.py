"""Teams inside an event, the requests to join them, and their checks.

Every route is nested under the event and looks the team up *through* that
event, so a team id from another event is a 404 here rather than a way across
tenancies.

Requirements and checks: a team can list requirements ("Extended police
certificate"). Approving a request — or placing someone directly — needs the
decider to tick each one (``team.checks_missing`` otherwise); a tick is stored
as a check record (who, when, issue date, expiry), never the evidence.

Documents: while a request is pending, the requester may attach one file per
requirement that ``accepts_document``, through a separate upload
(``PUT …/join/documents/{requirement_id}``) after the JSON join call. Keeping
it separate leaves joining a plain JSON request, lets a file be replaced or
removed before the decision, and means a failed upload never loses the
request. The file is readable by the team's managers and the requester only,
and deleted when the request is decided, withdrawn or the row goes away.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import NoReturn, cast

from fastapi import APIRouter, BackgroundTasks, Query, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DBDep
from app.api.files import serve_file
from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.crud.event_membership import event_membership as crud_membership
from app.crud.event_team import event_team as crud_team
from app.crud.user import user as crud_user
from app.logic.notifications.triggers import (
    dispatch_team_join_decided,
    dispatch_team_join_requested,
)
from app.logic.permissions import (
    can_manage_team,
    get_event_role,
    require_event_role,
    require_team_manager,
    role_at_least,
)
from app.logic.team_documents import (
    MAX_DOCUMENT_BYTES,
    DocumentError,
    content_disposition,
    prepare_document,
)
from app.logic.team_requirements import label_key
from app.logic.teams import (
    check_read,
    is_expired,
    needs_recheck,
    store_checks,
    validate_checks,
)
from app.models.event_team import (
    EventTeam,
    EventTeamCheck,
    EventTeamDocument,
    EventTeamMember,
    EventTeamRequirement,
)
from app.models.user import User
from app.schemas.event_team import (
    EventTeamCreate,
    EventTeamDecision,
    EventTeamJoin,
    EventTeamMemberAdd,
    EventTeamMemberRead,
    EventTeamMemberRoleUpdate,
    EventTeamRead,
    EventTeamUpdate,
    TeamCheckRead,
    TeamChecksUpdate,
    TeamDocumentRead,
    TeamMemberStatus,
    TeamRequirementRead,
    TeamRole,
    TeamTaskRead,
)

router = APIRouter(prefix="/events", tags=["teams"])


# --- Helpers ------------------------------------------------------------


async def _team_or_404(
    session: DBDep, *, event_id: uuid.UUID, team_id: uuid.UUID
) -> EventTeam:
    team = await crud_team.get_in_event(session, team_id=team_id, event_id=event_id)
    if team is None:
        raise_problem(404, code="team.not_found", detail="Team not found")
    return team


def _raise_name_taken() -> NoReturn:
    raise_problem(
        409,
        code="team.name_taken",
        detail="This event already has a team with that name",
    )


async def _ensure_name_free(
    session: DBDep,
    *,
    event_id: uuid.UUID,
    name: str,
    exclude_id: uuid.UUID | None = None,
) -> None:
    if await crud_team.get_by_name_ci(
        session, event_id=event_id, name=name, exclude_id=exclude_id
    ):
        _raise_name_taken()


def _refuse_open_team_with_requirements(
    requires_approval: bool, requirement_count: int
) -> None:
    """Requirements are ticked off when approving, so they need approval."""
    if requirement_count and not requires_approval:
        raise_problem(
            422,
            code="team.requirements_need_approval",
            detail="A team with requirements must approve who joins",
        )


def _doc_read(
    meta: tuple[uuid.UUID, str, str, int, dt.datetime],
) -> TeamDocumentRead:
    req_id, filename, content_type, size, uploaded = meta
    return TeamDocumentRead(
        requirement_id=req_id,
        filename=filename,
        content_type=content_type,
        size=size,
        uploaded_at=uploaded,
    )


async def decorate_teams(
    session: DBDep, user: User, event_id: uuid.UUID, teams: list[EventTeam]
) -> list[EventTeamRead]:
    """Attach the caller's view to a list of one event's teams.

    A constant number of queries, whatever the number of teams: the role is
    fetched once and the lead check reads the caller's own rows, which are
    loaded for every team together.
    """
    ids = [t.id for t in teams]
    role = await get_event_role(user, session, event_id)
    is_admin = role_at_least(role, "admin")
    today = dt.date.today()
    counts = await crud_team.counts(session, team_ids=ids)
    mine = await crud_team.rows_for_user(session, user_id=user.id, team_ids=ids)
    requirements = await crud_team.requirements_for_teams(session, team_ids=ids)
    team_tasks = await crud_team.tasks_by_team(
        session, team_ids=ids, published_only=not is_admin
    )
    open_shifts = await crud_team.open_shifts_by_task(
        session, team_ids=ids, published_only=not is_admin, today=today
    )
    leads = await crud_team.lead_names(session, team_ids=ids)
    pending_rows = [r.id for r in mine.values() if r.status == "pending"]
    approved_rows = [r.id for r in mine.values() if r.status == "approved"]
    my_docs = await crud_team.document_meta_for_members(
        session, member_ids=pending_rows
    )
    my_checks = await crud_team.checks_for_members(session, member_ids=approved_rows)

    out: list[EventTeamRead] = []
    for team in teams:
        row = mine.get(team.id)
        reqs = requirements.get(team.id, [])
        manage = is_admin or (
            role is not None
            and row is not None
            and row.status == "approved"
            and row.role == "lead"
        )
        recheck = False
        if row is not None and row.status == "approved" and reqs:
            checks = [check_read(c, r, today) for c, r in my_checks.get(row.id, [])]
            recheck = needs_recheck(reqs, checks)
        tasks = [
            TeamTaskRead(
                id=task_id, name=name, open_shift_count=open_shifts.get(task_id, 0)
            )
            for task_id, name in team_tasks.get(team.id, [])
        ]
        out.append(
            EventTeamRead(
                **team.model_dump(),
                requirements=[TeamRequirementRead.model_validate(r) for r in reqs],
                member_count=counts[team.id]["approved"],
                pending_count=counts[team.id]["pending"] if manage else 0,
                task_count=counts[team.id]["tasks"],
                tasks=tasks,
                open_shift_count=sum(t.open_shift_count for t in tasks),
                lead_names=leads.get(team.id, []),
                my_status=cast(TeamMemberStatus, row.status) if row else None,
                my_role=cast(TeamRole, row.role) if row else None,
                my_requested_at=row.created_at if row else None,
                my_documents=[_doc_read(m) for m in my_docs.get(row.id, [])]
                if row
                else [],
                my_needs_recheck=recheck,
                can_manage=manage,
            )
        )
    return out


async def _decorate_one(session: DBDep, user: User, team: EventTeam) -> EventTeamRead:
    return (await decorate_teams(session, user, team.event_id, [team]))[0]


async def member_reads(
    session: DBDep,
    *,
    event_id: uuid.UUID,
    teams: Sequence[EventTeam],
    rows: Sequence[tuple[EventTeamMember, User | None]],
) -> list[EventTeamMemberRead]:
    """Roster or request rows with checks, documents and request context.

    Pending rows also get what the review needs: the documents attached,
    valid checks of the same requirement (by label) in another team of this
    event, the requester's other teams and their bookings in the event. Every
    piece is one query for all rows.
    """
    today = dt.date.today()
    team_by_id = {t.id: t for t in teams}
    requirements = await crud_team.requirements_for_teams(
        session, team_ids=list(team_by_id)
    )
    member_ids = [m.id for m, _ in rows]
    pending = [(m, u) for m, u in rows if m.status == "pending"]
    pending_users = list({m.user_id for m, _ in pending})
    checks = await crud_team.checks_for_members(session, member_ids=member_ids)
    docs = await crud_team.document_meta_for_members(
        session, member_ids=[m.id for m, _ in pending]
    )
    elsewhere = await crud_team.checks_in_event(
        session, event_id=event_id, user_ids=pending_users
    )
    other_teams = await crud_team.other_team_names(
        session, event_id=event_id, user_ids=pending_users
    )
    bookings = await crud_team.booked_shift_counts(
        session, event_id=event_id, user_ids=pending_users
    )

    out: list[EventTeamMemberRead] = []
    for member, user in rows:
        team = team_by_id.get(member.team_id)
        reqs = requirements.get(member.team_id, [])
        own = [check_read(c, r, today) for c, r in checks.get(member.id, [])]
        read = EventTeamMemberRead(
            **member.model_dump(),
            team_name=team.name if team else None,
            user_name=user.name if user else None,
            user_email=user.email if user else None,
            user_avatar_etag=user.avatar_etag if user else None,
            checks=own,
            needs_recheck=member.status == "approved" and needs_recheck(reqs, own),
        )
        if member.status == "pending":
            read.documents = [_doc_read(d) for d in docs.get(member.id, [])]
            read.reusable_checks = _reusable(
                reqs,
                [
                    (check, req, name)
                    for uid, check, req, team_id, name in elsewhere
                    if uid == member.user_id and team_id != member.team_id
                ],
                today,
            )
            read.other_team_names = [
                name
                for team_id, name in other_teams.get(member.user_id, [])
                if team_id != member.team_id
            ]
            read.booked_shift_count = bookings.get(member.user_id, 0)
        out.append(read)
    return out


def _reusable(
    requirements: Sequence[EventTeamRequirement],
    candidates: Sequence[tuple[EventTeamCheck, EventTeamRequirement, str]],
    today: dt.date,
) -> list[TeamCheckRead]:
    """For each requirement, the best valid check with the same label elsewhere.

    Reported against *this* team's requirement id, so the review dialog can
    show it as already checked and prefill the issue date. The latest expiry
    wins; a check that never expires beats one that does.
    """
    out: list[TeamCheckRead] = []
    for req in requirements:
        best: TeamCheckRead | None = None
        for check, source_req, team_name in candidates:
            if label_key(source_req.label) != label_key(req.label):
                continue
            if is_expired(check, today):
                continue
            read = check_read(check, req, today, source_team_name=team_name)
            if best is None or (
                best.expires_on is not None
                and (read.expires_on is None or read.expires_on > best.expires_on)
            ):
                best = read
        if best is not None:
            out.append(best)
    return out


async def _one_member_read(
    session: DBDep, team: EventTeam, member: EventTeamMember
) -> EventTeamMemberRead:
    user = await crud_user.get(session, id=member.user_id)
    return (
        await member_reads(
            session, event_id=team.event_id, teams=[team], rows=[(member, user)]
        )
    )[0]


# --- Teams --------------------------------------------------------------


@router.get("/{event_id}/teams", response_model=list[EventTeamRead])
async def list_teams(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[EventTeamRead]:
    """The event's teams, with the caller's own standing in each."""
    await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event_id, minimum="member")
    teams = await crud_team.list_for_event(session, event_id=event_id)
    return await decorate_teams(session, current_user, event_id, teams)


@router.post("/{event_id}/teams", response_model=EventTeamRead, status_code=201)
async def create_team(
    event_id: uuid.UUID,
    body: EventTeamCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> EventTeamRead:
    """Create a team, with its requirements. Names are unique per event."""
    await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event_id, minimum="admin")
    _refuse_open_team_with_requirements(body.requires_approval, len(body.requirements))
    await _ensure_name_free(session, event_id=event_id, name=body.name)
    try:
        # A savepoint, so losing a race on the unique index (after the
        # pre-check above passed) leaves the transaction usable for the 409.
        async with session.begin_nested():
            team = await crud_team.create(session, event_id=event_id, data=body)
    except IntegrityError:
        _raise_name_taken()
    return await _decorate_one(session, current_user, team)


@router.patch("/{event_id}/teams/{team_id}", response_model=EventTeamRead)
async def update_team(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    body: EventTeamUpdate,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EventTeamRead:
    """Edit a team. Event admins only: a lead runs the roster, not the rules.

    Turning approval off approves every waiting request: nobody is left to
    decide them, and they asked for something that is now open.
    """
    await require_event_role(current_user, session, event_id, minimum="admin")
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)
    was_restricted = team.requires_approval
    requires_approval = (
        body.requires_approval
        if body.requires_approval is not None
        else team.requires_approval
    )
    requirement_count = (
        len(body.requirements)
        if body.requirements is not None
        else len(await crud_team.requirements(session, team_id=team.id))
    )
    _refuse_open_team_with_requirements(requires_approval, requirement_count)
    if body.name is not None:
        await _ensure_name_free(
            session, event_id=event_id, name=body.name, exclude_id=team.id
        )
    try:
        async with session.begin_nested():
            team = await crud_team.update(session, team=team, data=body)
    except IntegrityError:
        _raise_name_taken()
    except LookupError:
        raise_problem(
            422,
            code="team.requirement_not_found",
            detail="A requirement in the list does not belong to this team",
        )
    if was_restricted and not team.requires_approval:
        waiting = await crud_team.list_members(
            session, team_ids=[team.id], status="pending"
        )
        await crud_team.approve_all_pending(
            session, team_id=team.id, decided_by=current_user
        )
        for member, _user in waiting:
            background_tasks.add_task(
                dispatch_team_join_decided,
                team_id=team.id,
                user_id=member.user_id,
                approved=True,
            )
    return await _decorate_one(session, current_user, team)


@router.delete("/{event_id}/teams/{team_id}", status_code=204)
async def delete_team(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Delete a team. Tasks that required it become open to the whole event."""
    await require_event_role(current_user, session, event_id, minimum="admin")
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)
    await session.delete(team)
    await session.flush()


@router.get("/{event_id}/teams/requests", response_model=list[EventTeamMemberRead])
async def list_team_requests(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[EventTeamMemberRead]:
    """Every waiting request the caller may decide, across the event's teams.

    All of them for an event admin, those of the teams they lead for anyone
    else — empty for a plain member. Oldest first.
    """
    await crud_event.get(session, event_id, raise_404_error=True)
    role = await require_event_role(current_user, session, event_id, minimum="member")
    teams = await crud_team.list_for_event(session, event_id=event_id)
    if not role_at_least(role, "admin"):
        mine = await crud_team.rows_for_user(
            session, user_id=current_user.id, team_ids=[t.id for t in teams]
        )
        teams = [
            t
            for t in teams
            if (row := mine.get(t.id)) is not None
            and row.status == "approved"
            and row.role == "lead"
        ]
    rows = await crud_team.list_members(
        session, team_ids=[t.id for t in teams], status="pending"
    )
    return await member_reads(session, event_id=event_id, teams=teams, rows=rows)


# --- Joining ------------------------------------------------------------


@router.post(
    "/{event_id}/teams/{team_id}/join",
    response_model=EventTeamMemberRead,
    status_code=201,
)
async def join_team(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    body: EventTeamJoin,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EventTeamMemberRead:
    """Join an open team, or ask to join a restricted one.

    Files for the team's requirements are attached afterwards, one upload per
    requirement (``PUT …/join/documents/{requirement_id}``).
    """
    await require_event_role(current_user, session, event_id, minimum="member")
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)
    existing = await crud_team.get_member(
        session, team_id=team.id, user_id=current_user.id
    )
    if existing and existing.status == "approved":
        raise_problem(
            409, code="team.already_member", detail="You are already in this team"
        )
    # A request left over from when the team still needed approval is simply
    # let through below, instead of being stuck with no one to decide it.
    if existing and existing.status == "pending" and team.requires_approval:
        raise_problem(
            409,
            code="team.request_pending",
            detail="Your request to join this team is still waiting for a decision",
        )
    try:
        async with session.begin_nested():
            member = await crud_team.request(
                session, team=team, user_id=current_user.id, message=body.message
            )
    except IntegrityError:
        # Two clicks racing to insert the same row: the other one won.
        raise_problem(
            409,
            code="team.request_pending",
            detail="Your request to join this team is still waiting for a decision",
        )
    if member.status == "pending":
        # Joining an open team is done on the spot; only a waiting request
        # needs someone to look at it.
        background_tasks.add_task(
            dispatch_team_join_requested, team_id=team.id, user_id=current_user.id
        )
    return await _one_member_read(session, team, member)


@router.delete("/{event_id}/teams/{team_id}/join", status_code=204)
async def leave_team(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Leave a team, or withdraw a pending request.

    Existing bookings are kept: leaving a team stops new bookings, it does not
    pull someone off shifts they already committed to. Checks and attached
    files are deleted with the row.
    """
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)
    member = await crud_team.get_member(
        session, team_id=team.id, user_id=current_user.id
    )
    if member is None:
        raise_problem(
            404, code="team.member_not_found", detail="You are not in this team"
        )
    await crud_team.remove(session, member=member)


async def _own_pending_request(
    session: DBDep,
    user: User,
    *,
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    requirement_id: uuid.UUID,
) -> tuple[EventTeam, EventTeamMember, EventTeamRequirement]:
    await require_event_role(user, session, event_id, minimum="member")
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)
    member = await crud_team.get_member(session, team_id=team.id, user_id=user.id)
    if member is None or member.status != "pending":
        raise_problem(
            404,
            code="team.request_not_found",
            detail="You have no open request for this team",
        )
    requirement = next(
        (
            r
            for r in await crud_team.requirements(session, team_id=team.id)
            if r.id == requirement_id
        ),
        None,
    )
    if requirement is None:
        raise_problem(
            404,
            code="team.requirement_not_found",
            detail="This team has no such requirement",
        )
    return team, member, requirement


@router.put(
    "/{event_id}/teams/{team_id}/join/documents/{requirement_id}",
    response_model=TeamDocumentRead,
)
async def upload_team_document(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    requirement_id: uuid.UUID,
    file: UploadFile,
    session: DBDep,
    current_user: CurrentUser,
) -> TeamDocumentRead:
    """Attach a file to your pending request, for one requirement.

    PDF, PNG, JPEG or WebP, at most 5 MB; a second upload replaces the first.
    Seen only by the team's leads, the event admins and you, and deleted as
    soon as your request is decided.
    """
    _, member, requirement = await _own_pending_request(
        session,
        current_user,
        event_id=event_id,
        team_id=team_id,
        requirement_id=requirement_id,
    )
    if not requirement.accepts_document:
        raise_problem(
            422,
            code="team.document_not_accepted",
            detail="This requirement does not take a file",
        )
    event = await crud_event.get(session, event_id, raise_404_error=True)
    if event.is_sandbox or current_user.is_sandbox:
        raise_problem(
            403,
            code="sandbox.upload_disabled",
            detail="Files cannot be uploaded in a demo event",
        )
    if file.size is not None and file.size > MAX_DOCUMENT_BYTES:
        raise_problem(
            422,
            code="team.document_too_large",
            detail="The file is larger than 5 MB",
        )
    # Read one byte past the limit: enough to know it is too big without
    # holding an arbitrarily large body in memory.
    raw = await file.read(MAX_DOCUMENT_BYTES + 1)
    try:
        prepared = await run_in_threadpool(prepare_document, raw, file.filename)
    except DocumentError as exc:
        raise_problem(422, code=exc.code, detail=exc.detail)

    # Stored once, before the row: a retry below reuses the same file.
    storage_key = await crud_team.store_document_file(
        session, data=prepared.data, content_type=prepared.content_type
    )

    async def store() -> EventTeamDocument:
        return await crud_team.upsert_document(
            session,
            member_id=member.id,
            requirement_id=requirement.id,
            filename=prepared.filename,
            content_type=prepared.content_type,
            size=len(prepared.data),
            storage_key=storage_key,
        )

    try:
        # A savepoint: two uploads for the same check at once (a double
        # submit, a retry) race to insert the first file. The loser lands
        # here and replaces the winner's file, as a later upload would.
        async with session.begin_nested():
            doc = await store()
    except IntegrityError:
        doc = await store()
    return TeamDocumentRead(
        requirement_id=doc.requirement_id,
        filename=doc.filename,
        content_type=doc.content_type,
        size=doc.size,
        uploaded_at=doc.created_at,
    )


@router.delete(
    "/{event_id}/teams/{team_id}/join/documents/{requirement_id}",
    status_code=204,
)
async def delete_team_document(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    requirement_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Take a file back off your pending request."""
    _, member, requirement = await _own_pending_request(
        session,
        current_user,
        event_id=event_id,
        team_id=team_id,
        requirement_id=requirement_id,
    )
    doc = await crud_team.get_document(
        session, member_id=member.id, requirement_id=requirement.id
    )
    if doc is None:
        raise_problem(
            404, code="team.document_not_found", detail="No file attached here"
        )
    await crud_team.delete_document(session, document=doc)


@router.get(
    "/{event_id}/teams/{team_id}/members/{user_id}/documents/{requirement_id}",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/pdf": {},
                "image/webp": {},
            },
            "description": "The attached file",
        },
    },
)
async def get_team_document(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    requirement_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> Response:
    """A file attached to a pending request.

    For the team's managers and the requester. Anyone else gets the same 404
    as for a file that does not exist, so a request cannot be probed for.
    Never cached: the file is deleted once the request is decided.
    """
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)

    def not_found() -> NoReturn:
        raise_problem(404, code="team.document_not_found", detail="File not found")

    if user_id != current_user.id:
        role = await get_event_role(current_user, session, event_id)
        if role is None:
            not_found()
        if not await can_manage_team(current_user, session, team):
            not_found()
    member = await crud_team.get_member(session, team_id=team.id, user_id=user_id)
    if member is None:
        not_found()
    doc = await crud_team.get_document(
        session, member_id=member.id, requirement_id=requirement_id
    )
    if doc is None:
        not_found()
    # Streamed, never a link: a signed link works for whoever holds it, and
    # these documents are for the team's managers and the requester only.
    served = await serve_file(
        session,
        doc.storage_key,
        media_type=doc.content_type,
        headers={
            "Content-Disposition": content_disposition(doc.filename),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
        link=False,
    )
    if served is None:
        not_found()
    return served


# --- Roster (leads and event admins) -------------------------------------


@router.get(
    "/{event_id}/teams/{team_id}/members",
    response_model=list[EventTeamMemberRead],
)
async def list_team_members(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    status: TeamMemberStatus | None = Query(default=None),
) -> list[EventTeamMemberRead]:
    """The roster and requests, with checks. ``status`` narrows the list."""
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)
    await require_team_manager(current_user, session, team)
    rows = await crud_team.list_members(session, team_ids=[team.id], status=status)
    return await member_reads(session, event_id=event_id, teams=[team], rows=rows)


@router.get(
    "/{event_id}/teams/{team_id}/members/{user_id}/reusable-checks",
    response_model=list[TeamCheckRead],
)
async def list_reusable_checks(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[TeamCheckRead]:
    """Valid checks this person already has in another team of this event.

    For adding someone straight into a team with requirements, where no
    request row carries ``reusable_checks``: the dialog shows them as already
    checked and fills in the issue date. Never looks beyond this event.
    """
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)
    await require_team_manager(current_user, session, team)
    reqs = await crud_team.requirements(session, team_id=team.id)
    if not reqs:
        return []
    elsewhere = await crud_team.checks_in_event(
        session, event_id=event_id, user_ids=[user_id], exclude_team_id=team.id
    )
    return _reusable(
        reqs,
        [(check, req, name) for _, check, req, _, name in elsewhere],
        dt.date.today(),
    )


@router.post(
    "/{event_id}/teams/{team_id}/members",
    response_model=EventTeamMemberRead,
    status_code=201,
)
async def add_team_member(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    body: EventTeamMemberAdd,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EventTeamMemberRead:
    """Put an event member straight into the team (approving any request).

    Leads may add members; only event admins may appoint leads. Someone
    already in the team is a 409 — changing a role is ``PATCH
    …/members/{user_id}``, which is for event admins, so a lead cannot demote
    a co-lead through here. A team with requirements needs the same checks as
    approving a request.
    """
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)
    await require_team_manager(current_user, session, team)
    if body.role == "lead":
        await require_event_role(current_user, session, event_id, minimum="admin")
    if not await crud_membership.get(session, user_id=body.user_id, event_id=event_id):
        raise_problem(
            422,
            code="team.not_event_member",
            detail="Only members of this event can be added to its teams",
        )
    existing = await crud_team.get_member(
        session, team_id=team.id, user_id=body.user_id
    )
    if existing is not None and existing.status == "approved":
        raise_problem(
            409,
            code="team.already_member",
            detail="This person is already in the team",
        )
    # Read before ``place``: it updates this very row in place.
    was_waiting = existing is not None and existing.status == "pending"
    checks = validate_checks(
        await crud_team.requirements(session, team_id=team.id),
        body.checks,
        require_all=True,
    )
    try:
        async with session.begin_nested():
            member = await crud_team.place(
                session,
                team_id=team.id,
                user_id=body.user_id,
                role=body.role,
                decided_by=current_user,
            )
    except IntegrityError:
        raise_problem(
            409,
            code="team.already_member",
            detail="This person is already in the team",
        )
    await store_checks(
        session, member_id=member.id, checks=checks, checked_by=current_user
    )
    if was_waiting:
        # Placing someone who had asked is approving their request.
        background_tasks.add_task(
            dispatch_team_join_decided,
            team_id=team.id,
            user_id=body.user_id,
            approved=True,
        )
    return await _one_member_read(session, team, member)


@router.patch(
    "/{event_id}/teams/{team_id}/members/{user_id}",
    response_model=EventTeamMemberRead,
)
async def update_team_member_role(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    body: EventTeamMemberRoleUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> EventTeamMemberRead:
    """Appoint or step down a lead. Event admins only."""
    await require_event_role(current_user, session, event_id, minimum="admin")
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)
    member = await crud_team.get_member(session, team_id=team.id, user_id=user_id)
    if member is None or member.status != "approved":
        raise_problem(
            404,
            code="team.member_not_found",
            detail="That user is not an approved member of this team",
        )
    member = await crud_team.set_role(session, member=member, role=body.role)
    return await _one_member_read(session, team, member)


@router.post(
    "/{event_id}/teams/{team_id}/members/{user_id}/decide",
    response_model=EventTeamMemberRead,
)
async def decide_team_request(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    body: EventTeamDecision,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EventTeamMemberRead:
    """Approve or decline someone's request to join the team.

    Approving a team with requirements needs ``checks`` with one entry per
    requirement (and its issue date where asked): ``422 team.checks_missing``
    otherwise. Either way any attached files are deleted.
    """
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)
    await require_team_manager(current_user, session, team)
    member = await crud_team.get_member(session, team_id=team.id, user_id=user_id)
    if member is None:
        raise_problem(
            404, code="team.request_not_found", detail="Team request not found"
        )
    if member.status != "pending":
        raise_problem(
            409,
            code="team.request_decided",
            detail="That request has already been decided",
        )
    checks = (
        validate_checks(
            await crud_team.requirements(session, team_id=team.id),
            body.checks,
            require_all=True,
        )
        if body.approve
        else []
    )
    decided = await crud_team.decide(
        session, member=member, approve=body.approve, decided_by=current_user
    )
    await store_checks(
        session, member_id=decided.id, checks=checks, checked_by=current_user
    )
    background_tasks.add_task(
        dispatch_team_join_decided,
        team_id=team.id,
        user_id=decided.user_id,
        approved=body.approve,
    )
    return await _one_member_read(session, team, decided)


@router.put(
    "/{event_id}/teams/{team_id}/members/{user_id}/checks",
    response_model=EventTeamMemberRead,
)
async def record_team_checks(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    body: TeamChecksUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> EventTeamMemberRead:
    """Record or renew checks for someone already in the team.

    How "needs a new check" is cleared: after an expiry, or for a requirement
    added after the member joined. Only the listed requirements change.
    """
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)
    await require_team_manager(current_user, session, team)
    member = await crud_team.get_member(session, team_id=team.id, user_id=user_id)
    if member is None or member.status != "approved":
        raise_problem(
            404,
            code="team.member_not_found",
            detail="That user is not an approved member of this team",
        )
    checks = validate_checks(
        await crud_team.requirements(session, team_id=team.id),
        body.checks,
        require_all=False,
    )
    await store_checks(
        session, member_id=member.id, checks=checks, checked_by=current_user
    )
    return await _one_member_read(session, team, member)


@router.delete("/{event_id}/teams/{team_id}/members/{user_id}", status_code=204)
async def remove_team_member(
    event_id: uuid.UUID,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Take someone out of the team. A lead can only be removed by an admin.

    Their checks and any attached files go with the row.
    """
    team = await _team_or_404(session, event_id=event_id, team_id=team_id)
    await require_team_manager(current_user, session, team)
    member = await crud_team.get_member(session, team_id=team.id, user_id=user_id)
    if member is None:
        raise_problem(
            404, code="team.member_not_found", detail="That user is not in this team"
        )
    if member.role == "lead" and member.user_id != current_user.id:
        await require_event_role(current_user, session, event_id, minimum="admin")
    await crud_team.remove(session, member=member)
