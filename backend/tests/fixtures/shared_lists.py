"""Shared lists, and the guests who signed up through them.

Lists are created through ``crud.shared_list`` and guests through
``crud.shared_list_guest.create``, the calls the routes make, so a test sees the
rows production writes: the guest user's exact flags, a fresh list code, and
bookings carrying their sign-up's person (first-name consent, name, phone).

Nothing here commits; ``db_session`` is savepoint-wrapped like everywhere else.

``count_queries`` pins that a view or a batch over many lists costs no more
statements than one over a single list.
"""

import datetime as dt
from collections.abc import Callable, Generator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.shared_list import shared_list as crud_shared_list
from app.crud.shared_list_guest import shared_list_guest as crud_guest
from app.logic import clock
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import (
    AskMode,
    EndsMode,
    ListStatus,
    SharedList,
    SharedListGuest,
    ShowNames,
)
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User

CountQueries = Callable[[], AbstractContextManager[list[str]]]


class SharedListFactory(Protocol):
    """Creates a list; by default a live one on ``test_event`` with ``test_task``."""

    async def __call__(
        self,
        *,
        event: Event | None = None,
        tasks: Sequence[Task] | None = None,
        excluded: Sequence[Shift] = (),
        created_by: User | None = None,
        title: str = "Helfer gesucht",
        status: ListStatus = "live",
        ends_mode: EndsMode = "last_shift",
        ends_on: dt.date | None = None,
        ask_email: AskMode = "required",
        ask_phone: AskMode = "off",
        show_names: ShowNames = "none",
        max_per_person: int | None = None,
    ) -> SharedList: ...


@dataclass(frozen=True, slots=True)
class ListGuest:
    """One sign-up chain: the guest user, its contact row and its bookings."""

    user: User
    guest: SharedListGuest
    bookings: list[Booking]


class ListGuestFactory(Protocol):
    """Signs a guest up on ``shared_list``, confirmed on each of ``shifts``."""

    async def __call__(
        self,
        shared_list: SharedList,
        *,
        name: str = "Gast Eins",
        email: str | None = None,
        phone: str | None = None,
        language: Literal["en", "de"] = "de",
        shifts: Sequence[Shift] = (),
    ) -> ListGuest: ...


@pytest_asyncio.fixture
async def make_shared_list(
    db_session: AsyncSession,
    test_event: Event,
    test_task: Task,
    test_event_admin_user: User,
) -> SharedListFactory:
    """Return a factory for lists. A factory, because the coverage and access
    rules are statements about several lists side by side."""

    async def _make(
        *,
        event: Event | None = None,
        tasks: Sequence[Task] | None = None,
        excluded: Sequence[Shift] = (),
        created_by: User | None = None,
        title: str = "Helfer gesucht",
        status: ListStatus = "live",
        ends_mode: EndsMode = "last_shift",
        ends_on: dt.date | None = None,
        ask_email: AskMode = "required",
        ask_phone: AskMode = "off",
        show_names: ShowNames = "none",
        max_per_person: int | None = None,
    ) -> SharedList:
        shared_list = await crud_shared_list.create(
            db_session,
            event_id=(event or test_event).id,
            created_by=created_by or test_event_admin_user,
            title=title,
            intro=None,
            share_note=None,
            ask_email=ask_email,
            ask_phone=ask_phone,
            show_names=show_names,
            max_per_person=max_per_person,
            ends_mode=ends_mode,
            ends_on=ends_on,
        )
        await crud_shared_list.set_tasks(
            db_session,
            shared_list_id=shared_list.id,
            task_ids=[t.id for t in (tasks if tasks is not None else [test_task])],
        )
        await crud_shared_list.set_excluded(
            db_session,
            shared_list_id=shared_list.id,
            shift_ids=[s.id for s in excluded],
        )
        if status != "live":
            now = clock.utc_now()
            shared_list.status = status
            shared_list.paused_at = now if status == "paused" else None
            shared_list.ended_at = now if status == "ended" else None
            db_session.add(shared_list)
            await db_session.flush()
        return shared_list

    return _make


@pytest_asyncio.fixture
async def test_shared_list(make_shared_list: SharedListFactory) -> SharedList:
    """A live list on ``test_event`` offering ``test_task``, made by its admin."""
    return await make_shared_list()


@pytest_asyncio.fixture
async def make_list_guest(db_session: AsyncSession) -> ListGuestFactory:
    """Return a factory for guests who signed up through a list.

    Their bookings carry the list in ``shared_list_id``, the list's setting as
    their first-name consent, and the chain's name and phone, as a sign-up
    through a form showing that setting writes them. No capacity check and no
    reminders: that is the sign-up's business.
    """

    async def _make(
        shared_list: SharedList,
        *,
        name: str = "Gast Eins",
        email: str | None = None,
        phone: str | None = None,
        language: Literal["en", "de"] = "de",
        shifts: Sequence[Shift] = (),
    ) -> ListGuest:
        guest = await crud_guest.create(
            db_session,
            shared_list=shared_list,
            name=name,
            email=email,
            phone=phone,
            language=language,
            now=clock.utc_now(),
        )
        user = await db_session.get(User, guest.user_id)
        assert user is not None
        bookings = [
            Booking(
                shift_id=shift.id,
                user_id=user.id,
                status="confirmed",
                shared_list_id=shared_list.id,
                show_first_name=shared_list.show_names == "first",
                guest_name=user.name,
                guest_phone=user.phone_number,
            )
            for shift in shifts
        ]
        db_session.add_all(bookings)
        await db_session.flush()
        return ListGuest(user=user, guest=guest, bookings=bookings)

    return _make


@pytest.fixture
def count_queries(db_session: AsyncSession) -> CountQueries:
    """``with count_queries() as statements:`` collects what the session runs."""
    engine = db_session.get_bind()

    @contextmanager
    def _count() -> Generator[list[str]]:
        statements: list[str] = []

        def record(_c: Any, _cur: Any, statement: str, *_rest: Any) -> None:
            statements.append(statement)

        sa_event.listen(engine, "before_cursor_execute", record)
        try:
            yield statements
        finally:
            sa_event.remove(engine, "before_cursor_execute", record)

    return _count
