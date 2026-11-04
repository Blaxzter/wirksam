"""Invitations created, or accepted, by requests running at the same moment.

The daily limits count rows and then insert one, so ``logic.invitations``
counts under advisory locks per organiser and per address; inviting into an
open invitation and accepting it lock the address's invitation rows. Proving
that this holds takes real transactions on separate connections, so like
``test_voucher_concurrency.py`` these tests do not run on ``db_session``: the
setup is committed, each request runs the route or logic function in its own
session inside ``session.begin()``, and a ``finally`` block deletes everything
committed, because the test database is shared.
"""

import asyncio
import datetime as dt
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import pytest
import pytest_asyncio
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlmodel import col

from app.api.routes import events as events_routes
from app.api.routes.events import (
    create_event_invitation,
    create_event_invitations_bulk,
    remove_member,
)
from app.api.routes.invitations import accept_invitation
from app.api.routes.tasks.managers import withdraw_task_manager_invitation
from app.core.config import settings
from app.crud.event_invitation import event_invitation as crud_invitation
from app.logic import invitations
from app.logic.invitations import QuotaRefusal, invite_to_task
from app.models.event import Event
from app.models.event_invitation import EventInvitation
from app.models.event_invitation_task import EventInvitationTask
from app.models.event_membership import EventMembership
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from app.schemas.event import EventRead
from app.schemas.event_invitation import (
    EventInvitationBulkCreate,
    EventInvitationBulkResult,
    EventInvitationCreate,
    EventInvitationRead,
)
from app.schemas.task_manager import TaskManagerInviteResult

T = TypeVar("T")

#: One request's work, given its own session and the acting user.
Call = Callable[[AsyncSession, User], Awaitable[T]]


@dataclass
class Committed:
    sessions: async_sessionmaker[AsyncSession]
    key: str
    #: Owner of ``events[0]``, and of ``events[1]`` for ``organisers[1]``.
    organisers: tuple[User, User]
    events: tuple[Event, Event]
    #: Two tasks in ``events[0]``.
    tasks: tuple[Task, Task]
    #: An account that is in neither event.
    invitee: User

    def address(self, name: str) -> str:
        return f"{name}-{self.key}@example.org"


@pytest_asyncio.fixture
async def committed(test_engine: AsyncEngine) -> AsyncGenerator[Committed]:
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    key = uuid.uuid4().hex[:8]

    def _person(name: str) -> User:
        return User(
            subject=f"local|race-{name}-{key}",
            email=f"race-{name}-{key}@example.com",
            name=name.capitalize(),
            roles=[],
            is_active=True,
        )

    async with sessions() as setup:
        anna, ben, invitee = _person("anna"), _person("ben"), _person("invitee")
        setup.add_all([anna, ben, invitee])
        await setup.flush()
        events = (
            Event(
                name=f"Invitation race 1 {key}",
                start_date=dt.date(2026, 6, 10),
                end_date=dt.date(2026, 6, 14),
                created_by_id=anna.id,
            ),
            Event(
                name=f"Invitation race 2 {key}",
                start_date=dt.date(2026, 6, 10),
                end_date=dt.date(2026, 6, 14),
                created_by_id=ben.id,
            ),
        )
        setup.add_all(events)
        await setup.flush()
        setup.add_all(
            [
                EventMembership(user_id=anna.id, event_id=events[0].id, role="owner"),
                EventMembership(user_id=ben.id, event_id=events[1].id, role="owner"),
            ]
        )
        tasks = tuple(
            Task(
                name=name,
                start_date=dt.date(2026, 6, 11),
                end_date=dt.date(2026, 6, 11),
                status="published",
                created_by_id=anna.id,
                event_id=events[0].id,
            )
            for name in ("Bar", "Grill")
        )
        setup.add_all(tasks)
        await setup.commit()

    users = [anna.id, ben.id, invitee.id]
    event_ids = [e.id for e in events]
    task_ids = [t.id for t in tasks]
    try:
        yield Committed(
            sessions=sessions,
            key=key,
            organisers=(anna, ben),
            events=events,
            tasks=(tasks[0], tasks[1]),
            invitee=invitee,
        )
    finally:
        async with test_engine.begin() as conn:
            # Links go with their invitations and tasks (CASCADE).
            await conn.execute(
                delete(EventInvitation).where(
                    col(EventInvitation.event_id).in_(event_ids)
                )
            )
            await conn.execute(
                delete(TaskManager).where(col(TaskManager.task_id).in_(task_ids))
            )
            await conn.execute(delete(Task).where(col(Task.id).in_(task_ids)))
            await conn.execute(
                delete(EventMembership).where(
                    col(EventMembership.event_id).in_(event_ids)
                )
            )
            await conn.execute(delete(Event).where(col(Event.id).in_(event_ids)))
            await conn.execute(delete(User).where(col(User.id).in_(users)))


async def _request(
    c: Committed,
    actor: User,
    call: Call[T],
    *,
    delay: float = 0.0,
    pause: float = 0.0,
) -> T:
    """One request: ``call`` in its own session and transaction, as ``actor``.

    ``delay`` starts it later; ``pause`` keeps its transaction (and its locks)
    open after the call, so the other request certainly reaches them.
    """
    await asyncio.sleep(delay)
    async with c.sessions() as session, session.begin():
        user = await session.get(User, actor.id)
        assert user is not None
        result = await call(session, user)
        await asyncio.sleep(pause)
        return result


def _code(exc: object) -> str:
    assert isinstance(exc, HTTPException), exc
    detail: Any = exc.detail
    return str(detail["code"])


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


async def _invitations_to(c: Committed, email: str) -> list[EventInvitation]:
    async with c.sessions() as session:
        rows = await session.execute(
            select(EventInvitation).where(col(EventInvitation.email) == email.lower())
        )
        return list(rows.scalars())


@pytest.fixture
def limits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """The daily limits are off under TESTING; these tests switch them on."""
    monkeypatch.setattr(settings, "TESTING", False)


# ── Daily limits ──────────────────────────────────────────────────


def _invite_from_settings(event: Event, email: str) -> Call[EventInvitationRead]:
    async def call(session: AsyncSession, user: User) -> EventInvitationRead:
        return await create_event_invitation(
            event_id=event.id,
            body=EventInvitationCreate(email=email),
            session=session,
            current_user=user,
            background_tasks=BackgroundTasks(),
        )

    return call


def _invite_to(task: Task, email: str) -> Call[TaskManagerInviteResult]:
    async def call(session: AsyncSession, user: User) -> TaskManagerInviteResult:
        loaded = await session.get(Task, task.id)
        assert loaded is not None
        return await invite_to_task(
            session, task=loaded, inviter=user, email=email, now=_utc_now()
        )

    return call


def _bulk(event: Event, emails: list[str]) -> Call[EventInvitationBulkResult]:
    async def call(session: AsyncSession, user: User) -> EventInvitationBulkResult:
        return await create_event_invitations_bulk(
            event_id=event.id,
            body=EventInvitationBulkCreate(emails=emails),
            session=session,
            current_user=user,
            background_tasks=BackgroundTasks(),
        )

    return call


@pytest.mark.asyncio
@pytest.mark.usefixtures("limits_on")
async def test_two_events_cannot_both_take_an_addresss_last_invitation(
    committed: Committed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two organisers of two events invite one address at the same moment,
    with room for one more invitation to it today: exactly one goes out."""
    monkeypatch.setattr(invitations, "INVITATIONS_PER_ADDRESS_PER_DAY", 1)
    address = committed.address("shared")
    anna, ben = committed.organisers

    created, refused = await asyncio.gather(
        _request(
            committed,
            anna,
            _invite_from_settings(committed.events[0], address),
            pause=0.3,
        ),
        _request(
            committed,
            ben,
            _invite_from_settings(committed.events[1], address),
            delay=0.1,
        ),
        return_exceptions=True,
    )

    assert not isinstance(created, BaseException), created
    assert created.email == address
    assert _code(refused) == "invitation.address_limited"
    assert len(await _invitations_to(committed, address)) == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("limits_on")
async def test_one_organiser_cannot_pass_the_daily_cap_in_parallel(
    committed: Committed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One invitation left for the organiser today, two addresses typed into
    two tasks at once: one invited, one refused."""
    monkeypatch.setattr(invitations, "INVITATIONS_PER_INVITER_PER_DAY", 1)
    anna = committed.organisers[0]
    first, second = committed.address("first"), committed.address("second")

    invited, refused = await asyncio.gather(
        _request(committed, anna, _invite_to(committed.tasks[0], first), pause=0.3),
        _request(committed, anna, _invite_to(committed.tasks[1], second), delay=0.1),
        return_exceptions=True,
    )

    assert not isinstance(invited, BaseException), invited
    assert invited.status == "invited"
    assert _code(refused) == "invitation.rate_limited"
    assert len(await _invitations_to(committed, first)) == 1
    assert await _invitations_to(committed, second) == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("limits_on")
async def test_two_batches_in_opposite_order_neither_deadlock_nor_overshoot(
    committed: Committed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two organisers paste the same two addresses, in opposite order, at the
    same moment. Each address's check is slowed down so the batches overlap:
    locked one by one in the order pasted, each would hold one address the
    other waits for (a deadlock, and one batch fails). Sorted up front, the
    second batch waits for the first, then finds both addresses at their
    limit."""
    monkeypatch.setattr(invitations, "INVITATIONS_PER_ADDRESS_PER_DAY", 1)
    a, b = committed.address("a"), committed.address("b")
    real_check = events_routes.quota_refusal

    async def slow_check(
        session: AsyncSession, *, inviter: User, email: str, now: dt.datetime
    ) -> QuotaRefusal | None:
        refusal = await real_check(session, inviter=inviter, email=email, now=now)
        await asyncio.sleep(0.2)
        return refusal

    monkeypatch.setattr(events_routes, "quota_refusal", slow_check)
    anna, ben = committed.organisers

    first, second = await asyncio.gather(
        _request(committed, anna, _bulk(committed.events[0], [a, b]), pause=0.3),
        _request(committed, ben, _bulk(committed.events[1], [b, a]), delay=0.05),
        return_exceptions=True,
    )

    assert not isinstance(first, BaseException), first
    assert not isinstance(second, BaseException), second
    assert sorted(i.email or "" for i in first.created) == sorted([a, b])
    assert second.created == []
    assert sorted(second.skipped_rate_limited) == sorted([a, b])
    for address in (a, b):
        assert len(await _invitations_to(committed, address)) == 1


# ── Inviting while the invitee accepts ────────────────────────────


async def _open_invitation(c: Committed) -> EventInvitation:
    """A committed task-only invitation for the invitee, asking for the bar."""
    async with c.sessions() as session, session.begin():
        invitation = await crud_invitation.create(
            session,
            event_id=c.events[0].id,
            email=c.invitee.email or "",
            role="member",
            invited_by_id=c.organisers[0].id,
            expires_in_days=14,
            for_tasks_only=True,
        )
        session.add(
            EventInvitationTask(
                invitation_id=invitation.id,
                task_id=c.tasks[0].id,
                added_by_id=c.organisers[0].id,
                added_by_name=c.organisers[0].name,
            )
        )
    return invitation


def _accept(token: str) -> Call[EventRead]:
    async def call(session: AsyncSession, user: User) -> EventRead:
        return await accept_invitation(
            token=token,
            session=session,
            current_user=user,
            background_tasks=BackgroundTasks(),
        )

    return call


async def _in_charge(c: Committed) -> set[uuid.UUID]:
    async with c.sessions() as session:
        rows = await session.execute(
            select(col(TaskManager.task_id)).where(
                col(TaskManager.user_id) == c.invitee.id
            )
        )
        return set(rows.scalars())


async def _grill_links(c: Committed) -> list[EventInvitation]:
    """The invitations that link the grill."""
    async with c.sessions() as session:
        rows = await session.execute(
            select(EventInvitation)
            .join(
                EventInvitationTask,
                col(EventInvitationTask.invitation_id) == col(EventInvitation.id),
            )
            .where(col(EventInvitationTask.task_id) == c.tasks[1].id)
        )
        return list(rows.scalars())


@pytest.mark.asyncio
async def test_a_task_added_while_accepting_lands_on_a_new_invitation(
    committed: Committed,
) -> None:
    """The invitee accepts first; the organiser adds the grill a moment later
    to the invitation being accepted. The invite waits, finds it accepted,
    and invites again, rather than linking the grill to an invitation nobody
    will ever apply."""
    invitation = await _open_invitation(committed)
    anna = committed.organisers[0]
    grill = _invite_to(committed.tasks[1], committed.invitee.email or "")

    accepted, invited = await asyncio.gather(
        _request(committed, committed.invitee, _accept(invitation.token), pause=0.3),
        _request(committed, anna, grill, delay=0.1),
        return_exceptions=True,
    )

    assert not isinstance(accepted, BaseException), accepted
    assert not isinstance(invited, BaseException), invited
    assert invited.status == "invited"
    assert await _in_charge(committed) == {committed.tasks[0].id}
    [linked] = await _grill_links(committed)
    assert linked.id != invitation.id
    assert linked.accepted_at is None
    assert linked.revoked_at is None


@pytest.mark.asyncio
async def test_a_task_added_just_before_accepting_is_applied(
    committed: Committed,
) -> None:
    """The organiser adds the grill first; the invitee accepts while that is
    still open. The accept waits for it and puts them in charge of both."""
    invitation = await _open_invitation(committed)
    anna = committed.organisers[0]
    grill = _invite_to(committed.tasks[1], committed.invitee.email or "")

    invited, accepted = await asyncio.gather(
        _request(committed, anna, grill, pause=0.3),
        _request(committed, committed.invitee, _accept(invitation.token), delay=0.1),
        return_exceptions=True,
    )

    assert not isinstance(invited, BaseException), invited
    assert not isinstance(accepted, BaseException), accepted
    assert invited.status == "invited"
    assert invited.invitation is not None
    assert invited.invitation.id == invitation.id
    assert await _in_charge(committed) == {t.id for t in committed.tasks}


# ── Withdrawing while the invitee accepts ─────────────────────────


def _withdraw(task: Task, invitation: EventInvitation) -> Call[None]:
    async def call(session: AsyncSession, user: User) -> None:
        await withdraw_task_manager_invitation(
            task_id=task.id,
            invitation_id=invitation.id,
            session=session,
            current_user=user,
        )

    return call


async def _reloaded(c: Committed, invitation: EventInvitation) -> EventInvitation:
    async with c.sessions() as session:
        loaded = await session.get(EventInvitation, invitation.id)
        assert loaded is not None
        return loaded


@pytest.mark.asyncio
async def test_withdrawing_after_the_invitee_accepted_is_refused(
    committed: Committed,
) -> None:
    """The invitee accepts first and the organiser withdraws a moment later. The
    withdrawal waits and finds the invitation accepted. It must not say it took
    the task back while the person is in charge, nor mark an accepted invitation
    as revoked."""
    invitation = await _open_invitation(committed)
    anna = committed.organisers[0]

    accepted, refused = await asyncio.gather(
        _request(committed, committed.invitee, _accept(invitation.token), pause=0.3),
        _request(committed, anna, _withdraw(committed.tasks[0], invitation), delay=0.1),
        return_exceptions=True,
    )

    assert not isinstance(accepted, BaseException), accepted
    assert _code(refused) == "task.manager_invitation_not_found"
    assert await _in_charge(committed) == {committed.tasks[0].id}
    stored = await _reloaded(committed, invitation)
    assert stored.accepted_at is not None
    assert stored.revoked_at is None


@pytest.mark.asyncio
async def test_accepting_after_the_organiser_withdrew_is_refused(
    committed: Committed,
) -> None:
    """The organiser withdraws first and the invitee accepts a moment later. The
    accept waits and finds the invitation withdrawn."""
    invitation = await _open_invitation(committed)
    anna = committed.organisers[0]

    withdrawn, refused = await asyncio.gather(
        _request(committed, anna, _withdraw(committed.tasks[0], invitation), pause=0.3),
        _request(committed, committed.invitee, _accept(invitation.token), delay=0.1),
        return_exceptions=True,
    )

    assert not isinstance(withdrawn, BaseException), withdrawn
    assert _code(refused) == "invitation.revoked"
    assert await _in_charge(committed) == set()
    stored = await _reloaded(committed, invitation)
    assert stored.accepted_at is None
    assert stored.revoked_at is not None


# ── Leaving while a member accepts ────────────────────────────────


def _leave(event: Event) -> Call[None]:
    async def call(session: AsyncSession, user: User) -> None:
        await remove_member(
            event_id=event.id, user_id=user.id, session=session, current_user=user
        )

    return call


async def _is_member(c: Committed) -> bool:
    async with c.sessions() as session:
        rows = await session.execute(
            select(col(EventMembership.id)).where(
                col(EventMembership.user_id) == c.invitee.id,
                col(EventMembership.event_id) == c.events[0].id,
            )
        )
        return rows.first() is not None


@pytest.mark.asyncio
async def test_a_leave_waits_for_a_member_accepting_and_removes_what_it_granted(
    committed: Committed,
) -> None:
    """Someone already in the event accepts in one tab and leaves in another. The
    leave's clean-up has to see what accepting granted. If it ran past it, the
    person would be in charge again the day they re-joined."""
    async with committed.sessions() as session, session.begin():
        session.add(
            EventMembership(
                user_id=committed.invitee.id,
                event_id=committed.events[0].id,
                role="member",
            )
        )
    invitation = await _open_invitation(committed)

    accepted, left = await asyncio.gather(
        _request(committed, committed.invitee, _accept(invitation.token), pause=0.3),
        _request(committed, committed.invitee, _leave(committed.events[0]), delay=0.1),
        return_exceptions=True,
    )

    assert not isinstance(accepted, BaseException), accepted
    assert not isinstance(left, BaseException), left
    assert not await _is_member(committed)
    assert await _in_charge(committed) == set()


@pytest.mark.asyncio
async def test_accepting_after_a_leave_joins_again_as_a_newcomer(
    committed: Committed,
) -> None:
    """The leave comes first and the accept waits for it, so the accept has to
    treat the person as new instead of relying on a row that's gone."""
    async with committed.sessions() as session, session.begin():
        session.add(
            EventMembership(
                user_id=committed.invitee.id,
                event_id=committed.events[0].id,
                role="member",
            )
        )
    invitation = await _open_invitation(committed)

    left, accepted = await asyncio.gather(
        _request(committed, committed.invitee, _leave(committed.events[0]), pause=0.3),
        _request(committed, committed.invitee, _accept(invitation.token), delay=0.1),
        return_exceptions=True,
    )

    assert not isinstance(left, BaseException), left
    assert not isinstance(accepted, BaseException), accepted
    assert await _is_member(committed)
    assert await _in_charge(committed) == {committed.tasks[0].id}
