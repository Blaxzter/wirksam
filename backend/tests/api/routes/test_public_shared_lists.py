"""The public side of shared lists: the page, signing up, and the manage link.

Driven anonymously through ``unauthenticated_client``. The confirmation mail
is recorded instead of sent (``send_guest_mail`` is imported by name in the
route module), and both clocks are frozen at 1 June 2026, before every shift
added here (``tests/fixtures/guest_signups.py``).
"""

import datetime as dt
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.api.routes import public_shared_lists as routes
from app.core.config import settings
from app.core.rate_limit import (
    guest_ip_limiter,
    guest_link_miss_limiter,
    guest_manage_limiter,
    guest_pass_status_limiter,
    shared_list_miss_limiter,
    voucher_pass_limiter,
)
from app.crud.shared_list import shared_list as crud_shared_list
from app.logic.shared_lists import guest_account, guest_quota, guest_tokens
from app.logic.shared_lists.guest_mail import GuestMail
from app.models.booking import Booking
from app.models.booking_reminder import BookingReminder
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.shared_list import (
    GuestActivityLog,
    GuestMailSuppression,
    SharedList,
    SharedListGuest,
    ShowNames,
)
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.voucher import VoucherEntry
from tests.fixtures.client import act_as
from tests.fixtures.guest_signups import (
    add_shift,
    configure_smtp,
    confirm_address,
    disable_smtp,
    freeze_clocks,
    signup_body,
)
from tests.fixtures.shared_lists import ListGuest, ListGuestFactory, SharedListFactory

API = "/api/v1/public"
#: Over by the frozen clocks, so a shift that day has earned.
MAY = dt.date(2026, 5, 20)


@pytest.fixture(autouse=True)
def _clocks(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_clocks(monkeypatch)
    disable_smtp(monkeypatch)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[GuestMail]:
    """The mails the routes queued, instead of sending them."""
    sent: list[GuestMail] = []

    async def _record(mail: GuestMail) -> bool:
        sent.append(mail)
        return True

    monkeypatch.setattr(routes, "send_guest_mail", _record)
    return sent


@pytest.fixture
def limits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """The daily ceilings (and the rate limiters) are off under TESTING."""
    monkeypatch.setattr(settings, "TESTING", False)


@pytest_asyncio.fixture
async def shift(db_session: AsyncSession, test_task: Task) -> Shift:
    """11 June, 10-12, two places."""
    return await add_shift(db_session, test_task)


def _code(response: Response) -> str:
    return response.json()["code"]


async def _sign_up(
    client: AsyncClient, shared_list: SharedList, shift: Shift, **fields: Any
) -> Response:
    return await client.post(
        f"{API}/shared-lists/{shared_list.code}/signups",
        json=signup_body(shift, **fields),
    )


async def _signed_up(
    client: AsyncClient, shared_list: SharedList, shift: Shift, **fields: Any
) -> dict[str, Any]:
    response = await _sign_up(client, shared_list, shift, **fields)
    assert response.status_code == 201, response.text
    return response.json()


async def _guest_of(db: AsyncSession, booking_id: str) -> tuple[User, SharedListGuest]:
    booking = await db.get(Booking, uuid.UUID(booking_id))
    assert booking is not None
    user = await db.get(User, booking.user_id)
    guest = await db.scalar(
        select(SharedListGuest).where(col(SharedListGuest.user_id) == booking.user_id)
    )
    assert user is not None and guest is not None
    return user, guest


# ── The public page ───────────────────────────────────────────────


@pytest.mark.asyncio
class TestPublicPage:
    async def test_shows_the_list_and_nothing_personal(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        shift: Shift,
        test_event: Event,
    ) -> None:
        test_shared_list.intro = "Komm vorbei!\n<b>https://example.org</b>"
        test_shared_list.share_note = "WhatsApp Gruppe"
        db_session.add(test_shared_list)
        await db_session.flush()

        response = await unauthenticated_client.get(
            f"{API}/shared-lists/{test_shared_list.code}"
        )

        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert set(body) == {
            "code",
            "title",
            "intro",
            "status",
            "event",
            "ask_email",
            "ask_phone",
            "show_names",
            "max_per_person",
            "days",
            "retention_days",
        }
        assert body["intro"] == "Komm vorbei!\n<b>https://example.org</b>"
        assert body["status"] == "live"
        assert body["event"] == {
            "name": test_event.name,
            "start_date": "2026-06-10",
            "end_date": "2026-06-14",
            "timezone": test_event.timezone,
        }
        [day] = body["days"]
        assert day["date"] == "2026-06-11"
        [listed] = day["shifts"]
        assert listed["id"] == str(shift.id)
        assert listed["capacity"] == 2
        assert listed["free"] == 2
        assert listed["full"] is False
        assert listed["names"] == []
        assert listed["others_count"] == 0
        assert listed["vouchers"] == 0
        assert "WhatsApp" not in response.text
        assert "description" not in listed

    async def test_started_shifts_are_not_offered(
        self,
        unauthenticated_client: AsyncClient,
        test_shared_list: SharedList,
        test_shift: Shift,
        shift: Shift,
    ) -> None:
        """``test_shift`` was on 24 May."""
        body = (
            await unauthenticated_client.get(
                f"{API}/shared-lists/{test_shared_list.code}"
            )
        ).json()
        listed = [s["id"] for day in body["days"] for s in day["shifts"]]
        assert listed == [str(shift.id)]

    @pytest.mark.parametrize(
        ("status", "shown"), [("paused", "paused"), ("ended", "closed")]
    )
    async def test_a_list_that_is_not_live_offers_nothing(
        self,
        unauthenticated_client: AsyncClient,
        make_shared_list: SharedListFactory,
        shift: Shift,
        status: Any,
        shown: str,
    ) -> None:
        shared_list = await make_shared_list(status=status)
        body = (
            await unauthenticated_client.get(f"{API}/shared-lists/{shared_list.code}")
        ).json()
        assert body["status"] == shown
        assert body["days"] == []

    async def test_an_unpublished_event_closes_the_list(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_event: Event,
        shift: Shift,
    ) -> None:
        test_event.status = "draft"
        db_session.add(test_event)
        await db_session.flush()
        body = (
            await unauthenticated_client.get(
                f"{API}/shared-lists/{test_shared_list.code}"
            )
        ).json()
        assert body["status"] == "closed"
        assert body["days"] == []

    async def test_counts_views_only_while_live(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        shift: Shift,
    ) -> None:
        url = f"{API}/shared-lists/{test_shared_list.code}"
        await unauthenticated_client.get(url)
        await unauthenticated_client.get(url)
        await db_session.refresh(test_shared_list)
        assert test_shared_list.view_count == 2

        test_shared_list.status = "paused"
        db_session.add(test_shared_list)
        await db_session.flush()
        await unauthenticated_client.get(url)
        await db_session.refresh(test_shared_list)
        assert test_shared_list.view_count == 2

    async def test_unknown_and_rotated_codes_are_not_found(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
    ) -> None:
        old = test_shared_list.code
        await crud_shared_list.rotate_code(
            db_session, shared_list=test_shared_list, now=dt.datetime(2026, 6, 1)
        )
        for code in ("unknowncode1", old):
            response = await unauthenticated_client.get(f"{API}/shared-lists/{code}")
            assert response.status_code == 404
            assert _code(response) == "shared_list.not_found"
        new = await unauthenticated_client.get(
            f"{API}/shared-lists/{test_shared_list.code}"
        )
        assert new.status_code == 200

    async def test_misses_are_rate_limited(
        self, unauthenticated_client: AsyncClient, limits_on: None
    ) -> None:
        shared_list_miss_limiter.reset()
        try:
            for _ in range(20):
                response = await unauthenticated_client.get(
                    f"{API}/shared-lists/nothinghere1"
                )
                assert response.status_code == 404
            response = await unauthenticated_client.get(
                f"{API}/shared-lists/nothinghere1"
            )
            assert response.status_code == 429
            assert _code(response) == "shared_list.rate_limited"
            assert "retry-after" in response.headers
        finally:
            shared_list_miss_limiter.reset()

    async def test_switched_off(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        test_shared_list: SharedList,
        shift: Shift,
    ) -> None:
        """The list closes; whoever signed up before keeps their page, which
        every mail about their shifts still links to."""
        token = (await _signed_up(unauthenticated_client, test_shared_list, shift))[
            "guest_token"
        ]
        monkeypatch.setattr(settings, "SHARED_LISTS_ENABLED", False)
        page = await unauthenticated_client.get(
            f"{API}/shared-lists/{test_shared_list.code}"
        )
        signup = await _sign_up(unauthenticated_client, test_shared_list, shift)
        # Before the form is validated: an off switch is not a 422.
        incomplete = await unauthenticated_client.post(
            f"{API}/shared-lists/{test_shared_list.code}/signups", json={}
        )
        for response in (page, signup, incomplete):
            assert response.status_code == 404
            assert _code(response) == "shared_list.disabled"

        manage = await unauthenticated_client.post(
            f"{API}/guest-signups/manage", json={"token": token}
        )
        assert manage.status_code == 200, manage.text
        erase = await unauthenticated_client.post(
            f"{API}/guest-signups/erase", json={"token": token}
        )
        assert erase.status_code == 204

    async def test_a_list_closing_by_hand_stays_live_with_nothing_left(
        self,
        unauthenticated_client: AsyncClient,
        make_shared_list: SharedListFactory,
        test_shift: Shift,
    ) -> None:
        """Only ``test_shift`` (24 May, over) is on it."""
        shared_list = await make_shared_list(ends_mode="manual", show_names="first")
        body = (
            await unauthenticated_client.get(f"{API}/shared-lists/{shared_list.code}")
        ).json()
        assert (body["status"], body["days"]) == ("live", [])


@pytest.mark.asyncio
class TestFirstNames:
    """Who the public page names (D12): only guests who were told so when
    they signed up, through whichever list, and only on lists that show
    first names."""

    async def _names(
        self, client: AsyncClient, shared_list: SharedList
    ) -> tuple[list[str], int]:
        body = (await client.get(f"{API}/shared-lists/{shared_list.code}")).json()
        [day] = body["days"]
        [listed] = day["shifts"]
        return listed["names"], listed["others_count"]

    async def test_members_are_never_named(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        shift: Shift,
        test_user: User,
    ) -> None:
        shared_list = await make_shared_list(show_names="first")
        db_session.add(Booking(shift_id=shift.id, user_id=test_user.id))
        await db_session.flush()
        assert await self._names(unauthenticated_client, shared_list) == ([], 1)

    async def test_consent_is_what_the_list_said_at_sign_up(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        shift: Shift,
    ) -> None:
        unnamed_list = await make_shared_list(show_names="none")
        await make_list_guest(unnamed_list, name="Bea Still", shifts=[shift])
        unnamed_list.show_names = "first"
        db_session.add(unnamed_list)
        await db_session.flush()
        assert await self._names(unauthenticated_client, unnamed_list) == ([], 1)

    async def test_a_consenting_guest_is_named_on_every_list_that_shows_names(
        self,
        unauthenticated_client: AsyncClient,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        shift: Shift,
    ) -> None:
        where_she_signed = await make_shared_list(show_names="first")
        another = await make_shared_list(show_names="first", title="Zweite")
        silent = await make_shared_list(show_names="none", title="Dritte")
        await make_list_guest(where_she_signed, name="Carla Maria Weiß", shifts=[shift])

        assert await self._names(unauthenticated_client, another) == (["Carla"], 0)
        assert await self._names(unauthenticated_client, silent) == ([], 0)

    async def test_each_sign_up_is_named_as_itself(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        shift: Shift,
    ) -> None:
        """By the booking's own name, never the guest user's: an account pools
        the sign-ups of everyone who confirmed one address."""
        shared_list = await make_shared_list(show_names="first")
        signed = await make_list_guest(shared_list, name="Carla Weiß", shifts=[shift])
        signed.user.name = "Konto Inhaberin"
        db_session.add(signed.user)
        await db_session.flush()
        assert await self._names(unauthenticated_client, shared_list) == (["Carla"], 0)

    async def test_an_erased_guest_is_never_named(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        shift: Shift,
    ) -> None:
        shared_list = await make_shared_list(show_names="first")
        signed = await make_list_guest(shared_list, name="Dora", shifts=[shift])
        signed.guest.erased_at = dt.datetime(2026, 6, 1)
        db_session.add(signed.guest)
        await db_session.flush()
        assert await self._names(unauthenticated_client, shared_list) == ([], 1)


# ── Signing up ────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSignUp:
    async def test_creates_a_guest_with_exactly_these_fields(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        shift: Shift,
        test_event: Event,
        outbox: list[GuestMail],
    ) -> None:
        shared_list = await make_shared_list(show_names="first", ask_phone="optional")

        body = await _signed_up(
            unauthenticated_client,
            shared_list,
            shift,
            name="  Anna   Müller ",
            email=" Anna@Example.ORG ",
            phone=" +49 170 123 ",
            language="en",
            show_names="first",
        )

        user, guest = await _guest_of(db_session, body["booking_id"])
        assert user.subject.startswith("listguest|")
        assert user.is_list_guest is True
        assert user.email is None
        assert user.password_hash is None
        assert user.name == "Anna Müller"
        assert user.phone_number == "+49 170 123"
        assert user.preferred_language == "en"
        assert user.default_reminder_offsets == []
        assert (user.notify_email, user.notify_push, user.notify_telegram) == (
            False,
            False,
            False,
        )
        assert user.roles == []
        assert user.approval_status == "approved"
        assert user.is_active is True
        assert guest.email == "anna@example.org"
        assert guest.event_id == test_event.id
        assert guest.shared_list_id == shared_list.id
        assert guest.confirmed_at is None
        assert guest.manage_nonce is not None
        assert guest.last_signup_at == dt.datetime(2026, 6, 1, 6, 0)
        booking = await db_session.get(Booking, uuid.UUID(body["booking_id"]))
        assert booking is not None
        assert booking.status == "confirmed"
        assert booking.shared_list_id == shared_list.id
        assert booking.show_first_name is True
        assert (booking.guest_name, booking.guest_phone) == (
            "Anna Müller",
            "+49 170 123",
        )
        assert body["email"] == "anna@example.org"
        assert body["date"] == "2026-06-11"
        assert body["shift"]["free"] == 1
        assert body["shift"]["names"] == ["Anna"]
        assert body["remaining"] is None
        assert guest_tokens.manage_token(guest) == body["guest_token"]
        log = (
            await db_session.execute(
                select(GuestActivityLog).where(
                    col(GuestActivityLog.booking_id) == booking.id
                )
            )
        ).scalars()
        assert [(row.kind, row.shared_list_id) for row in log] == [
            ("signup", shared_list.id)
        ]
        # Without SMTP nothing is queued.
        assert outbox == []

    async def test_a_list_that_shows_no_names_keeps_its_guests_unnamed(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        shift: Shift,
    ) -> None:
        body = await _signed_up(
            unauthenticated_client, test_shared_list, shift, show_names="first"
        )
        booking = await db_session.get(Booking, uuid.UUID(body["booking_id"]))
        assert booking is not None
        assert booking.show_first_name is False

    @pytest.mark.parametrize(("seen", "now"), [("none", "first"), ("first", "none")])
    async def test_a_guest_is_named_only_as_the_form_said(
        self,
        seen: ShowNames,
        now: ShowNames,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        shift: Shift,
    ) -> None:
        """The organisers changed the setting while the page was open: a guest
        told nobody would see their name stays unnamed, and one told otherwise
        is not named on a list that has since stopped naming anyone."""
        shared_list = await make_shared_list(show_names=now)

        body = await _signed_up(
            unauthenticated_client, shared_list, shift, show_names=seen
        )

        booking = await db_session.get(Booking, uuid.UUID(body["booking_id"]))
        assert booking is not None
        assert booking.show_first_name is False
        assert body["shift"]["names"] == []

    async def test_the_form_must_say_what_it_showed(
        self,
        unauthenticated_client: AsyncClient,
        test_shared_list: SharedList,
        shift: Shift,
    ) -> None:
        body = signup_body(shift)
        del body["show_names"]
        response = await unauthenticated_client.post(
            f"{API}/shared-lists/{test_shared_list.code}/signups", json=body
        )
        assert response.status_code == 422

    async def test_fields_the_list_does_not_ask_for_are_dropped(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        shift: Shift,
    ) -> None:
        shared_list = await make_shared_list(ask_email="off", ask_phone="off")
        body = await _signed_up(
            unauthenticated_client, shared_list, shift, phone="0170 1234"
        )
        user, guest = await _guest_of(db_session, body["booking_id"])
        assert guest.email is None
        assert user.phone_number is None
        assert body["email"] is None

    async def test_optional_fields_may_stay_empty(
        self,
        unauthenticated_client: AsyncClient,
        make_shared_list: SharedListFactory,
        shift: Shift,
    ) -> None:
        shared_list = await make_shared_list(ask_email="optional", ask_phone="optional")
        body = await _signed_up(
            unauthenticated_client, shared_list, shift, email="", phone="  "
        )
        assert body["email"] is None
        assert body["show_manage_link"] is True

    @pytest.mark.parametrize(
        ("fields", "location"),
        [
            ({"name": "A"}, "name"),
            ({"name": "Ann\x00a"}, "name"),
            ({"email": "not-an-address"}, "email"),
            ({"phone": "call me"}, "phone"),
        ],
    )
    async def test_malformed_fields_are_a_422(
        self,
        unauthenticated_client: AsyncClient,
        make_shared_list: SharedListFactory,
        shift: Shift,
        fields: dict[str, str],
        location: str,
    ) -> None:
        shared_list = await make_shared_list(ask_phone="optional")
        response = await _sign_up(unauthenticated_client, shared_list, shift, **fields)
        assert response.status_code == 422
        assert location in response.text


@pytest.mark.asyncio
class TestSignUpRefusals:
    """Each refusal of the sign-up, and that they come in the documented order."""

    async def test_unknown_code(
        self, unauthenticated_client: AsyncClient, shift: Shift
    ) -> None:
        response = await unauthenticated_client.post(
            f"{API}/shared-lists/nothinghere1/signups", json=signup_body(shift)
        )
        assert response.status_code == 404
        assert _code(response) == "shared_list.not_found"

    @pytest.mark.parametrize(
        ("status", "code"),
        [("paused", "shared_list.paused"), ("ended", "shared_list.closed")],
    )
    async def test_a_list_that_is_not_live(
        self,
        unauthenticated_client: AsyncClient,
        make_shared_list: SharedListFactory,
        shift: Shift,
        status: Any,
        code: str,
    ) -> None:
        shared_list = await make_shared_list(status=status)
        # Before the missing address: the list's state comes first.
        response = await _sign_up(
            unauthenticated_client, shared_list, shift, email=None
        )
        assert response.status_code == 409
        assert _code(response) == code

    async def test_an_expired_list(
        self,
        unauthenticated_client: AsyncClient,
        make_shared_list: SharedListFactory,
        shift: Shift,
    ) -> None:
        shared_list = await make_shared_list(
            ends_mode="date", ends_on=dt.date(2026, 5, 31)
        )
        response = await _sign_up(unauthenticated_client, shared_list, shift)
        assert response.status_code == 409
        assert _code(response) == "shared_list.closed"

    async def test_required_fields(
        self,
        unauthenticated_client: AsyncClient,
        make_shared_list: SharedListFactory,
        db_session: AsyncSession,
        test_task: Task,
    ) -> None:
        started = await add_shift(db_session, test_task, day=dt.date(2026, 5, 31))
        await add_shift(db_session, test_task)
        shared_list = await make_shared_list(ask_phone="required")
        # Before the shift: a started shift with no address is still a 422.
        no_email = await _sign_up(
            unauthenticated_client, shared_list, started, email=None
        )
        assert no_email.status_code == 422
        assert _code(no_email) == "shared_list.email_required"
        no_phone = await _sign_up(unauthenticated_client, shared_list, started)
        assert no_phone.status_code == 422
        assert _code(no_phone) == "shared_list.phone_required"

    async def test_shifts_the_list_does_not_offer(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_task: Task,
        test_draft_task: Task,
    ) -> None:
        excluded = await add_shift(db_session, test_task)
        offered = await add_shift(
            db_session, test_task, start=dt.time(14, 0), end=dt.time(16, 0)
        )
        other_task = await add_shift(db_session, test_draft_task)
        shared_list = await make_shared_list(excluded=[excluded])
        for shift in (excluded, other_task):
            response = await _sign_up(unauthenticated_client, shared_list, shift)
            assert response.status_code == 404
            assert _code(response) == "shared_list.shift_not_offered"
        assert (
            await _sign_up(unauthenticated_client, shared_list, offered)
        ).status_code == 201

    async def test_a_started_shift(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
    ) -> None:
        """8:30 on 1 June: the 8:00 shift has started, the untimed one too,
        since its day has begun."""
        await add_shift(db_session, test_task)
        for start, end in ((dt.time(8, 0), dt.time(9, 0)), (None, None)):
            started = await add_shift(
                db_session, test_task, day=dt.date(2026, 6, 1), start=start, end=end
            )
            response = await _sign_up(unauthenticated_client, test_shared_list, started)
            assert response.status_code == 409
            assert _code(response) == "shared_list.shift_started"

    async def test_a_token_that_is_no_chain_of_this_list(
        self,
        unauthenticated_client: AsyncClient,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        shift: Shift,
    ) -> None:
        here = await make_shared_list()
        elsewhere = await make_shared_list(title="Andere Liste")
        other = await make_list_guest(elsewhere, email="b@example.org")
        for token in ("garbage", guest_tokens.manage_token(other.guest)):
            response = await _sign_up(
                unauthenticated_client, here, shift, guest_token=token
            )
            assert response.status_code == 403
            assert _code(response) == "shared_list.guest_token_invalid"

    async def test_the_same_address_twice_on_a_shift_through_any_list(
        self,
        unauthenticated_client: AsyncClient,
        make_shared_list: SharedListFactory,
        shift: Shift,
    ) -> None:
        first = await make_shared_list()
        second = await make_shared_list(title="Zweite")
        await _signed_up(unauthenticated_client, first, shift, email="same@example.org")
        response = await _sign_up(
            unauthenticated_client, second, shift, email="SAME@example.org"
        )
        assert response.status_code == 409
        assert _code(response) == "shared_list.already_signed_up"

    async def test_the_same_chain_twice_on_a_shift(
        self,
        unauthenticated_client: AsyncClient,
        make_shared_list: SharedListFactory,
        shift: Shift,
    ) -> None:
        shared_list = await make_shared_list(ask_email="optional")
        first = await _signed_up(unauthenticated_client, shared_list, shift, email=None)
        response = await _sign_up(
            unauthenticated_client,
            shared_list,
            shift,
            email=None,
            guest_token=first["guest_token"],
        )
        assert response.status_code == 409
        assert _code(response) == "shared_list.already_signed_up"

    async def test_a_full_shift(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
    ) -> None:
        shift = await add_shift(db_session, test_task, max_bookings=1)
        await _signed_up(unauthenticated_client, test_shared_list, shift)
        response = await _sign_up(unauthenticated_client, test_shared_list, shift)
        assert response.status_code == 409
        assert _code(response) == "booking.slot_full"


@pytest.mark.asyncio
class TestChains:
    async def test_a_chain_continues_with_its_token(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
    ) -> None:
        morning = await add_shift(db_session, test_task)
        later = await add_shift(
            db_session, test_task, start=dt.time(14), end=dt.time(16)
        )
        first = await _signed_up(
            unauthenticated_client, test_shared_list, morning, email="c@example.org"
        )
        second = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            later,
            name="Somebody Else",
            email="other@example.org",
            guest_token=first["guest_token"],
        )
        first_user, _ = await _guest_of(db_session, first["booking_id"])
        second_user, guest = await _guest_of(db_session, second["booking_id"])
        assert first_user.id == second_user.id
        # What the chain stored wins.
        assert second_user.name == "Anna Gast"
        assert second["email"] == "c@example.org"
        assert guest.email == "c@example.org"
        assert second["guest_token"] == first["guest_token"]
        # Only the first sign-up of a chain may show the manage link.
        assert second["show_manage_link"] is False

    async def test_each_sign_up_keeps_its_own_consent_and_the_chains_person(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_task: Task,
    ) -> None:
        shared_list = await make_shared_list(show_names="first", ask_phone="optional")
        first = await _signed_up(
            unauthenticated_client,
            shared_list,
            await add_shift(db_session, test_task),
            phone="0170 1",
            show_names="first",
        )
        second = await _signed_up(
            unauthenticated_client,
            shared_list,
            await add_shift(db_session, test_task, day=dt.date(2026, 6, 12)),
            name="Jemand Anderes",
            phone="0999 9",
            show_names="none",
            guest_token=first["guest_token"],
        )

        people = [
            (b.show_first_name, b.guest_name, b.guest_phone)
            for b in [
                await db_session.get(Booking, uuid.UUID(body["booking_id"]))
                for body in (first, second)
            ]
            if b is not None
        ]
        assert people == [
            (True, "Anna Gast", "0170 1"),
            (False, "Anna Gast", "0170 1"),
        ]

    async def test_a_chain_cannot_take_overlapping_shifts(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
    ) -> None:
        one = await add_shift(db_session, test_task)
        overlapping = await add_shift(
            db_session, test_task, start=dt.time(11), end=dt.time(13)
        )
        first = await _signed_up(unauthenticated_client, test_shared_list, one)
        response = await _sign_up(
            unauthenticated_client,
            test_shared_list,
            overlapping,
            guest_token=first["guest_token"],
        )
        assert response.status_code == 409
        assert _code(response) == "booking.time_conflict"
        assert response.json()["conflicting_shift"]["id"] == str(one.id)

    async def test_undo_and_sign_again_brings_the_booking_back(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        shift: Shift,
    ) -> None:
        first = await _signed_up(
            unauthenticated_client, test_shared_list, shift, remind=True
        )
        cancelled = await unauthenticated_client.post(
            f"{API}/guest-signups/cancel",
            json={"token": first["guest_token"], "booking_id": first["booking_id"]},
        )
        assert cancelled.status_code == 200
        again = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            shift,
            remind=True,
            guest_token=first["guest_token"],
        )
        assert again["booking_id"] == first["booking_id"]
        reminders = (
            (
                await db_session.execute(
                    select(BookingReminder).where(
                        col(BookingReminder.booking_id)
                        == uuid.UUID(first["booking_id"])
                    )
                )
            )
            .scalars()
            .all()
        )
        assert [(r.offset_minutes, r.status, r.channels) for r in reminders] == [
            (1440, "pending", ["email"])
        ]


@pytest.mark.asyncio
class TestReminderAndMail:
    async def _reminders(
        self, db: AsyncSession, booking_id: str
    ) -> list[BookingReminder]:
        rows = await db.execute(
            select(BookingReminder).where(
                col(BookingReminder.booking_id) == uuid.UUID(booking_id)
            )
        )
        return list(rows.scalars())

    async def test_a_reminder_only_when_asked_for_and_with_an_address(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_task: Task,
    ) -> None:
        shared_list = await make_shared_list(ask_email="optional")
        asked = await _signed_up(
            unauthenticated_client,
            shared_list,
            await add_shift(db_session, test_task),
            remind=True,
        )
        not_asked = await _signed_up(
            unauthenticated_client, shared_list, await add_shift(db_session, test_task)
        )
        no_address = await _signed_up(
            unauthenticated_client,
            shared_list,
            await add_shift(db_session, test_task),
            email=None,
            remind=True,
        )
        [reminder] = await self._reminders(db_session, asked["booking_id"])
        assert (reminder.offset_minutes, reminder.channels) == (1440, ["email"])
        # 11 June 10:00 in Berlin, a day before, in UTC.
        assert reminder.remind_at == dt.datetime(2026, 6, 10, 8, 0)
        assert await self._reminders(db_session, not_asked["booking_id"]) == []
        assert await self._reminders(db_session, no_address["booking_id"]) == []

    async def test_one_confirmation_per_chain(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
        test_event: Event,
        outbox: list[GuestMail],
    ) -> None:
        configure_smtp(monkeypatch)
        shift = await add_shift(db_session, test_task)
        first = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            shift,
            name="Eva Gast",
            email="eva@example.org",
            language="en",
        )
        assert first["mail_queued"] is True
        assert first["show_manage_link"] is False
        [mail] = outbox
        assert mail.kind == "confirmation"
        assert mail.to == "eva@example.org"
        assert mail.language == "en"
        assert mail.name == "Eva Gast"
        assert mail.event_name == test_event.name
        # The mail's own link to the same page, which only the mailbox has.
        _, guest = await _guest_of(db_session, first["booking_id"])
        assert mail.token == guest_tokens.mail_token(guest) != first["guest_token"]
        assert [(s.task_name, s.date) for s in mail.shifts] == [
            (test_task.name, dt.date(2026, 6, 11))
        ]

        follow_up = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            await add_shift(db_session, test_task, start=dt.time(14), end=dt.time(16)),
            guest_token=first["guest_token"],
        )
        assert follow_up["mail_queued"] is False
        assert follow_up["show_manage_link"] is False
        assert len(outbox) == 1

    async def test_no_smtp_and_an_opted_out_address_answer_alike(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
        outbox: list[GuestMail],
    ) -> None:
        without_smtp = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            await add_shift(db_session, test_task),
        )
        configure_smtp(monkeypatch)
        await guest_quota.suppress(db_session, address="optout@example.org")
        opted_out = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            await add_shift(db_session, test_task),
            email="optout@example.org",
        )
        for body in (without_smtp, opted_out):
            assert body["mail_queued"] is False
            assert body["show_manage_link"] is True
        assert set(without_smtp) == set(opted_out)
        assert outbox == []


@pytest.mark.asyncio
class TestPerPersonLimit:
    async def test_counted_by_address_across_chains(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_task: Task,
    ) -> None:
        shared_list = await make_shared_list(max_per_person=2)
        shifts = [
            await add_shift(db_session, test_task, start=dt.time(h), end=dt.time(h + 1))
            for h in (9, 11, 13)
        ]
        one = await _signed_up(
            unauthenticated_client, shared_list, shifts[0], email="m@example.org"
        )
        assert one["remaining"] == 1
        two = await _signed_up(
            unauthenticated_client, shared_list, shifts[1], email="M@example.org"
        )
        assert two["remaining"] == 0
        response = await _sign_up(
            unauthenticated_client, shared_list, shifts[2], email="m@example.org"
        )
        assert response.status_code == 409
        assert _code(response) == "shared_list.max_per_person"
        assert response.json()["max"] == 2

    async def test_counted_by_chain_without_an_address(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_task: Task,
    ) -> None:
        shared_list = await make_shared_list(ask_email="off", max_per_person=1)
        first = await _signed_up(
            unauthenticated_client, shared_list, await add_shift(db_session, test_task)
        )
        assert first["remaining"] == 0
        response = await _sign_up(
            unauthenticated_client,
            shared_list,
            await add_shift(db_session, test_task, start=dt.time(14), end=dt.time(16)),
            guest_token=first["guest_token"],
        )
        assert _code(response) == "shared_list.max_per_person"
        # A new chain cannot be told apart: it starts over.
        other = await _sign_up(
            unauthenticated_client,
            shared_list,
            await add_shift(db_session, test_task, start=dt.time(16), end=dt.time(18)),
        )
        assert other.status_code == 201

    async def test_no_limit(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
    ) -> None:
        for hour in (9, 11, 13, 15):
            body = await _signed_up(
                unauthenticated_client,
                test_shared_list,
                await add_shift(
                    db_session, test_task, start=dt.time(hour), end=dt.time(hour + 1)
                ),
                email="many@example.org",
            )
            assert body["remaining"] is None


@pytest.mark.asyncio
@pytest.mark.usefixtures("limits_on")
class TestDailyCeilings:
    async def test_signups_per_address(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
    ) -> None:
        monkeypatch.setattr(settings, "GUEST_SIGNUPS_PER_ADDRESS_PER_DAY", 2)
        bodies = [
            await _signed_up(
                unauthenticated_client,
                test_shared_list,
                await add_shift(
                    db_session, test_task, start=dt.time(h), end=dt.time(h + 1)
                ),
                email="busy@example.org",
            )
            for h in (9, 11)
        ]
        # Erasing the guests makes no room: the log keeps counting.
        for body in bodies:
            erased = await unauthenticated_client.post(
                f"{API}/guest-signups/erase", json={"token": body["guest_token"]}
            )
            assert erased.status_code == 204
        response = await _sign_up(
            unauthenticated_client,
            test_shared_list,
            await add_shift(db_session, test_task, start=dt.time(13), end=dt.time(14)),
            email="busy@example.org",
        )
        assert response.status_code == 429
        assert _code(response) == "shared_list.too_many_for_address"

    async def test_other_events_per_address(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_admin_user: User,
    ) -> None:
        monkeypatch.setattr(settings, "GUEST_SIGNUP_EVENTS_PER_ADDRESS_PER_DAY", 2)
        lists: list[tuple[SharedList, Task, Shift]] = []
        for n in range(3):
            event = Event(
                name=f"Fest {n}",
                start_date=dt.date(2026, 6, 10),
                end_date=dt.date(2026, 6, 14),
                status="published",
                created_by_id=test_admin_user.id,
            )
            db_session.add(event)
            await db_session.flush()
            db_session.add(
                EventMembership(
                    user_id=test_admin_user.id, event_id=event.id, role="owner"
                )
            )
            task = Task(
                name=f"Bar {n}",
                start_date=dt.date(2026, 6, 11),
                end_date=dt.date(2026, 6, 11),
                status="published",
                event_id=event.id,
            )
            db_session.add(task)
            await db_session.flush()
            lists.append(
                (
                    await make_shared_list(event=event, tasks=[task]),
                    task,
                    await add_shift(db_session, task),
                )
            )
        for shared_list, _, shift in lists[:2]:
            await _signed_up(
                unauthenticated_client, shared_list, shift, email="hop@example.org"
            )
        # Again in one of the two events: fine.
        first_list, first_task, _ = lists[0]
        again = await _sign_up(
            unauthenticated_client,
            first_list,
            await add_shift(db_session, first_task, start=dt.time(14), end=dt.time(15)),
            email="hop@example.org",
        )
        assert again.status_code == 201
        third_list, _, third_shift = lists[2]
        third = await _sign_up(
            unauthenticated_client, third_list, third_shift, email="hop@example.org"
        )
        assert third.status_code == 429
        assert _code(third) == "shared_list.too_many_for_address"

    async def test_signups_per_list(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        test_task: Task,
    ) -> None:
        monkeypatch.setattr(settings, "SHARED_LIST_SIGNUPS_PER_LIST_PER_DAY", 2)
        shared_list = await make_shared_list(ask_email="off")
        shift = await add_shift(db_session, test_task, max_bookings=10)
        first = await _signed_up(unauthenticated_client, shared_list, shift)
        await _signed_up(unauthenticated_client, shared_list, shift)
        undone = await unauthenticated_client.post(
            f"{API}/guest-signups/erase", json={"token": first["guest_token"]}
        )
        assert undone.status_code == 204
        response = await _sign_up(unauthenticated_client, shared_list, shift)
        assert response.status_code == 429
        assert _code(response) == "shared_list.daily_limit"


@pytest.mark.asyncio
class TestTurnstile:
    @pytest.fixture
    def checked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> list[tuple[str | None, str | None]]:
        calls: list[tuple[str | None, str | None]] = []

        async def _verify(
            token: str | None, *, expected_action: str | None = None
        ) -> bool:
            calls.append((token, expected_action))
            return token == "solved"

        monkeypatch.setattr(routes, "verify_turnstile", _verify)
        return calls

    async def test_off_without_a_secret(
        self,
        unauthenticated_client: AsyncClient,
        test_shared_list: SharedList,
        shift: Shift,
        checked: list[tuple[str | None, str | None]],
    ) -> None:
        await _signed_up(unauthenticated_client, test_shared_list, shift)
        assert checked == []

    async def test_on_with_a_secret(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        test_shared_list: SharedList,
        shift: Shift,
        checked: list[tuple[str | None, str | None]],
    ) -> None:
        monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", "secret")
        refused = await _sign_up(
            unauthenticated_client, test_shared_list, shift, turnstile_token="forged"
        )
        assert refused.status_code == 403
        assert _code(refused) == "auth.captcha_failed"
        await _signed_up(
            unauthenticated_client, test_shared_list, shift, turnstile_token="solved"
        )
        assert checked == [
            ("forged", "shared-list-signup"),
            ("solved", "shared-list-signup"),
        ]


# ── The manage link ───────────────────────────────────────────────


@pytest.mark.asyncio
class TestManage:
    async def _manage(self, client: AsyncClient, token: str) -> Response:
        return await client.post(f"{API}/guest-signups/manage", json={"token": token})

    async def test_any_failing_token_is_one_404(
        self,
        unauthenticated_client: AsyncClient,
        test_shared_list: SharedList,
        shift: Shift,
    ) -> None:
        token = (await _signed_up(unauthenticated_client, test_shared_list, shift))[
            "guest_token"
        ]
        head, _, tag = token.partition(".")
        tampered = f"{head}.{'A' if tag[0] != 'A' else 'B'}{tag[1:]}"
        for bad in ("garbage", f"{uuid.uuid4().hex}.{tag}", tampered):
            response = await self._manage(unauthenticated_client, bad)
            assert response.status_code == 404
            assert _code(response) == "guest_signup.not_found"
        assert (await self._manage(unauthenticated_client, token)).status_code == 200

    async def test_shows_every_booking_with_its_options(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
        test_event: Event,
    ) -> None:
        first = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            await add_shift(db_session, test_task),
            remind=True,
        )
        await _signed_up(
            unauthenticated_client,
            test_shared_list,
            await add_shift(db_session, test_task, day=dt.date(2026, 6, 12)),
            guest_token=first["guest_token"],
        )
        body = (await self._manage(unauthenticated_client, first["guest_token"])).json()
        assert body["name"] == "Anna Gast"
        assert body["event"]["name"] == test_event.name
        assert body["can_set_reminders"] is True
        assert [
            (b["date"], b["status"], b["can_cancel"], b["reminder_on"])
            for b in body["bookings"]
        ] == [
            ("2026-06-11", "confirmed", True, True),
            ("2026-06-12", "confirmed", True, False),
        ]
        assert body["bookings"][0]["event_name"] == test_event.name
        assert body["bookings"][0]["location"] == "Foyer"

    async def test_cancel_until_the_shift_is_over(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
    ) -> None:
        first = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            await add_shift(db_session, test_task),
            remind=True,
        )
        later = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            await add_shift(db_session, test_task, day=dt.date(2026, 6, 12)),
            guest_token=first["guest_token"],
        )
        response = await unauthenticated_client.post(
            f"{API}/guest-signups/cancel",
            json={"token": first["guest_token"], "booking_id": first["booking_id"]},
        )
        assert response.status_code == 200
        [cancelled, _] = response.json()["bookings"]
        assert cancelled["status"] == "cancelled"
        assert cancelled["can_cancel"] is False
        assert cancelled["reminder_on"] is False

        # 20:00 on 12 June in Berlin: that morning's shift is over.
        freeze_clocks(monkeypatch, dt.datetime(2026, 6, 12, 18, 0))
        over = await unauthenticated_client.post(
            f"{API}/guest-signups/cancel",
            json={"token": first["guest_token"], "booking_id": later["booking_id"]},
        )
        assert over.status_code == 409
        assert _code(over) == "booking.shift_over"

    async def test_a_booking_of_someone_else_is_not_found(
        self,
        unauthenticated_client: AsyncClient,
        test_shared_list: SharedList,
        shift: Shift,
        test_booking: Booking,
    ) -> None:
        token = (await _signed_up(unauthenticated_client, test_shared_list, shift))[
            "guest_token"
        ]
        response = await unauthenticated_client.post(
            f"{API}/guest-signups/cancel",
            json={"token": token, "booking_id": str(test_booking.id)},
        )
        assert response.status_code == 404
        assert _code(response) == "guest_signup.not_found"

    async def test_reminders_off_and_on_again(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        shift: Shift,
    ) -> None:
        body = await _signed_up(
            unauthenticated_client, test_shared_list, shift, remind=True
        )
        for enabled in (False, True, False, True):
            response = await unauthenticated_client.post(
                f"{API}/guest-signups/reminders",
                json={"token": body["guest_token"], "enabled": enabled},
            )
            assert response.status_code == 200
            assert response.json()["bookings"][0]["reminder_on"] is enabled
        rows = (
            (
                await db_session.execute(
                    select(col(BookingReminder.status)).where(
                        col(BookingReminder.booking_id) == uuid.UUID(body["booking_id"])
                    )
                )
            )
            .scalars()
            .all()
        )
        assert rows == ["pending"]

    async def test_reminders_need_an_address(
        self,
        unauthenticated_client: AsyncClient,
        make_shared_list: SharedListFactory,
        shift: Shift,
    ) -> None:
        shared_list = await make_shared_list(ask_email="off")
        token = (await _signed_up(unauthenticated_client, shared_list, shift))[
            "guest_token"
        ]
        response = await unauthenticated_client.post(
            f"{API}/guest-signups/reminders", json={"token": token, "enabled": True}
        )
        assert response.status_code == 409
        assert _code(response) == "guest_signup.no_email"

    async def test_reminders_only_for_shifts_still_ahead(
        self,
        unauthenticated_client: AsyncClient,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        shift: Shift,
        test_shift: Shift,
    ) -> None:
        """``test_shift`` was on 24 May."""
        signed = await make_list_guest(
            test_shared_list, email="r@example.org", shifts=[test_shift, shift]
        )
        response = await unauthenticated_client.post(
            f"{API}/guest-signups/reminders",
            json={"token": guest_tokens.manage_token(signed.guest), "enabled": True},
        )
        assert [b["reminder_on"] for b in response.json()["bookings"]] == [
            False,
            True,
        ]

    async def test_a_removed_shift_shows_what_was_kept_of_it(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        shift: Shift,
    ) -> None:
        signed = await make_list_guest(
            test_shared_list, email="s@example.org", shifts=[shift]
        )
        booking = signed.bookings[0]
        booking.status = "cancelled"
        booking.shift_id = None
        booking.cancelled_task_name = "Bar"
        booking.cancelled_shift_date = dt.date(2026, 6, 11)
        booking.cancelled_shift_start_time = dt.time(10)
        db_session.add(booking)
        await db_session.flush()
        token = guest_tokens.manage_token(signed.guest)

        body = (await self._manage(unauthenticated_client, token)).json()
        assert body["bookings"] == [
            {
                "booking_id": str(booking.id),
                "status": "cancelled",
                "event_name": None,
                "task_name": "Bar",
                "date": "2026-06-11",
                "start_time": "10:00:00",
                "end_time": None,
                "location": None,
                "can_cancel": False,
                "reminder_on": False,
                "vouchers": 0,
                "show_first_name": False,
                "name": "Gast Eins",
            }
        ]
        # Cancelling it again changes nothing.
        again = await unauthenticated_client.post(
            f"{API}/guest-signups/cancel",
            json={"token": token, "booking_id": str(booking.id)},
        )
        assert again.status_code == 200
        assert again.json()["bookings"] == body["bookings"]

    async def test_vouchers_per_event_without_names_or_notes(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_draft_event: Event,
        test_task: Task,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """A task moved to another event took a shift along: what it earns
        there is a second entry, after the guest's own event."""
        test_task.vouchers_per_shift = 2
        moved = Task(
            name="Abbau",
            start_date=MAY,
            end_date=MAY,
            status="published",
            event_id=test_draft_event.id,
            vouchers_per_shift=3,
        )
        db_session.add_all([test_task, moved])
        await db_session.flush()
        signed = await make_list_guest(
            test_shared_list,
            shifts=[
                await add_shift(db_session, test_task, day=MAY),
                await add_shift(db_session, moved, day=MAY),
            ],
        )
        db_session.add(
            VoucherEntry(
                event_id=test_event.id,
                user_id=signed.user.id,
                kind="adjustment",
                amount=1,
                note="Für Gast Eins, Handy leer",
                actor_name="Olga Organisatorin",
            )
        )
        await db_session.flush()

        body = (
            await self._manage(
                unauthenticated_client, guest_tokens.manage_token(signed.guest)
            )
        ).json()

        assert [
            (v["event_name"], v["account"]["summary"]["available"])
            for v in body["vouchers"]
        ] == [(test_event.name, 3), (test_draft_event.name, 3)]
        [entry] = body["vouchers"][0]["account"]["entries"]
        assert (entry["amount"], entry["note"], entry["actor_name"]) == (1, None, None)
        assert body["vouchers"][0]["account"]["summary"]["email"] is None
        assert "Olga" not in str(body) and "Handy" not in str(body)
        assert sorted(b["vouchers"] for b in body["bookings"]) == [2, 3]

    async def test_nothing_that_earns_shows_no_vouchers(
        self,
        unauthenticated_client: AsyncClient,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        shift: Shift,
    ) -> None:
        signed = await make_list_guest(test_shared_list, shifts=[shift])
        body = (
            await self._manage(
                unauthenticated_client, guest_tokens.manage_token(signed.guest)
            )
        ).json()
        assert body["vouchers"] == []

    async def test_erase_on_is_the_period_after_the_last_shift(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
        make_list_guest: ListGuestFactory,
    ) -> None:
        monkeypatch.setattr(settings, "GUEST_DATA_RETENTION_DAYS", 14)
        signed = await make_list_guest(
            test_shared_list,
            shifts=[
                await add_shift(db_session, test_task),
                await add_shift(db_session, test_task, day=dt.date(2026, 6, 13)),
            ],
        )
        body = (
            await self._manage(
                unauthenticated_client, guest_tokens.manage_token(signed.guest)
            )
        ).json()
        # The sweep counts the guest due once 13 June + 14 days has passed.
        assert (body["retention_days"], body["erase_on"]) == (14, "2026-06-28")

    async def test_what_the_page_offers_by_token_and_account(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        chain = await make_list_guest(test_shared_list, email="m@example.org")
        other = await make_list_guest(test_shared_list, email="m@example.org")
        no_address = await make_list_guest(test_shared_list)

        async def offers(token: str) -> tuple[bool, bool, bool, bool]:
            body = (await self._manage(unauthenticated_client, token)).json()
            return (
                body["confirmed"],
                body["can_confirm"],
                body["can_reject"],
                body["reject_suppresses"],
            )

        assert await offers(guest_tokens.mail_token(chain.guest)) == (
            False,
            True,
            True,
            True,
        )
        assert await offers(guest_tokens.manage_token(chain.guest)) == (
            False,
            False,
            False,
            False,
        )
        assert await offers(guest_tokens.mail_token(no_address.guest)) == (
            False,
            False,
            True,
            False,
        )
        await confirm_address(db_session, chain.guest)
        assert await offers(guest_tokens.mail_token(chain.guest)) == (
            True,
            False,
            False,
            False,
        )
        # "Das war ich nicht" no longer stops all mail to the address: its
        # owner confirmed sign-ups with it.
        assert await offers(guest_tokens.mail_token(other.guest)) == (
            False,
            True,
            True,
            False,
        )

    async def test_has_phone_and_each_bookings_own_name(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
        make_list_guest: ListGuestFactory,
    ) -> None:
        maria = await make_list_guest(
            test_shared_list,
            name="Maria",
            email="fam@example.org",
            shifts=[await add_shift(db_session, test_task)],
        )
        tom = await make_list_guest(
            test_shared_list,
            name="Tom",
            email="fam@example.org",
            phone="0170 2",
            shifts=[await add_shift(db_session, test_task, day=dt.date(2026, 6, 12))],
        )
        token = guest_tokens.mail_token(maria.guest)
        assert (await self._manage(unauthenticated_client, token)).json()[
            "has_phone"
        ] is False
        await confirm_address(db_session, maria.guest)
        await confirm_address(db_session, tom.guest)

        body = (await self._manage(unauthenticated_client, token)).json()

        assert body["name"] == "Maria"
        assert body["has_phone"] is True
        assert [b["name"] for b in body["bookings"]] == ["Maria", "Tom"]
        assert "0170 2" not in str(body)

    async def test_the_buckets_are_keyed_per_guest_and_per_ip(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        signed = await make_list_guest(test_shared_list)
        keys: list[tuple[str, str]] = []
        for name, bucket in (
            ("ip", guest_ip_limiter),
            ("miss", guest_link_miss_limiter),
            ("guest", guest_manage_limiter),
        ):

            async def record(key: str, name: str = name) -> None:
                keys.append((name, key))

            monkeypatch.setattr(bucket, "check", record)

        await self._manage(
            unauthenticated_client, guest_tokens.manage_token(signed.guest)
        )
        await self._manage(unauthenticated_client, "garbage")

        await self._manage(
            unauthenticated_client, guest_tokens.mail_token(signed.guest)
        )

        ip = keys[0][1]
        assert keys == [
            ("ip", ip),
            ("guest", f"guest:{signed.user.id}:response"),
            ("ip", ip),
            ("miss", ip),
            ("ip", ip),
            ("guest", f"guest:{signed.user.id}:mail"),
        ]

    @pytest.mark.usefixtures("guest_buckets")
    async def test_calls_are_counted_per_guest(
        self,
        unauthenticated_client: AsyncClient,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """A queue of guests behind one venue NAT does not share a bucket."""
        busy = guest_tokens.manage_token(
            (await make_list_guest(test_shared_list)).guest
        )
        calm = guest_tokens.manage_token(
            (await make_list_guest(test_shared_list, name="Zwei")).guest
        )
        for _ in range(30):
            assert (await self._manage(unauthenticated_client, busy)).status_code == 200

        refused = await self._manage(unauthenticated_client, busy)

        assert refused.status_code == 429
        assert _code(refused) == "guest_signup.rate_limited"
        assert (await self._manage(unauthenticated_client, calm)).status_code == 200

    @pytest.mark.usefixtures("guest_buckets")
    async def test_the_sign_ups_token_cannot_use_up_the_mail_links_calls(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """Whoever typed someone else's address holds the token the sign-up
        answered with. Spending its calls must not stop the address's owner
        from saying "Das war ich nicht"."""
        chain = await make_list_guest(test_shared_list, email="victim@example.org")
        typed = guest_tokens.manage_token(chain.guest)
        for _ in range(30):
            assert (
                await self._manage(unauthenticated_client, typed)
            ).status_code == 200
        assert (await self._manage(unauthenticated_client, typed)).status_code == 429

        rejected = await unauthenticated_client.post(
            f"{API}/guest-signups/not-me",
            json={"token": guest_tokens.mail_token(chain.guest)},
        )

        assert rejected.status_code == 204
        assert (
            await db_session.scalar(
                select(func.count()).where(col(User.id) == chain.user.id)
            )
            == 0
        )

    async def test_a_typed_address_tells_nothing_about_other_events(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_draft_event: Event,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """Anyone can type any address into a list and read the page behind
        the answer. Whether that address confirmed a guest account at some
        other organiser's event is only for the mailbox's owner to see."""
        elsewhere = await make_list_guest(
            await make_shared_list(event=test_draft_event, tasks=[]),
            email="victim@example.org",
        )
        await confirm_address(db_session, elsewhere.guest)
        known = await make_list_guest(test_shared_list, email="victim@example.org")
        unknown = await make_list_guest(test_shared_list, email="nobody@example.org")

        async def suppresses(token: str) -> bool:
            body = (await self._manage(unauthenticated_client, token)).json()
            return body["reject_suppresses"]

        assert [
            await suppresses(guest_tokens.manage_token(signed.guest))
            for signed in (known, unknown)
        ] == [False, False]
        assert [
            await suppresses(guest_tokens.mail_token(signed.guest))
            for signed in (known, unknown)
        ] == [False, True]


@pytest.mark.asyncio
class TestErase:
    async def test_keeps_only_worked_shifts_without_a_name(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
        make_list_guest: ListGuestFactory,
        test_shift: Shift,
    ) -> None:
        """``test_shift`` (24 May) is over; the 11 June one is ahead."""
        ahead = await add_shift(db_session, test_task)
        cancelled_shift = await add_shift(
            db_session, test_task, day=dt.date(2026, 6, 12)
        )
        signed = await make_list_guest(
            test_shared_list,
            name="Fritz Gast",
            email="fritz@example.org",
            phone="0170 99",
            shifts=[test_shift, ahead, cancelled_shift],
        )
        worked, future, cancelled = signed.bookings
        cancelled.status = "cancelled"
        db_session.add(cancelled)
        await db_session.flush()
        token = guest_tokens.manage_token(signed.guest)

        response = await unauthenticated_client.post(
            f"{API}/guest-signups/erase", json={"token": token}
        )

        assert response.status_code == 204
        remaining = (
            (
                await db_session.execute(
                    select(col(Booking.id)).where(
                        col(Booking.user_id) == signed.user.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert remaining == [worked.id]
        await db_session.refresh(signed.user)
        await db_session.refresh(signed.guest)
        assert (signed.user.name, signed.user.phone_number) == (None, None)
        assert signed.guest.email is None
        assert signed.guest.manage_nonce is None
        assert signed.guest.erased_at == dt.datetime(2026, 6, 1, 6, 0)
        assert future.id not in remaining
        again = await unauthenticated_client.post(
            f"{API}/guest-signups/manage", json={"token": token}
        )
        assert again.status_code == 404

    async def test_a_guest_with_nothing_worked_is_deleted(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        shift: Shift,
    ) -> None:
        body = await _signed_up(unauthenticated_client, test_shared_list, shift)
        user, _ = await _guest_of(db_session, body["booking_id"])
        user_id = user.id
        response = await unauthenticated_client.post(
            f"{API}/guest-signups/erase", json={"token": body["guest_token"]}
        )
        assert response.status_code == 204
        db_session.expunge_all()
        assert await db_session.get(User, user_id) is None
        assert (
            await db_session.scalar(
                select(func.count()).where(col(SharedListGuest.user_id) == user_id)
            )
        ) == 0
        # The log stays: erasing resets no ceiling.
        assert (
            await db_session.scalar(
                select(func.count()).where(
                    col(GuestActivityLog.booking_id) == uuid.UUID(body["booking_id"])
                )
            )
        ) == 1

    async def test_not_me_erases_and_stops_all_mail_to_the_address(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
        outbox: list[GuestMail],
    ) -> None:
        configure_smtp(monkeypatch)
        body = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            await add_shift(db_session, test_task),
            email="victim@example.org",
        )
        assert body["mail_queued"] is True
        [confirmation] = outbox
        page = await unauthenticated_client.post(
            f"{API}/guest-signups/manage", json={"token": confirmation.token}
        )
        assert page.json()["can_reject"] is True
        response = await unauthenticated_client.post(
            f"{API}/guest-signups/not-me", json={"token": confirmation.token}
        )
        assert response.status_code == 204
        assert (
            await db_session.scalar(
                select(func.count()).where(
                    col(GuestMailSuppression.address_hash)
                    == guest_tokens.address_hash("victim@example.org")
                )
            )
        ) == 1
        again = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            await add_shift(db_session, test_task, day=dt.date(2026, 6, 12)),
            email="victim@example.org",
        )
        assert again["mail_queued"] is False
        assert len(outbox) == 1

    async def test_whoever_typed_an_address_cannot_silence_it(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        shift: Shift,
        outbox: list[GuestMail],
    ) -> None:
        """The sign-up's answer holds a token of its own, not the mail's: it
        manages the chain, but "Das war ich nicht" needs the mailbox."""
        configure_smtp(monkeypatch)
        body = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            shift,
            email="victim@example.org",
        )
        [confirmation] = outbox
        assert confirmation.token != body["guest_token"]
        page = await unauthenticated_client.post(
            f"{API}/guest-signups/manage", json={"token": body["guest_token"]}
        )
        assert page.json()["can_reject"] is False

        response = await unauthenticated_client.post(
            f"{API}/guest-signups/not-me", json={"token": body["guest_token"]}
        )

        assert response.status_code == 403
        assert _code(response) == "guest_signup.mail_link_required"
        assert (
            await db_session.scalar(
                select(func.count()).select_from(GuestMailSuppression)
            )
        ) == 0
        _, guest = await _guest_of(db_session, body["booking_id"])
        assert guest.manage_nonce is not None


# ── Vouchers and guest accounts ───────────────────────────────────


@pytest.mark.asyncio
class TestVouchersOnThePublicPage:
    async def test_each_shift_says_what_it_earns(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        make_shared_list: SharedListFactory,
    ) -> None:
        test_task.vouchers_per_shift = 2
        plain = Task(
            name="Garderobe",
            start_date=dt.date(2026, 6, 11),
            end_date=dt.date(2026, 6, 11),
            status="published",
            event_id=test_event.id,
        )
        db_session.add_all([test_task, plain])
        await db_session.flush()
        await add_shift(db_session, test_task)
        await add_shift(db_session, plain, start=dt.time(14), end=dt.time(16))
        shared_list = await make_shared_list(tasks=[test_task, plain])

        body = (
            await unauthenticated_client.get(f"{API}/shared-lists/{shared_list.code}")
        ).json()

        assert {
            s["task_name"]: s["vouchers"] for day in body["days"] for s in day["shifts"]
        } == {test_task.name: 2, "Garderobe": 0}

    async def test_the_retention_period_is_the_setting(
        self,
        unauthenticated_client: AsyncClient,
        async_client: AsyncClient,
        app: FastAPI,
        monkeypatch: pytest.MonkeyPatch,
        test_event_admin_user: User,
        test_shared_list: SharedList,
        shift: Shift,
    ) -> None:
        monkeypatch.setattr(settings, "GUEST_DATA_RETENTION_DAYS", 14)

        public = await unauthenticated_client.get(
            f"{API}/shared-lists/{test_shared_list.code}"
        )
        with act_as(app, test_event_admin_user):
            preview = await async_client.get(
                f"/api/v1/shared-lists/{test_shared_list.id}/preview"
            )

        assert public.json()["retention_days"] == 14
        assert preview.json()["retention_days"] == 14


@pytest.fixture
def guest_buckets(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The guest rate limiters on and empty, and empty again afterwards."""
    monkeypatch.setattr(settings, "TESTING", False)
    buckets = (
        guest_ip_limiter,
        guest_link_miss_limiter,
        guest_manage_limiter,
        guest_pass_status_limiter,
        voucher_pass_limiter,
    )
    for bucket in buckets:
        bucket.reset()
    yield
    for bucket in buckets:
        bucket.reset()


async def _confirm(client: AsyncClient, token: str) -> Response:
    return await client.post(f"{API}/guest-signups/confirm", json={"token": token})


@pytest.mark.asyncio
class TestConfirm:
    """Confirming the address, "Ja, das bin ich"
    (``POST /public/guest-signups/confirm``)."""

    async def _two_chains(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db: AsyncSession,
        shared_list: SharedList,
        task: Task,
        outbox: list[GuestMail],
    ) -> tuple[dict[str, Any], dict[str, Any], str, str]:
        """Two visits with one address: two chains, two confirmation mails."""
        configure_smtp(monkeypatch)
        first = await _signed_up(
            client,
            shared_list,
            await add_shift(db, task),
            name="Maria Muster",
            email="fam@example.org",
        )
        second = await _signed_up(
            client,
            shared_list,
            await add_shift(db, task, day=dt.date(2026, 6, 12)),
            name="Tom Muster",
            email="fam@example.org",
        )
        first_mail, second_mail = (mail.token for mail in outbox)
        return first, second, first_mail, second_mail

    async def test_the_first_promotes_and_the_second_merges(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
        outbox: list[GuestMail],
    ) -> None:
        _, _, first_mail, second_mail = await self._two_chains(
            unauthenticated_client,
            monkeypatch,
            db_session,
            test_shared_list,
            test_task,
            outbox,
        )

        promoted = await _confirm(unauthenticated_client, first_mail)
        merged = await _confirm(unauthenticated_client, second_mail)

        assert promoted.status_code == 200, promoted.text
        assert merged.status_code == 200, merged.text
        # A promotion keeps the token the page holds; a merge hands over the
        # account's.
        assert promoted.json()["token"] == first_mail
        assert merged.json()["token"] == first_mail
        page = merged.json()["manage"]
        assert (page["confirmed"], page["can_confirm"], page["name"]) == (
            True,
            False,
            "Maria Muster",
        )
        assert [b["name"] for b in page["bookings"]] == ["Maria Muster", "Tom Muster"]
        # The old link of the merged chain opens the account, and confirming
        # it again changes nothing.
        again = await _confirm(unauthenticated_client, second_mail)
        assert again.status_code == 200
        assert again.json()["token"] == first_mail

    async def test_only_the_mail_link_confirms(
        self,
        unauthenticated_client: AsyncClient,
        test_shared_list: SharedList,
        shift: Shift,
    ) -> None:
        body = await _signed_up(unauthenticated_client, test_shared_list, shift)

        response = await _confirm(unauthenticated_client, body["guest_token"])

        assert response.status_code == 403
        assert _code(response) == "guest_signup.mail_link_required"

    async def test_a_chain_without_an_address_is_never_a_500(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        shift: Shift,
    ) -> None:
        shared_list = await make_shared_list(ask_email="off", ask_phone="required")
        body = await _signed_up(
            unauthenticated_client, shared_list, shift, phone="0170 1"
        )
        _, guest = await _guest_of(db_session, body["booking_id"])

        by_form = await _confirm(unauthenticated_client, body["guest_token"])
        by_mail = await _confirm(unauthenticated_client, guest_tokens.mail_token(guest))

        assert (by_form.status_code, _code(by_form)) == (
            403,
            "guest_signup.mail_link_required",
        )
        assert (by_mail.status_code, _code(by_mail)) == (404, "guest_signup.not_found")

    async def test_a_forged_token_takes_no_lock(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        test_shared_list: SharedList,
        shift: Shift,
    ) -> None:
        token = (await _signed_up(unauthenticated_client, test_shared_list, shift))[
            "guest_token"
        ]
        head, _, tag = token.partition(".")

        async def no_lock(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("locked for a forged token")

        monkeypatch.setattr(guest_account.crud_event, "lock", no_lock)
        monkeypatch.setattr(guest_account.guest_quota, "lock_account", no_lock)

        response = await _confirm(
            unauthenticated_client, f"{head}.{'A' if tag[0] != 'A' else 'B'}{tag[1:]}"
        )

        assert response.status_code == 404
        assert _code(response) == "guest_signup.not_found"

    @pytest.mark.parametrize("merged", [False, True])
    async def test_the_retired_response_token_opens_nothing_but_a_new_chain(
        self,
        merged: bool,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
        outbox: list[GuestMail],
    ) -> None:
        """The done page and its "Noch eine Schicht" hold the response token:
        after the confirmation it opens nothing, and another sign-up with it
        starts a chain of its own."""
        first, second, first_mail, second_mail = await self._two_chains(
            unauthenticated_client,
            monkeypatch,
            db_session,
            test_shared_list,
            test_task,
            outbox,
        )
        if merged:
            await _confirm(unauthenticated_client, first_mail)
        await _confirm(unauthenticated_client, second_mail)
        retired = second["guest_token"]

        page = await unauthenticated_client.post(
            f"{API}/guest-signups/manage", json={"token": retired}
        )
        another = await _signed_up(
            unauthenticated_client,
            test_shared_list,
            await add_shift(db_session, test_task, day=dt.date(2026, 6, 13)),
            name="Tom Muster",
            email="fam@example.org",
            guest_token=retired,
        )

        assert (page.status_code, _code(page)) == (404, "guest_signup.not_found")
        user, _ = await _guest_of(db_session, another["booking_id"])
        assert another["guest_token"] != retired
        assert user.id.hex != retired.partition(".")[0]
        assert another["mail_queued"] is True
        assert first["booking_id"] != another["booking_id"]

    @pytest.mark.usefixtures("guest_buckets")
    @pytest.mark.parametrize("merged", [False, True])
    async def test_a_retired_response_token_is_a_miss(
        self,
        merged: bool,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """Whoever only typed the address keeps a dead token. Confirming with
        it counts against their IP, never against the account the address's
        owner uses."""
        first = await make_list_guest(test_shared_list, email="fam@example.org")
        chain = await make_list_guest(test_shared_list, email="fam@example.org")
        retired = guest_tokens.manage_token(chain.guest)
        if merged:
            await confirm_address(db_session, first.guest)
        await confirm_address(db_session, chain.guest)
        account = first if merged else chain

        for _ in range(30):
            missed = await _confirm(unauthenticated_client, retired)
            assert (missed.status_code, _code(missed)) == (
                404,
                "guest_signup.not_found",
            )
        refused = await _confirm(unauthenticated_client, retired)
        page = await unauthenticated_client.post(
            f"{API}/guest-signups/manage",
            json={"token": guest_tokens.mail_token(account.guest)},
        )

        assert (refused.status_code, _code(refused)) == (
            429,
            "guest_signup.rate_limited",
        )
        assert page.status_code == 200

    async def test_a_confirmation_beside_an_account_promises_no_silence(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_draft_event: Event,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        test_task: Task,
        outbox: list[GuestMail],
    ) -> None:
        """ "Das war ich nicht" keeps an address with an account mailable, so
        the confirmation does not say it would stop all mail."""
        configure_smtp(monkeypatch)
        account = await make_list_guest(
            await make_shared_list(event=test_draft_event, tasks=[]),
            email="fam@example.org",
        )
        await confirm_address(db_session, account.guest)

        for day, email in ((11, "fam@example.org"), (12, "new@example.org")):
            await _signed_up(
                unauthenticated_client,
                test_shared_list,
                await add_shift(db_session, test_task, day=dt.date(2026, 6, day)),
                email=email,
            )

        assert [mail.not_me for mail in outbox] == ["erases", "suppresses"]

    async def test_an_unconfirmed_chain_sees_only_itself(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_task: Task,
        outbox: list[GuestMail],
    ) -> None:
        test_task.vouchers_per_shift = 2
        db_session.add(test_task)
        await db_session.flush()
        first, second, first_mail, _ = await self._two_chains(
            unauthenticated_client,
            monkeypatch,
            db_session,
            test_shared_list,
            test_task,
            outbox,
        )
        await _confirm(unauthenticated_client, first_mail)

        for token in (second["guest_token"], outbox[1].token):
            page = (
                await unauthenticated_client.post(
                    f"{API}/guest-signups/manage", json={"token": token}
                )
            ).json()
            assert [b["booking_id"] for b in page["bookings"]] == [second["booking_id"]]
            [vouchers] = page["vouchers"]
            assert vouchers["account"]["summary"]["upcoming"] == 2
        assert first["booking_id"] != second["booking_id"]

    async def test_not_me_on_an_account_is_refused(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        shift: Shift,
        outbox: list[GuestMail],
    ) -> None:
        configure_smtp(monkeypatch)
        await _signed_up(unauthenticated_client, test_shared_list, shift)
        [mail] = outbox
        await _confirm(unauthenticated_client, mail.token)

        response = await unauthenticated_client.post(
            f"{API}/guest-signups/not-me", json={"token": mail.token}
        )

        assert response.status_code == 409
        assert _code(response) == "guest_signup.reject_confirmed"

    @pytest.mark.parametrize("where", ["here", "elsewhere"])
    async def test_not_me_beside_an_account_keeps_the_address_mailable(
        self,
        where: str,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_draft_event: Event,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        shift: Shift,
    ) -> None:
        """Only the inbox's owner holds a chain's mail link. Having confirmed
        an account with the address, suppressing it would silently stop the
        mail about their own sign-ups."""
        configure_smtp(monkeypatch)
        account_list = (
            test_shared_list
            if where == "here"
            else await make_shared_list(event=test_draft_event, tasks=[])
        )
        account = await make_list_guest(account_list, email="fam@example.org")
        await confirm_address(db_session, account.guest)
        chain = await make_list_guest(
            test_shared_list, email="fam@example.org", shifts=[shift]
        )

        response = await unauthenticated_client.post(
            f"{API}/guest-signups/not-me",
            json={"token": guest_tokens.mail_token(chain.guest)},
        )

        assert response.status_code == 204
        assert (
            await db_session.scalar(
                select(func.count()).where(col(User.id) == chain.user.id)
            )
            == 0
        )
        assert (
            await db_session.scalar(
                select(func.count()).select_from(GuestMailSuppression)
            )
            == 0
        )
        assert await guest_quota.reserve_mail(
            db_session,
            address="fam@example.org",
            kind="reminder",
            event_id=account.guest.event_id,
            booking_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
class TestGuestVoucherPass:
    """A guest's voucher code, through the token of their manage page."""

    @pytest_asyncio.fixture
    async def earned(
        self,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> tuple[ListGuest, Task]:
        """A guest who worked an ended shift worth 2, and a point."""
        test_task.vouchers_per_shift = 2
        point = Task(
            name="Theke",
            start_date=MAY,
            end_date=MAY,
            status="published",
            event_id=test_event.id,
            is_voucher_point=True,
        )
        db_session.add_all([test_task, point])
        await db_session.flush()
        signed = await make_list_guest(
            test_shared_list,
            name="Gast Eins",
            shifts=[await add_shift(db_session, test_task, day=MAY)],
        )
        return signed, point

    async def _issue(
        self, client: AsyncClient, token: str, event_id: uuid.UUID
    ) -> Response:
        return await client.post(
            f"{API}/guest-signups/vouchers/pass",
            json={"token": token, "event_id": str(event_id)},
        )

    async def _status(
        self, client: AsyncClient, token: str, event_id: uuid.UUID, pass_id: str
    ) -> Response:
        return await client.post(
            f"{API}/guest-signups/vouchers/pass-status",
            json={"token": token, "event_id": str(event_id), "pass_id": pass_id},
        )

    async def test_the_response_token_shows_a_code_a_member_redeems(
        self,
        unauthenticated_client: AsyncClient,
        async_client: AsyncClient,
        app: FastAPI,
        test_event: Event,
        test_event_admin_user: User,
        earned: tuple[ListGuest, Task],
    ) -> None:
        signed, point = earned
        token = guest_tokens.manage_token(signed.guest)

        issued = await self._issue(unauthenticated_client, token, test_event.id)

        assert issued.status_code == 201, issued.text
        code = issued.json()
        assert code["qr_payload"] == f"WV1:{code['code']}"
        assert code["event_name"] == test_event.name
        status = await self._status(
            unauthenticated_client, token, test_event.id, code["id"]
        )
        assert (status.json()["status"], status.json()["available"]) == ("active", 2)
        with act_as(app, test_event_admin_user):
            checked = await async_client.post(
                f"/api/v1/events/{test_event.id}/vouchers/check",
                json={"task_id": str(point.id), "code": code["code"]},
            )
            redeemed = await async_client.post(
                f"/api/v1/events/{test_event.id}/vouchers/redeem",
                json={
                    "task_id": str(point.id),
                    "code": code["code"],
                    "amount": 2,
                    "request_id": str(uuid.uuid4()),
                },
            )
        assert (checked.json()["is_guest"], checked.json()["name"]) == (
            True,
            "Gast Eins",
        )
        assert redeemed.status_code == 201, redeemed.text
        used = (
            await self._status(unauthenticated_client, token, test_event.id, code["id"])
        ).json()
        assert (used["status"], used["redeemed_amount"], used["available"]) == (
            "used",
            2,
            0,
        )

    async def test_an_event_without_vouchers_is_not_found(
        self,
        unauthenticated_client: AsyncClient,
        test_event: Event,
        test_draft_event: Event,
        earned: tuple[ListGuest, Task],
    ) -> None:
        signed, _ = earned

        response = await self._issue(
            unauthenticated_client,
            guest_tokens.manage_token(signed.guest),
            test_draft_event.id,
        )

        assert response.status_code == 404
        assert _code(response) == "guest_signup.not_found"

    async def test_a_replaced_code_is_gone(
        self,
        unauthenticated_client: AsyncClient,
        test_event: Event,
        earned: tuple[ListGuest, Task],
    ) -> None:
        signed, _ = earned
        token = guest_tokens.mail_token(signed.guest)
        first = (await self._issue(unauthenticated_client, token, test_event.id)).json()
        await self._issue(unauthenticated_client, token, test_event.id)

        response = await self._status(
            unauthenticated_client, token, test_event.id, first["id"]
        )

        assert response.status_code == 404
        assert _code(response) == "voucher.pass_not_found"

    async def test_not_switched_off(
        self,
        unauthenticated_client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        test_event: Event,
        earned: tuple[ListGuest, Task],
    ) -> None:
        signed, _ = earned
        monkeypatch.setattr(settings, "SHARED_LISTS_ENABLED", False)

        response = await self._issue(
            unauthenticated_client,
            guest_tokens.manage_token(signed.guest),
            test_event.id,
        )

        assert response.status_code == 201

    @pytest.mark.usefixtures("guest_buckets")
    async def test_a_code_screen_is_counted_per_guest(
        self,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_task: Task,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
        earned: tuple[ListGuest, Task],
    ) -> None:
        """A screen asks every two seconds; ten of them behind one venue NAT
        must not share a bucket."""
        signed, _ = earned
        neighbour = await make_list_guest(
            test_shared_list,
            name="Nachbar",
            shifts=[await add_shift(db_session, test_task, day=MAY)],
        )
        tokens = [guest_tokens.manage_token(g.guest) for g in (signed, neighbour)]
        passes = [
            (await self._issue(unauthenticated_client, t, test_event.id)).json()["id"]
            for t in tokens
        ]
        for _ in range(120):
            assert (
                await self._status(
                    unauthenticated_client, tokens[0], test_event.id, passes[0]
                )
            ).status_code == 200

        refused = await self._status(
            unauthenticated_client, tokens[0], test_event.id, passes[0]
        )
        neighbours = await self._status(
            unauthenticated_client, tokens[1], test_event.id, passes[1]
        )

        assert (refused.status_code, _code(refused)) == (
            429,
            "guest_signup.rate_limited",
        )
        assert neighbours.status_code == 200

    @pytest.mark.usefixtures("guest_buckets")
    async def test_misses_are_counted_per_ip(
        self,
        unauthenticated_client: AsyncClient,
        test_event: Event,
        earned: tuple[ListGuest, Task],
    ) -> None:
        """A scan for live tokens meets its bucket at once; a guest behind the
        same address whose token resolves does not."""
        signed, _ = earned
        for _ in range(30):
            response = await self._issue(
                unauthenticated_client, f"{uuid.uuid4().hex}.forged", test_event.id
            )
            assert response.status_code == 404
        refused = await self._issue(
            unauthenticated_client, f"{uuid.uuid4().hex}.forged", test_event.id
        )
        live = await self._issue(
            unauthenticated_client,
            guest_tokens.manage_token(signed.guest),
            test_event.id,
        )

        assert (refused.status_code, _code(refused)) == (
            429,
            "guest_signup.rate_limited",
        )
        assert live.status_code == 201
