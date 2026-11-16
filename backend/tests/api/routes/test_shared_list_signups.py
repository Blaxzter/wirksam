"""The organisers' side of the guests on a list: the sign-ups table, removing
sign-ups, and the preview of the public page.

The cast, all in ``test_event``: ``test_event_admin_user`` is an event admin,
``test_user`` a member put in charge of a task where a test needs it. Both
clocks are frozen at 1 June 2026, so the 11 June shifts are ahead and
``test_shift`` (24 May) is over.
"""

import datetime as dt
import uuid
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.routes import shared_list_guests as routes
from app.core.config import settings
from app.crud.booking_reminder import booking_reminder as crud_reminder
from app.logic.shared_lists import removal
from app.logic.shared_lists.erase import anonymise
from app.logic.shared_lists.guest_mail import GuestMail
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.event import Event
from app.models.shared_list import SharedList, SharedListGuest
from app.models.shift import Shift
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User
from app.schemas.booking_reminder import ReminderOffsetEntry
from tests.fixtures.client import act_as
from tests.fixtures.guest_signups import (
    add_shift,
    configure_smtp,
    disable_smtp,
    freeze_clocks,
    pooled_family,
)
from tests.fixtures.shared_lists import (
    CountQueries,
    ListGuest,
    ListGuestFactory,
    SharedListFactory,
)

API = "/api/v1"


@pytest.fixture(autouse=True)
def _clocks(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_clocks(monkeypatch)
    disable_smtp(monkeypatch)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[GuestMail]:
    sent: list[GuestMail] = []

    async def _record(mail: GuestMail) -> bool:
        sent.append(mail)
        return True

    monkeypatch.setattr(routes, "send_guest_mail", _record)
    return sent


@pytest_asyncio.fixture
async def other_task(db_session: AsyncSession, test_event: Event) -> Task:
    task = Task(
        name="Grill",
        start_date=dt.date(2026, 6, 11),
        end_date=dt.date(2026, 6, 11),
        status="published",
        event_id=test_event.id,
    )
    db_session.add(task)
    await db_session.flush()
    return task


@pytest_asyncio.fixture
async def bar_shift(db_session: AsyncSession, test_task: Task) -> Shift:
    return await add_shift(db_session, test_task, max_bookings=5)


@pytest_asyncio.fixture
async def grill_shift(db_session: AsyncSession, other_task: Task) -> Shift:
    return await add_shift(db_session, other_task, start=dt.time(14), end=dt.time(16))


@pytest_asyncio.fixture
async def two_task_list(
    make_shared_list: SharedListFactory, test_task: Task, other_task: Task
) -> SharedList:
    return await make_shared_list(tasks=[test_task, other_task])


async def _in_charge(db: AsyncSession, task: Task, user: User) -> None:
    db.add(TaskManager(task_id=task.id, user_id=user.id))
    await db.flush()


def _code(response: Response) -> str:
    return response.json()["code"]


async def _signups(
    client: AsyncClient, shared_list: SharedList, **params: Any
) -> Response:
    return await client.get(
        f"{API}/shared-lists/{shared_list.id}/signups", params=params
    )


async def _remove(
    client: AsyncClient, shared_list: SharedList, **body: Any
) -> Response:
    return await client.post(
        f"{API}/shared-lists/{shared_list.id}/signups/remove", json=body
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("as_event_admin")
class TestSignupsTable:
    async def test_an_admin_sees_every_sign_up_with_contact_data(
        self,
        async_client: AsyncClient,
        two_task_list: SharedList,
        make_list_guest: ListGuestFactory,
        bar_shift: Shift,
        grill_shift: Shift,
    ) -> None:
        anna = await make_list_guest(
            two_task_list,
            name="Anna",
            email="anna@example.org",
            phone="0170 1",
            shifts=[bar_shift],
        )
        await make_list_guest(two_task_list, name="Bert", shifts=[grill_shift])

        response = await _signups(async_client, two_task_list)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert body["hidden_count"] == 0
        assert body["can_erase"] is True
        by_name = {row["name"]: row for row in body["items"]}
        assert by_name["Anna"]["email"] == "anna@example.org"
        assert by_name["Anna"]["phone"] == "0170 1"
        assert by_name["Anna"]["booking_id"] == str(anna.bookings[0].id)
        assert by_name["Anna"]["task_name"] == "Pfingsten 2026"
        assert by_name["Anna"]["shift_date"] == "2026-06-11"
        assert by_name["Anna"]["can_remove"] is True
        assert by_name["Anna"]["erased"] is False
        assert by_name["Bert"]["email"] is None

    async def test_sorting_searching_and_paging(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
    ) -> None:
        early = await add_shift(db_session, test_task, start=dt.time(8), end=dt.time(9))
        untimed = await add_shift(db_session, test_task, start=None, end=None)
        late = await add_shift(
            db_session, test_task, start=dt.time(18), end=dt.time(19)
        )
        signed: list[ListGuest] = []
        for minute, (name, shift) in enumerate(
            [("Cleo", early), ("anton", late), ("Berta", untimed)]
        ):
            guest = await make_list_guest(
                test_shared_list,
                name=name,
                email=f"{name.lower()}@example.org",
                shifts=[shift],
            )
            guest.bookings[0].created_at = dt.datetime(2026, 6, 1, 6, minute)
            db_session.add(guest.bookings[0])
            signed.append(guest)
        await db_session.flush()

        async def names(**params: Any) -> list[str]:
            body = (await _signups(async_client, test_shared_list, **params)).json()
            return [row["name"] for row in body["items"]]

        assert await names() == ["Berta", "anton", "Cleo"]
        assert await names(sort_dir="asc") == ["Cleo", "anton", "Berta"]
        assert await names(sort_by="name") == ["anton", "Berta", "Cleo"]
        assert await names(sort_by="name", sort_dir="desc") == [
            "Cleo",
            "Berta",
            "anton",
        ]
        assert await names(sort_by="shift_start") == ["Berta", "Cleo", "anton"]
        assert await names(sort_by="shift_start", sort_dir="desc") == [
            "anton",
            "Cleo",
            "Berta",
        ]
        assert await names(q="ANT") == ["anton"]
        assert await names(q="berta@") == ["Berta"]
        assert await names(q="%") == []
        page = (
            await _signups(
                async_client, test_shared_list, sort_by="name", skip=1, limit=1
            )
        ).json()
        assert (page["total"], [row["name"] for row in page["items"]]) == (3, ["Berta"])

    async def test_possible_duplicates_and_erased_guests(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        bar_shift: Shift,
        grill_shift: Shift,
    ) -> None:
        first = await make_shared_list(ask_email="off")
        other_list = await make_shared_list(ask_email="off", title="Andere")
        await make_list_guest(first, name="Anna Gast", shifts=[bar_shift])
        # Through another list, typed differently: still the same name.
        await make_list_guest(other_list, name="anna gast", shifts=[bar_shift])
        erased = await make_list_guest(first, name="Erika", shifts=[bar_shift])
        await anonymise(
            db_session, user_ids=[erased.user.id], now=dt.datetime(2026, 6, 1)
        )

        body = (await _signups(async_client, first, sort_by="name")).json()

        assert [
            (r["name"], r["possible_duplicate"], r["erased"]) for r in body["items"]
        ] == [
            ("Anna Gast", True, False),
            (None, False, True),
        ]

    async def test_counts_what_a_confirmed_address_pools(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        bar_shift: Shift,
    ) -> None:
        """Erasing a guest account takes every sign-up pooled in it, perhaps
        other people's, so the table says how many there are beside each. A
        chain is one person's, and counts nothing."""
        later = await add_shift(
            db_session, test_task, start=dt.time(14), end=dt.time(16)
        )
        await pooled_family(
            db_session, test_shared_list, make_list_guest, bar_shift, later
        )
        await make_list_guest(
            test_shared_list,
            name="Anna Kette",
            email="anna@example.org",
            shifts=[bar_shift, later],
        )

        body = (await _signups(async_client, test_shared_list, sort_by="name")).json()

        assert [(row["name"], row["pooled_signups"]) for row in body["items"]] == [
            ("Anna Kette", 0),
            ("Anna Kette", 0),
            ("Maria Muster", 1),
            ("Tom Muster", 1),
        ]

    async def test_a_task_moved_away_takes_its_sign_ups_along(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        bar_shift: Shift,
        test_private_event: Event,
    ) -> None:
        await make_list_guest(test_shared_list, shifts=[bar_shift])
        test_task.event_id = test_private_event.id
        db_session.add(test_task)
        await db_session.flush()
        body = (await _signups(async_client, test_shared_list)).json()
        assert body["total"] == 0

    async def test_switched_off(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        test_shared_list: SharedList,
    ) -> None:
        monkeypatch.setattr(settings, "SHARED_LISTS_ENABLED", False)
        for response in (
            await _signups(async_client, test_shared_list),
            await _remove(
                async_client, test_shared_list, booking_ids=[str(uuid.uuid4())]
            ),
            await async_client.get(f"{API}/shared-lists/{test_shared_list.id}/preview"),
        ):
            assert response.status_code == 404
            assert _code(response) == "shared_list.disabled"


@pytest.mark.asyncio
class TestPeopleInCharge:
    async def test_see_only_the_sign_ups_on_their_tasks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        two_task_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_user: User,
        bar_shift: Shift,
        grill_shift: Shift,
    ) -> None:
        await _in_charge(db_session, test_task, test_user)
        await make_list_guest(
            two_task_list, name="Anna", email="a@example.org", shifts=[bar_shift]
        )
        await make_list_guest(
            two_task_list, name="Bert", email="b@example.org", shifts=[grill_shift]
        )
        await make_list_guest(two_task_list, name="Cora", shifts=[grill_shift])

        body = (await _signups(async_client, two_task_list)).json()

        assert [(r["name"], r["email"]) for r in body["items"]] == [
            ("Anna", "a@example.org")
        ]
        assert body["total"] == 1
        assert body["hidden_count"] == 2
        assert body["can_erase"] is False
        # Searching does not reach past what they may see.
        assert (await _signups(async_client, two_task_list, q="b@example")).json()[
            "total"
        ] == 0

    async def test_an_unknown_list(self, async_client: AsyncClient) -> None:
        response = await async_client.get(f"{API}/shared-lists/{uuid.uuid4()}/signups")
        assert response.status_code == 404
        assert _code(response) == "shared_list.not_found"

    async def test_outsiders_and_plain_members_do_not_see_the_list(
        self,
        app: FastAPI,
        async_client: AsyncClient,
        test_shared_list: SharedList,
        test_outsider_user: User,
    ) -> None:
        response = await _signups(async_client, test_shared_list)
        assert response.status_code == 404
        assert _code(response) == "shared_list.not_found"
        with act_as(app, test_outsider_user):
            response = await _signups(async_client, test_shared_list)
        assert response.status_code == 404


@pytest.mark.asyncio
class TestRemoval:
    async def _reminder_statuses(self, db: AsyncSession, booking: Booking) -> list[str]:
        rows = await db.execute(
            select(col(BookingReminder.status)).where(
                col(BookingReminder.booking_id) == booking.id
            )
        )
        return list(rows.scalars())

    @pytest.mark.usefixtures("as_event_admin")
    async def test_takes_a_guest_off_and_tells_them(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_event: Event,
        outbox: list[GuestMail],
    ) -> None:
        configure_smtp(monkeypatch)
        one = await add_shift(db_session, test_task)
        two = await add_shift(db_session, test_task, day=dt.date(2026, 6, 12))
        signed = await make_list_guest(
            test_shared_list,
            name="Gerd",
            email="gerd@example.org",
            language="en",
            shifts=[one, two],
        )
        for booking, shift in zip(signed.bookings, (one, two), strict=True):
            await crud_reminder.replace_for_booking(
                db_session,
                booking_id=booking.id,
                user_id=signed.user.id,
                shift_id=shift.id,
                entries=[ReminderOffsetEntry(offset_minutes=1440, channels=["email"])],
                slot_start=dt.datetime.combine(shift.date, dt.time(10)),
                zone=test_event.timezone,
            )

        response = await _remove(
            async_client,
            test_shared_list,
            booking_ids=[str(b.id) for b in signed.bookings],
        )

        assert response.status_code == 200
        body = response.json()
        assert body == {
            "removed": [str(b.id) for b in signed.bookings],
            "erased_guests": 0,
            "also_removed": 0,
            "skipped": [],
        }
        for booking in signed.bookings:
            await db_session.refresh(booking)
            assert booking.status == "cancelled"
            assert await self._reminder_statuses(db_session, booking) == ["cancelled"]
        [mail] = outbox
        assert (mail.kind, mail.to, mail.language) == (
            "removed",
            "gerd@example.org",
            "en",
        )
        assert [s.date for s in mail.shifts] == [
            dt.date(2026, 6, 11),
            dt.date(2026, 6, 12),
        ]

    @pytest.mark.usefixtures("as_event_admin")
    async def test_without_notify_nobody_is_told(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        bar_shift: Shift,
        outbox: list[GuestMail],
    ) -> None:
        configure_smtp(monkeypatch)
        signed = await make_list_guest(
            test_shared_list, email="spam@example.org", shifts=[bar_shift]
        )
        response = await _remove(
            async_client,
            test_shared_list,
            booking_ids=[str(signed.bookings[0].id)],
            notify=False,
        )
        assert response.json()["removed"] == [str(signed.bookings[0].id)]
        assert outbox == []

    @pytest.mark.usefixtures("as_event_admin")
    async def test_every_reason_to_skip(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        bar_shift: Shift,
        test_shift: Shift,
        test_booking: Booking,
    ) -> None:
        here = await make_shared_list()
        elsewhere = await make_shared_list(title="Andere")
        other_list = await make_list_guest(elsewhere, shifts=[bar_shift])
        worked = await make_list_guest(here, shifts=[test_shift])
        undone = await make_list_guest(here, shifts=[bar_shift])
        undone.bookings[0].status = "cancelled"
        db_session.add(undone.bookings[0])
        await db_session.flush()
        unknown = uuid.uuid4()

        response = await _remove(
            async_client,
            here,
            booking_ids=[
                str(other_list.bookings[0].id),
                str(unknown),
                str(undone.bookings[0].id),
                # A member's booking, made in the app.
                str(test_booking.id),
                str(worked.bookings[0].id),
            ],
        )

        assert response.json() == {
            "removed": [],
            "erased_guests": 0,
            "also_removed": 0,
            "skipped": [
                {
                    "id": str(other_list.bookings[0].id),
                    "code": "shared_list.signup_not_found",
                },
                {"id": str(unknown), "code": "shared_list.signup_not_found"},
                {
                    "id": str(undone.bookings[0].id),
                    "code": "shared_list.signup_not_found",
                },
                {"id": str(test_booking.id), "code": "shared_list.signup_not_found"},
                {"id": str(worked.bookings[0].id), "code": "booking.shift_over"},
            ],
        }
        await db_session.refresh(worked.bookings[0])
        assert worked.bookings[0].status == "confirmed"

    async def test_a_person_in_charge_removes_only_on_their_tasks(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        two_task_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_user: User,
        bar_shift: Shift,
        grill_shift: Shift,
    ) -> None:
        await _in_charge(db_session, test_task, test_user)
        mine = await make_list_guest(two_task_list, shifts=[bar_shift])
        theirs = await make_list_guest(two_task_list, shifts=[grill_shift])
        response = await _remove(
            async_client,
            two_task_list,
            booking_ids=[str(mine.bookings[0].id), str(theirs.bookings[0].id)],
        )
        assert response.json() == {
            "removed": [str(mine.bookings[0].id)],
            "erased_guests": 0,
            "also_removed": 0,
            "skipped": [
                {"id": str(theirs.bookings[0].id), "code": "shared_list.forbidden"}
            ],
        }

    async def test_only_event_admins_erase(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        test_user: User,
        bar_shift: Shift,
    ) -> None:
        await _in_charge(db_session, test_task, test_user)
        signed = await make_list_guest(test_shared_list, shifts=[bar_shift])
        response = await _remove(
            async_client,
            test_shared_list,
            booking_ids=[str(signed.bookings[0].id)],
            erase=True,
        )
        assert response.status_code == 403
        assert _code(response) == "shared_list.forbidden"

    @pytest.mark.usefixtures("as_event_admin")
    async def test_an_admin_erases_the_guests_touched(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        bar_shift: Shift,
        test_shift: Shift,
        outbox: list[GuestMail],
    ) -> None:
        configure_smtp(monkeypatch)
        gone = await make_list_guest(
            test_shared_list, email="gone@example.org", shifts=[bar_shift]
        )
        kept = await make_list_guest(
            test_shared_list,
            name="Worked",
            email="kept@example.org",
            shifts=[test_shift],
        )
        gone_id = gone.user.id
        response = await _remove(
            async_client,
            test_shared_list,
            booking_ids=[str(gone.bookings[0].id), str(kept.bookings[0].id)],
            erase=True,
        )
        assert response.json() == {
            "removed": [str(gone.bookings[0].id)],
            "erased_guests": 2,
            "also_removed": 0,
            "skipped": [{"id": str(kept.bookings[0].id), "code": "booking.shift_over"}],
        }
        assert outbox == []
        db_session.expunge_all()
        assert await db_session.get(User, gone_id) is None
        anonymous = await db_session.get(User, kept.user.id)
        assert anonymous is not None and anonymous.name is None
        contact = await db_session.scalar(
            select(SharedListGuest).where(col(SharedListGuest.user_id) == kept.user.id)
        )
        assert contact is not None and contact.email is None

    @pytest.mark.usefixtures("as_event_admin")
    async def test_erasing_a_guest_account_takes_what_it_pools_along(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        bar_shift: Shift,
    ) -> None:
        """Tom's sign-up was confirmed into Maria's guest account: erasing his
        data erases the account, and Maria's sign-up goes too. The result
        counts it, so the organiser is not told one went when two did."""
        later = await add_shift(
            db_session, test_task, start=dt.time(14), end=dt.time(16)
        )
        maria, tom = await pooled_family(
            db_session, test_shared_list, make_list_guest, bar_shift, later
        )
        maria_booking, tom_booking = maria.bookings[0].id, tom.bookings[0].id

        response = await _remove(
            async_client, test_shared_list, booking_ids=[str(tom_booking)], erase=True
        )

        assert response.json() == {
            "removed": [str(tom_booking)],
            "erased_guests": 1,
            "also_removed": 1,
            "skipped": [],
        }
        db_session.expunge_all()
        assert await db_session.get(Booking, maria_booking) is None
        assert await db_session.get(Booking, tom_booking) is None

    @pytest.mark.usefixtures("as_event_admin")
    async def test_everything_since_a_moment(
        self,
        async_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        bar_shift: Shift,
    ) -> None:
        signed: list[Booking] = []
        for minute in range(4):
            guest = await make_list_guest(test_shared_list, shifts=[bar_shift])
            guest.bookings[0].created_at = dt.datetime(2026, 6, 1, 5, minute)
            db_session.add(guest.bookings[0])
            signed.append(guest.bookings[0])
        await db_session.flush()
        monkeypatch.setattr(removal, "CREATED_SINCE_MAX", 2)

        first = await _remove(
            async_client,
            test_shared_list,
            created_since="2026-06-01T05:01:00Z",
            notify=False,
        )
        assert first.json()["removed"] == [str(signed[1].id), str(signed[2].id)]
        second = await _remove(
            async_client,
            test_shared_list,
            created_since="2026-06-01T05:01:00",
            notify=False,
        )
        assert second.json()["removed"] == [str(signed[3].id)]
        await db_session.refresh(signed[0])
        assert signed[0].status == "confirmed"

    @pytest.mark.usefixtures("as_event_admin")
    async def test_everything_since_a_moment_leaves_a_task_moved_away_out(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        two_task_list: SharedList,
        make_list_guest: ListGuestFactory,
        other_task: Task,
        test_private_event: Event,
        bar_shift: Shift,
        grill_shift: Shift,
    ) -> None:
        """As in the table of sign-ups and its counts: the moved task took its
        sign-ups along, so they are neither removed nor reported as skipped."""
        stays = await make_list_guest(two_task_list, shifts=[bar_shift])
        await make_list_guest(two_task_list, shifts=[grill_shift])
        other_task.event_id = test_private_event.id
        db_session.add(other_task)
        await db_session.flush()

        response = await _remove(
            async_client,
            two_task_list,
            created_since="2026-01-01T00:00:00",
            notify=False,
        )

        assert response.json() == {
            "removed": [str(stays.bookings[0].id)],
            "erased_guests": 0,
            "also_removed": 0,
            "skipped": [],
        }

    @pytest.mark.usefixtures("as_event_admin")
    async def test_a_sign_up_that_is_no_guests_is_left_alone(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_user: User,
        bar_shift: Shift,
    ) -> None:
        """A booking through the list that a member holds, as one taken over
        by an account would be: an organiser may neither cancel nor erase it,
        and the account stays."""
        booking = Booking(
            shift_id=bar_shift.id,
            user_id=test_user.id,
            status="confirmed",
            shared_list_id=test_shared_list.id,
        )
        db_session.add(booking)
        await db_session.flush()

        response = await _remove(
            async_client, test_shared_list, booking_ids=[str(booking.id)], erase=True
        )

        assert response.json() == {
            "removed": [],
            "erased_guests": 0,
            "also_removed": 0,
            "skipped": [
                {"id": str(booking.id), "code": "shared_list.signup_not_guest"}
            ],
        }
        await db_session.refresh(booking)
        assert booking.status == "confirmed"
        await db_session.refresh(test_user)
        assert test_user.name is not None

    @pytest.mark.usefixtures("as_event_admin")
    @pytest.mark.parametrize("mode", [{"notify": False}, {"erase": True}])
    async def test_more_sign_ups_cost_no_more_statements(
        self,
        mode: dict[str, bool],
        async_client: AsyncClient,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        bar_shift: Shift,
        count_queries: CountQueries,
    ) -> None:
        """The clean-up after a wave of fake sign-ups removes hundreds at once:
        the guests are locked, their reminders cancelled and their data
        erased a fixed number of statements, not one or more per guest."""

        async def remove(guests: int) -> list[str]:
            signed = [
                await make_list_guest(
                    test_shared_list, email=f"wave{n}@example.org", shifts=[bar_shift]
                )
                for n in range(guests)
            ]
            ids = [str(guest.bookings[0].id) for guest in signed]
            with count_queries() as statements:
                response = await _remove(
                    async_client, test_shared_list, booking_ids=ids, **mode
                )
            assert response.json()["removed"] == ids
            return statements

        one = await remove(1)
        five = await remove(5)
        assert one
        assert len(five) == len(one)

    @pytest.mark.usefixtures("as_event_admin")
    @pytest.mark.parametrize(
        "body",
        [
            {},
            {
                "booking_ids": [str(uuid.UUID(int=1))],
                "created_since": "2026-06-01T05:00:00",
            },
        ],
    )
    async def test_exactly_one_selector(
        self,
        async_client: AsyncClient,
        test_shared_list: SharedList,
        body: dict[str, Any],
    ) -> None:
        response = await _remove(async_client, test_shared_list, **body)
        assert response.status_code == 422
        assert _code(response) == "shared_list.remove_selector"


@pytest.mark.asyncio
class TestPreview:
    @pytest.mark.usefixtures("as_event_admin")
    async def test_shows_the_public_page_without_counting_a_view(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        bar_shift: Shift,
    ) -> None:
        response = await async_client.get(
            f"{API}/shared-lists/{test_shared_list.id}/preview"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == test_shared_list.code
        assert [s["id"] for day in body["days"] for s in day["shifts"]] == [
            str(bar_shift.id)
        ]
        await db_session.refresh(test_shared_list)
        assert test_shared_list.view_count == 0

    async def test_not_for_members_without_a_task_on_it(
        self, async_client: AsyncClient, test_shared_list: SharedList
    ) -> None:
        response = await async_client.get(
            f"{API}/shared-lists/{test_shared_list.id}/preview"
        )
        assert response.status_code == 404
        assert _code(response) == "shared_list.not_found"
