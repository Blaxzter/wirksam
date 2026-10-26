import datetime as dt
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Self

from sqlalchemy import ColumnElement, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.team_requirements import add_years, label_key
from app.models.booking import Booking
from app.models.event_team import (
    EventTeam,
    EventTeamCheck,
    EventTeamDocument,
    EventTeamMember,
    EventTeamRequirement,
)
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.event_team import (
    EventTeamCreate,
    EventTeamUpdate,
    TeamRequirementIn,
)


def _now() -> datetime:
    """Naive UTC, matching how every other timestamp in the app is stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class _RequirementShape:
    """What a requirement asked before an edit, to compare against after it."""

    label: str
    ask_issue_date: bool
    valid_for_years: int | None
    accepts_document: bool

    @classmethod
    def of(cls, req: EventTeamRequirement) -> Self:
        return cls(
            label=req.label,
            ask_issue_date=req.ask_issue_date,
            valid_for_years=req.valid_for_years,
            accepts_document=req.accepts_document,
        )


class CRUDEventTeam:
    """Teams, their requirements, rosters, checks and request documents.

    Never commits; the request owns the transaction. Who may call what is
    decided in the routes through ``app.logic.permissions``.
    """

    # --- Teams ------------------------------------------------------------

    async def get_in_event(
        self,
        session: AsyncSession,
        *,
        team_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> EventTeam | None:
        """A team, but only if it belongs to ``event_id``.

        Always look teams up through the event in the URL: a team id from
        another event must read as "not found", not leak across tenancies.
        """
        result = await session.execute(
            select(EventTeam).where(
                col(EventTeam.id) == team_id,
                col(EventTeam.event_id) == event_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_event(
        self, session: AsyncSession, *, event_id: uuid.UUID
    ) -> list[EventTeam]:
        result = await session.execute(
            select(EventTeam)
            .where(col(EventTeam.event_id) == event_id)
            .order_by(func.lower(col(EventTeam.name)))
        )
        return list(result.scalars().all())

    async def get_by_name_ci(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> EventTeam | None:
        """The event's team called ``name``, ignoring case and outer spaces.

        The friendly pre-check before an insert; the unique index on
        ``(event_id, lower(name))`` settles a race. ``exclude_id`` skips the
        team being renamed.
        """
        query = select(EventTeam).where(
            col(EventTeam.event_id) == event_id,
            func.lower(col(EventTeam.name)) == name.strip().lower(),
        )
        if exclude_id is not None:
            query = query.where(col(EventTeam.id) != exclude_id)
        result = await session.execute(query)
        return result.scalars().first()

    async def create(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        data: EventTeamCreate,
    ) -> EventTeam:
        team = EventTeam(
            event_id=event_id,
            **data.model_dump(exclude={"requirements"}),
        )
        session.add(team)
        await session.flush()
        await self.replace_requirements(session, team=team, items=data.requirements)
        await session.refresh(team)
        return team

    async def update(
        self,
        session: AsyncSession,
        *,
        team: EventTeam,
        data: EventTeamUpdate,
    ) -> EventTeam:
        """Apply the fields the client sent, requirements included."""
        fields = data.model_dump(exclude_unset=True, exclude={"requirements"})
        for key, value in fields.items():
            setattr(team, key, value)
        team.updated_at = _now()
        session.add(team)
        await session.flush()
        if data.requirements is not None:
            await self.replace_requirements(session, team=team, items=data.requirements)
        await session.refresh(team)
        return team

    async def counts(
        self, session: AsyncSession, *, team_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict[str, int]]:
        """Approved members, pending requests and gated tasks, per team."""
        out: dict[uuid.UUID, dict[str, int]] = {
            tid: {"approved": 0, "pending": 0, "tasks": 0} for tid in team_ids
        }
        if not team_ids:
            return out
        rows = await session.execute(
            select(
                col(EventTeamMember.team_id), col(EventTeamMember.status), func.count()
            )
            .where(
                col(EventTeamMember.team_id).in_(team_ids),
                col(EventTeamMember.status).in_(("approved", "pending")),
            )
            .group_by(col(EventTeamMember.team_id), col(EventTeamMember.status))
        )
        for team_id, status, n in rows.all():
            out[team_id][status] = n
        task_rows = await session.execute(
            select(col(Task.team_id), func.count())
            .where(col(Task.team_id).in_(team_ids))
            .group_by(col(Task.team_id))
        )
        for team_id, n in task_rows.all():
            if team_id is not None:
                out[team_id]["tasks"] = n
        return out

    async def tasks_by_team(
        self,
        session: AsyncSession,
        *,
        team_ids: list[uuid.UUID],
        published_only: bool,
    ) -> dict[uuid.UUID, list[tuple[uuid.UUID, str]]]:
        """``(task id, name)`` of the tasks each team gates, alphabetically."""
        out: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)
        if not team_ids:
            return out
        query = (
            select(col(Task.team_id), col(Task.id), col(Task.name))
            .where(col(Task.team_id).in_(team_ids))
            .order_by(func.lower(col(Task.name)))
        )
        if published_only:
            query = query.where(col(Task.status) == "published")
        for team_id, task_id, name in (await session.execute(query)).all():
            if team_id is not None:
                out[team_id].append((task_id, name))
        return out

    async def open_shifts_by_task(
        self,
        session: AsyncSession,
        *,
        team_ids: list[uuid.UUID],
        published_only: bool,
        today: dt.date,
    ) -> dict[uuid.UUID, int]:
        """Shifts from ``today`` on, with a free place, per task of these teams."""
        if not team_ids:
            return {}
        booked = (
            select(func.count())
            .select_from(Booking)
            .where(
                col(Booking.shift_id) == col(Shift.id),
                col(Booking.status) == "confirmed",
            )
            .correlate(Shift)
            .scalar_subquery()
        )
        query = (
            select(col(Task.id), func.count())
            .select_from(Shift)
            .join(Task, col(Task.id) == col(Shift.task_id))
            .where(
                col(Task.team_id).in_(team_ids),
                col(Shift.date) >= today,
                col(Shift.max_bookings) > booked,
            )
            .group_by(col(Task.id))
        )
        if published_only:
            query = query.where(col(Task.status) == "published")
        return dict((await session.execute(query)).all())

    async def lead_names(
        self, session: AsyncSession, *, team_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[str]]:
        out: dict[uuid.UUID, list[str]] = defaultdict(list)
        if not team_ids:
            return out
        rows = await session.execute(
            select(col(EventTeamMember.team_id), col(User.name))
            .join(User, col(User.id) == col(EventTeamMember.user_id))
            .where(
                col(EventTeamMember.team_id).in_(team_ids),
                col(EventTeamMember.status) == "approved",
                col(EventTeamMember.role) == "lead",
            )
            .order_by(func.lower(col(User.name)))
        )
        for team_id, name in rows.all():
            if name:
                out[team_id].append(name)
        return out

    async def team_count_by_event(
        self, session: AsyncSession, *, event_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not event_ids:
            return {}
        rows = await session.execute(
            select(col(EventTeam.event_id), func.count())
            .where(col(EventTeam.event_id).in_(event_ids))
            .group_by(col(EventTeam.event_id))
        )
        return dict(rows.all())

    async def decidable_pending_by_event(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        admin_event_ids: list[uuid.UUID],
        member_event_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, int]:
        """Pending team requests the user may decide, per event.

        All of them in ``admin_event_ids``; in ``member_event_ids`` only those
        of teams the user leads. One query either way.
        """
        if not admin_event_ids and not member_event_ids:
            return {}
        leads = (
            select(col(EventTeamMember.team_id))
            .where(
                col(EventTeamMember.user_id) == user_id,
                col(EventTeamMember.status) == "approved",
                col(EventTeamMember.role) == "lead",
            )
            .scalar_subquery()
        )
        conditions: list[ColumnElement[bool]] = []
        if admin_event_ids:
            conditions.append(col(EventTeam.event_id).in_(admin_event_ids))
        if member_event_ids:
            conditions.append(
                col(EventTeam.event_id).in_(member_event_ids)
                & col(EventTeam.id).in_(leads)
            )
        query = (
            select(col(EventTeam.event_id), func.count())
            .select_from(EventTeamMember)
            .join(EventTeam, col(EventTeam.id) == col(EventTeamMember.team_id))
            .where(col(EventTeamMember.status) == "pending")
            .group_by(col(EventTeam.event_id))
        )
        query = query.where(or_(*conditions))
        return dict((await session.execute(query)).all())

    # --- Requirements -----------------------------------------------------

    async def requirements_for_teams(
        self, session: AsyncSession, *, team_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[EventTeamRequirement]]:
        out: dict[uuid.UUID, list[EventTeamRequirement]] = defaultdict(list)
        if not team_ids:
            return out
        result = await session.execute(
            select(EventTeamRequirement)
            .where(col(EventTeamRequirement.team_id).in_(team_ids))
            .order_by(
                col(EventTeamRequirement.position),
                col(EventTeamRequirement.created_at),
            )
        )
        for req in result.scalars().all():
            out[req.team_id].append(req)
        return out

    async def requirements(
        self, session: AsyncSession, *, team_id: uuid.UUID
    ) -> list[EventTeamRequirement]:
        return (await self.requirements_for_teams(session, team_ids=[team_id]))[team_id]

    async def replace_requirements(
        self,
        session: AsyncSession,
        *,
        team: EventTeam,
        items: list[TeamRequirementIn],
    ) -> None:
        """Make the team's requirements exactly ``items``, in that order.

        Items with an ``id`` update that requirement, items without add one,
        and requirements left out are deleted — their checks and documents
        with them. Unknown ids raise ``LookupError``. An edit keeps the checks
        recorded against the requirement only while it still asks the same
        thing; see :meth:`_settle_edited_requirement`.
        """
        existing = {r.id: r for r in await self.requirements(session, team_id=team.id)}
        keep: set[uuid.UUID] = set()
        for position, item in enumerate(items):
            fields = item.model_dump(exclude={"id"})
            if item.id is not None:
                req = existing.get(item.id)
                if req is None:
                    raise LookupError(item.id)
                before = _RequirementShape.of(req)
                for key, value in fields.items():
                    setattr(req, key, value)
                req.position = position
                req.updated_at = _now()
                keep.add(req.id)
                await self._settle_edited_requirement(session, before=before, after=req)
            else:
                req = EventTeamRequirement(team_id=team.id, position=position, **fields)
            session.add(req)
        for req_id, req in existing.items():
            if req_id not in keep:
                await session.delete(req)
        await session.flush()

    async def _settle_edited_requirement(
        self,
        session: AsyncSession,
        *,
        before: _RequirementShape,
        after: EventTeamRequirement,
    ) -> None:
        """Bring the checks and files of an edited requirement in line with it.

        A check is a decider's word on *this* question. Renaming the
        requirement ("First-aid course" → "Police certificate") or starting to
        ask for the issue date changes the question, so the old checks are
        dropped and the members show as needing a new check — otherwise the
        approval rule could be met by ticks nobody gave. A new validity only
        moves the expiry dates. A requirement that stops taking files loses
        the ones already attached to waiting requests.
        """
        checks = (
            (
                await session.execute(
                    select(EventTeamCheck).where(
                        col(EventTeamCheck.requirement_id) == after.id
                    )
                )
            )
            .scalars()
            .all()
        )
        asks_more = after.ask_issue_date and not before.ask_issue_date
        if label_key(before.label) != label_key(after.label) or asks_more:
            for check in checks:
                await session.delete(check)
        elif (
            before.valid_for_years != after.valid_for_years
            or before.ask_issue_date != after.ask_issue_date
        ):
            for check in checks:
                # Counted from the issue date where one is asked for, else
                # from the day of the check — as when it was recorded.
                start = (
                    check.issued_on
                    if after.ask_issue_date and check.issued_on is not None
                    else check.checked_at.date()
                )
                check.expires_on = (
                    add_years(start, after.valid_for_years)
                    if after.valid_for_years is not None
                    else None
                )
                check.updated_at = _now()
                session.add(check)
        if before.accepts_document and not after.accepts_document:
            await session.execute(
                delete(EventTeamDocument).where(
                    col(EventTeamDocument.requirement_id) == after.id
                )
            )

    # --- Members ----------------------------------------------------------

    async def get_member(
        self,
        session: AsyncSession,
        *,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> EventTeamMember | None:
        result = await session.execute(
            select(EventTeamMember).where(
                col(EventTeamMember.team_id) == team_id,
                col(EventTeamMember.user_id) == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def rows_for_user(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        team_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, EventTeamMember]:
        if not team_ids:
            return {}
        result = await session.execute(
            select(EventTeamMember).where(
                col(EventTeamMember.user_id) == user_id,
                col(EventTeamMember.team_id).in_(team_ids),
            )
        )
        return {row.team_id: row for row in result.scalars().all()}

    async def approved_team_ids(
        self, session: AsyncSession, *, user_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Every team, in any event, the user is an approved member of."""
        result = await session.execute(
            select(col(EventTeamMember.team_id)).where(
                col(EventTeamMember.user_id) == user_id,
                col(EventTeamMember.status) == "approved",
            )
        )
        return list(result.scalars().all())

    async def is_approved(
        self,
        session: AsyncSession,
        *,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str | None = None,
    ) -> bool:
        query = select(col(EventTeamMember.id)).where(
            col(EventTeamMember.team_id) == team_id,
            col(EventTeamMember.user_id) == user_id,
            col(EventTeamMember.status) == "approved",
        )
        if role is not None:
            query = query.where(col(EventTeamMember.role) == role)
        result = await session.execute(query)
        return result.first() is not None

    async def list_members(
        self,
        session: AsyncSession,
        *,
        team_ids: list[uuid.UUID],
        status: str | None = None,
    ) -> list[tuple[EventTeamMember, User]]:
        """Rows of the given teams with their users: leads first, then by name.

        Pending requests come oldest first instead, so the queue reads in the
        order people asked.
        """
        if not team_ids:
            return []
        query = (
            select(EventTeamMember, User)
            .join(User, col(User.id) == col(EventTeamMember.user_id))
            .where(col(EventTeamMember.team_id).in_(team_ids))
        )
        if status:
            query = query.where(col(EventTeamMember.status) == status)
        if status == "pending":
            query = query.order_by(col(EventTeamMember.created_at))
        else:
            query = query.order_by(
                col(EventTeamMember.role).desc(), func.lower(col(User.name))
            )
        result = await session.execute(query)
        return [(m, u) for m, u in result.all()]

    async def approved_rows_for_teams(
        self,
        session: AsyncSession,
        *,
        team_ids: list[uuid.UUID],
        user_ids: set[uuid.UUID],
    ) -> dict[uuid.UUID, list[EventTeamMember]]:
        """Approved rows of ``user_ids`` in ``team_ids``, grouped by team."""
        out: dict[uuid.UUID, list[EventTeamMember]] = defaultdict(list)
        if not team_ids or not user_ids:
            return out
        result = await session.execute(
            select(EventTeamMember).where(
                col(EventTeamMember.team_id).in_(team_ids),
                col(EventTeamMember.user_id).in_(user_ids),
                col(EventTeamMember.status) == "approved",
            )
        )
        for row in result.scalars().all():
            out[row.team_id].append(row)
        return out

    async def other_team_names(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        user_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[tuple[uuid.UUID, str]]]:
        """``{user_id: [(team_id, team_name), …]}`` of approved rows in the event."""
        out: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)
        if not user_ids:
            return out
        rows = await session.execute(
            select(col(EventTeamMember.user_id), col(EventTeam.id), col(EventTeam.name))
            .join(EventTeam, col(EventTeam.id) == col(EventTeamMember.team_id))
            .where(
                col(EventTeam.event_id) == event_id,
                col(EventTeamMember.user_id).in_(user_ids),
                col(EventTeamMember.status) == "approved",
            )
            .order_by(func.lower(col(EventTeam.name)))
        )
        for user_id, team_id, name in rows.all():
            out[user_id].append((team_id, name))
        return out

    async def booked_shift_counts(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        user_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, int]:
        """Confirmed bookings per user in one event."""
        if not user_ids:
            return {}
        rows = await session.execute(
            select(col(Booking.user_id), func.count())
            .join(Shift, col(Shift.id) == col(Booking.shift_id))
            .join(Task, col(Task.id) == col(Shift.task_id))
            .where(
                col(Task.event_id) == event_id,
                col(Booking.user_id).in_(user_ids),
                col(Booking.status) == "confirmed",
            )
            .group_by(col(Booking.user_id))
        )
        return dict(rows.all())

    async def request(
        self,
        session: AsyncSession,
        *,
        team: EventTeam,
        user_id: uuid.UUID,
        message: str | None,
    ) -> EventTeamMember:
        """Join an open team at once, or open a request for a restricted one.

        A declined row is re-opened rather than blocked, so someone can ask
        again after talking to the team lead. A pending row on a team that
        has since stopped requiring approval is approved here.
        """
        status = "pending" if team.requires_approval else "approved"
        obj = await self.get_member(session, team_id=team.id, user_id=user_id)
        if obj is None:
            obj = EventTeamMember(team_id=team.id, user_id=user_id)
        elif status == "pending":
            # Asking again: the queue should show when they asked *this* time.
            obj.created_at = _now()
        obj.status = status
        obj.message = message
        obj.decided_by_id = None
        obj.decided_by_name = None
        obj.decided_at = None if status == "pending" else _now()
        obj.updated_at = _now()
        session.add(obj)
        await session.flush()
        if status == "approved":
            # A leftover request let through: decided, so its files go, as in
            # ``decide`` and ``place``.
            await self.delete_documents(session, member_id=obj.id)
        await session.refresh(obj)
        return obj

    async def place(
        self,
        session: AsyncSession,
        *,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str,
        decided_by: User,
    ) -> EventTeamMember:
        """Make someone an approved member (or lead).

        Only for someone who is not approved yet — the route refuses an
        approved row, so a lead cannot use this to change another lead's role.
        A pending request is approved on the way, and its documents dropped.
        """
        obj = await self.get_member(session, team_id=team_id, user_id=user_id)
        if obj is None:
            obj = EventTeamMember(team_id=team_id, user_id=user_id)
        obj.status = "approved"
        obj.role = role
        obj.decided_by_id = decided_by.id
        obj.decided_by_name = decided_by.name
        obj.decided_at = _now()
        obj.updated_at = _now()
        session.add(obj)
        await session.flush()
        await self.delete_documents(session, member_id=obj.id)
        await session.refresh(obj)
        return obj

    async def decide(
        self,
        session: AsyncSession,
        *,
        member: EventTeamMember,
        approve: bool,
        decided_by: User,
    ) -> EventTeamMember:
        """Approve or decline a request. Either way its documents are deleted."""
        member.status = "approved" if approve else "declined"
        member.decided_by_id = decided_by.id
        member.decided_by_name = decided_by.name
        member.decided_at = _now()
        member.updated_at = _now()
        session.add(member)
        await session.flush()
        await self.delete_documents(session, member_id=member.id)
        await session.refresh(member)
        return member

    async def approve_all_pending(
        self, session: AsyncSession, *, team_id: uuid.UUID, decided_by: User
    ) -> int:
        """Approve every pending request at once (the team just opened up)."""
        pending = select(col(EventTeamMember.id)).where(
            col(EventTeamMember.team_id) == team_id,
            col(EventTeamMember.status) == "pending",
        )
        await session.execute(
            delete(EventTeamDocument).where(
                col(EventTeamDocument.member_id).in_(pending)
            )
        )
        result = await session.execute(
            update(EventTeamMember)
            .where(
                col(EventTeamMember.team_id) == team_id,
                col(EventTeamMember.status) == "pending",
            )
            .values(
                status="approved",
                decided_by_id=decided_by.id,
                decided_by_name=decided_by.name,
                decided_at=_now(),
                updated_at=_now(),
            )
            .execution_options(synchronize_session="fetch")
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def set_role(
        self, session: AsyncSession, *, member: EventTeamMember, role: str
    ) -> EventTeamMember:
        member.role = role
        member.updated_at = _now()
        session.add(member)
        await session.flush()
        await session.refresh(member)
        return member

    async def remove(self, session: AsyncSession, *, member: EventTeamMember) -> None:
        """Delete a row; its checks and documents go with it (CASCADE)."""
        await session.delete(member)
        await session.flush()

    async def remove_user_from_event_teams(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> None:
        """Drop every team row of a user who left (or was removed from) an event.

        Without this, re-joining the event later would silently restore team
        access nobody re-approved. Checks and documents cascade with the rows.
        """
        team_ids = select(col(EventTeam.id)).where(col(EventTeam.event_id) == event_id)
        await session.execute(
            delete(EventTeamMember).where(
                col(EventTeamMember.user_id) == user_id,
                col(EventTeamMember.team_id).in_(team_ids),
            )
        )
        await session.flush()

    # --- Checks -----------------------------------------------------------

    async def record_check(
        self,
        session: AsyncSession,
        *,
        member_id: uuid.UUID,
        requirement_id: uuid.UUID,
        issued_on: dt.date | None,
        expires_on: dt.date | None,
        checked_by: User,
    ) -> EventTeamCheck:
        """Record (or renew) that ``checked_by`` saw proof of a requirement."""
        result = await session.execute(
            select(EventTeamCheck).where(
                col(EventTeamCheck.member_id) == member_id,
                col(EventTeamCheck.requirement_id) == requirement_id,
            )
        )
        check = result.scalar_one_or_none()
        if check is None:
            check = EventTeamCheck(
                member_id=member_id, requirement_id=requirement_id, checked_at=_now()
            )
        check.checked_at = _now()
        check.checked_by_id = checked_by.id
        check.checked_by_name = checked_by.name
        check.issued_on = issued_on
        check.expires_on = expires_on
        check.updated_at = _now()
        session.add(check)
        await session.flush()
        return check

    async def checks_for_members(
        self, session: AsyncSession, *, member_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[tuple[EventTeamCheck, EventTeamRequirement]]]:
        out: dict[uuid.UUID, list[tuple[EventTeamCheck, EventTeamRequirement]]] = (
            defaultdict(list)
        )
        if not member_ids:
            return out
        rows = await session.execute(
            select(EventTeamCheck, EventTeamRequirement)
            .join(
                EventTeamRequirement,
                col(EventTeamRequirement.id) == col(EventTeamCheck.requirement_id),
            )
            .where(col(EventTeamCheck.member_id).in_(member_ids))
            .order_by(col(EventTeamRequirement.position))
        )
        for check, req in rows.all():
            out[check.member_id].append((check, req))
        return out

    async def checks_in_event(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        user_ids: list[uuid.UUID],
        exclude_team_id: uuid.UUID | None = None,
    ) -> list[tuple[uuid.UUID, EventTeamCheck, EventTeamRequirement, uuid.UUID, str]]:
        """``(user_id, check, requirement, team id, team name)`` in one event.

        Only *approved* rows count: a check on a declined request is not one
        the event relied on. Never crosses into another event — a certificate
        seen for one organiser is not seen for the next.
        """
        if not user_ids:
            return []
        query = (
            select(
                col(EventTeamMember.user_id),
                EventTeamCheck,
                EventTeamRequirement,
                col(EventTeam.id),
                col(EventTeam.name),
            )
            .join(
                EventTeamMember,
                col(EventTeamMember.id) == col(EventTeamCheck.member_id),
            )
            .join(EventTeam, col(EventTeam.id) == col(EventTeamMember.team_id))
            .join(
                EventTeamRequirement,
                col(EventTeamRequirement.id) == col(EventTeamCheck.requirement_id),
            )
            .where(
                col(EventTeam.event_id) == event_id,
                col(EventTeamMember.user_id).in_(user_ids),
                col(EventTeamMember.status) == "approved",
            )
        )
        if exclude_team_id is not None:
            query = query.where(col(EventTeam.id) != exclude_team_id)
        rows = await session.execute(query)
        return [
            (uid, check, req, team_id, name)
            for uid, check, req, team_id, name in rows.all()
        ]

    # --- Documents --------------------------------------------------------

    async def get_document(
        self,
        session: AsyncSession,
        *,
        member_id: uuid.UUID,
        requirement_id: uuid.UUID,
    ) -> EventTeamDocument | None:
        result = await session.execute(
            select(EventTeamDocument).where(
                col(EventTeamDocument.member_id) == member_id,
                col(EventTeamDocument.requirement_id) == requirement_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_document(
        self,
        session: AsyncSession,
        *,
        member_id: uuid.UUID,
        requirement_id: uuid.UUID,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> EventTeamDocument:
        """Attach a file to a request, replacing an earlier one for the same check."""
        doc = await self.get_document(
            session, member_id=member_id, requirement_id=requirement_id
        )
        if doc is None:
            doc = EventTeamDocument(
                member_id=member_id,
                requirement_id=requirement_id,
                filename=filename,
                content_type=content_type,
                size=len(data),
                data=data,
            )
        else:
            doc.filename = filename
            doc.content_type = content_type
            doc.size = len(data)
            doc.data = data
            doc.created_at = _now()
            doc.updated_at = _now()
        session.add(doc)
        await session.flush()
        return doc

    async def delete_document(
        self, session: AsyncSession, *, document: EventTeamDocument
    ) -> None:
        await session.delete(document)
        await session.flush()

    async def delete_documents(
        self, session: AsyncSession, *, member_id: uuid.UUID
    ) -> None:
        """Delete every file attached to a request (it was just decided)."""
        await session.execute(
            delete(EventTeamDocument).where(
                col(EventTeamDocument.member_id) == member_id
            )
        )
        await session.flush()

    async def document_meta_for_members(
        self, session: AsyncSession, *, member_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[tuple[uuid.UUID, str, str, int, datetime]]]:
        """``{member_id: [(requirement_id, filename, type, size, uploaded), …]}``.

        Selects the columns only, so listing a queue never loads the bytes.
        """
        out: dict[uuid.UUID, list[tuple[uuid.UUID, str, str, int, datetime]]] = (
            defaultdict(list)
        )
        if not member_ids:
            return out
        rows = await session.execute(
            select(
                col(EventTeamDocument.member_id),
                col(EventTeamDocument.requirement_id),
                col(EventTeamDocument.filename),
                col(EventTeamDocument.content_type),
                col(EventTeamDocument.size),
                col(EventTeamDocument.created_at),
            )
            .join(
                EventTeamRequirement,
                col(EventTeamRequirement.id) == col(EventTeamDocument.requirement_id),
            )
            .where(col(EventTeamDocument.member_id).in_(member_ids))
            .order_by(col(EventTeamRequirement.position))
        )
        for member_id, req_id, filename, ctype, size, created in rows.all():
            out[member_id].append((req_id, filename, ctype, size, created))
        return out


event_team = CRUDEventTeam()
