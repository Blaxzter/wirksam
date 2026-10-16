import csv
import datetime as dt
import io
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.crud.event_membership import event_membership as crud_membership
from app.crud.user import user as crud_user
from app.crud.work_log import work_log as crud_work_log
from app.logic.permissions import require_event_role, require_event_visible
from app.logic.work_hours import event_hours, volunteer_hours
from app.models.event import Event
from app.models.user import User
from app.models.work_log import WorkLog
from app.schemas.work_hours import (
    VolunteerHours,
    VolunteerHoursDetail,
    WorkLogCreate,
    WorkLogRead,
    WorkLogUpdate,
)

router = APIRouter(prefix="/events", tags=["work-hours"])


async def _event_for(session: AsyncSession, user: User, event_id: uuid.UUID) -> Event:
    # Visibility first: it 404s a sandbox demo for everyone but its guest,
    # which require_event_role alone would let the superadmin through.
    event = await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_visible(user, session, event)
    return event


@router.get("/{event_id}/hours", response_model=list[VolunteerHours])
async def list_event_hours(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[VolunteerHours]:
    """Worked hours for every volunteer in the event. Event admins only."""
    await _event_for(session, current_user, event_id)
    await require_event_role(current_user, session, event_id, minimum="admin")
    return await event_hours(session, event_id)


@router.get("/{event_id}/hours/export")
async def export_event_hours(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> StreamingResponse:
    """The same list as CSV, for certificates and thank-you letters."""
    event = await _event_for(session, current_user, event_id)
    await require_event_role(current_user, session, event_id, minimum="admin")
    rows = await event_hours(session, event_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Volunteer Name",
            "Volunteer Email",
            "Role",
            "Shifts Worked",
            "Shift Hours",
            "Manual Hours",
            "Total Hours",
            "Upcoming Shifts",
            "Upcoming Hours",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r.name or "",
                r.email or "",
                r.role or "",
                r.shift_count,
                _hours(r.shift_minutes),
                _hours(r.manual_minutes),
                _hours(r.total_minutes),
                r.upcoming_shift_count,
                _hours(r.upcoming_shift_minutes),
            ]
        )

    filename = f"hours-{event.start_date.isoformat()}.csv"
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{event_id}/hours/{user_id}", response_model=VolunteerHoursDetail)
async def get_volunteer_hours(
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> VolunteerHoursDetail:
    """One volunteer's hours with the shifts and entries behind them.

    Anyone in the event may read their own; reading someone else's needs admin.
    """
    await _event_for(session, current_user, event_id)
    is_self = user_id == current_user.id
    await require_event_role(
        current_user, session, event_id, minimum="member" if is_self else "admin"
    )
    user = (
        current_user
        if is_self
        else await crud_user.get(session, id=user_id, raise_404_error=True)
    )
    return await volunteer_hours(session, event_id, user)


@router.post("/{event_id}/work-logs", response_model=WorkLogRead, status_code=201)
async def create_work_log(
    event_id: uuid.UUID,
    body: WorkLogCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> WorkLog:
    """Credit a volunteer with hours no shift covers. Event admins only."""
    await _event_for(session, current_user, event_id)
    await require_event_role(current_user, session, event_id, minimum="admin")

    if not await crud_membership.get(session, user_id=body.user_id, event_id=event_id):
        raise_problem(
            404,
            code="event.member_not_found",
            detail="That user is not a member of this event",
        )

    entry = WorkLog(
        event_id=event_id,
        user_id=body.user_id,
        date=body.date,
        minutes=body.minutes,
        description=body.description.strip(),
        created_by_id=current_user.id,
        created_by_name=current_user.name or current_user.email,
    )
    session.add(entry)
    await session.flush()
    await session.refresh(entry)
    return entry


@router.patch("/{event_id}/work-logs/{work_log_id}", response_model=WorkLogRead)
async def update_work_log(
    event_id: uuid.UUID,
    work_log_id: uuid.UUID,
    body: WorkLogUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> WorkLog:
    await _event_for(session, current_user, event_id)
    await require_event_role(current_user, session, event_id, minimum="admin")
    entry = await _work_log_or_404(session, event_id, work_log_id)

    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if "description" in data:
        data["description"] = data["description"].strip()
    data["updated_at"] = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return await crud_work_log.update(session, db_obj=entry, obj_in=data)


@router.delete("/{event_id}/work-logs/{work_log_id}", status_code=204)
async def delete_work_log(
    event_id: uuid.UUID,
    work_log_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    await _event_for(session, current_user, event_id)
    await require_event_role(current_user, session, event_id, minimum="admin")
    entry = await _work_log_or_404(session, event_id, work_log_id)
    await session.delete(entry)
    await session.flush()


async def _work_log_or_404(
    session: AsyncSession, event_id: uuid.UUID, work_log_id: uuid.UUID
) -> WorkLog:
    entry = await crud_work_log.get_in_event(
        session, work_log_id=work_log_id, event_id=event_id
    )
    if entry is None:
        raise_problem(404, code="work_log.not_found", detail="Work log entry not found")
    return entry


def _hours(minutes: int) -> str:
    """Decimal hours with two places — what a spreadsheet sums without help."""
    return f"{minutes / 60:.2f}"
