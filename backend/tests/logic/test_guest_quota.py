"""The daily ceilings of ``guest_quota``, counted in ``guest_activity_log``.

They are off under TESTING, so every counting test switches them on. Rows are
written as the sign-up and the mails write them; the log has no foreign keys,
so ids that point nowhere are fine.
"""

import datetime as dt
import logging
import uuid
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.logic.shared_lists import guest_quota
from app.logic.shared_lists.guest_tokens import address_hash
from app.models.event import Event
from app.models.shared_list import GuestActivityLog, GuestMailSuppression
from tests.fixtures.guest_signups import configure_smtp
from tests.fixtures.sandbox import SandboxSetup

ADDRESS = "quota@example.org"


@pytest.fixture
def limits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TESTING", False)


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_smtp(monkeypatch)


def _code(exc: pytest.ExceptionInfo[HTTPException]) -> str:
    detail: Any = exc.value.detail
    return str(detail["code"])


async def _log(db: AsyncSession, **fields: object) -> None:
    db.add(GuestActivityLog(**fields))  # pyright: ignore[reportArgumentType]
    await db.flush()


async def _rows(db: AsyncSession, kind: str) -> int:
    return (
        await db.scalar(select(func.count()).where(col(GuestActivityLog.kind) == kind))
    ) or 0


@pytest.mark.usefixtures("limits_on")
class TestAdmitSignup:
    async def test_per_address(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "GUEST_SIGNUPS_PER_ADDRESS_PER_DAY", 2)
        event_id = uuid.uuid4()
        hashed = address_hash(ADDRESS)
        await _log(db_session, kind="signup", address_hash=hashed, event_id=event_id)
        await guest_quota.admit_signup(db_session, hashed=hashed, event_id=event_id)
        await _log(db_session, kind="signup", address_hash=hashed, event_id=event_id)
        with pytest.raises(HTTPException) as refused:
            await guest_quota.admit_signup(db_session, hashed=hashed, event_id=event_id)
        assert refused.value.status_code == 429
        assert _code(refused) == "shared_list.too_many_for_address"

    async def test_only_the_last_day_counts(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "GUEST_SIGNUPS_PER_ADDRESS_PER_DAY", 1)
        hashed = address_hash(ADDRESS)
        yesterday = dt.datetime.now(dt.UTC).replace(tzinfo=None) - dt.timedelta(
            hours=25
        )
        await _log(
            db_session,
            kind="signup",
            address_hash=hashed,
            event_id=uuid.uuid4(),
            created_at=yesterday,
        )
        await guest_quota.admit_signup(db_session, hashed=hashed, event_id=uuid.uuid4())

    async def test_other_events_per_address(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "GUEST_SIGNUP_EVENTS_PER_ADDRESS_PER_DAY", 2)
        hashed = address_hash(ADDRESS)
        here, there, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        for event_id in (here, there, there):
            await _log(
                db_session, kind="signup", address_hash=hashed, event_id=event_id
            )
        # Two events so far, one of them this one: room.
        await guest_quota.admit_signup(db_session, hashed=hashed, event_id=here)
        with pytest.raises(HTTPException) as refused:
            await guest_quota.admit_signup(db_session, hashed=hashed, event_id=third)
        assert _code(refused) == "shared_list.too_many_for_address"

    async def test_mails_do_not_count_as_sign_ups(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "GUEST_SIGNUPS_PER_ADDRESS_PER_DAY", 1)
        hashed = address_hash(ADDRESS)
        await _log(db_session, kind="confirmation", address_hash=hashed)
        await guest_quota.admit_signup(db_session, hashed=hashed, event_id=uuid.uuid4())

    async def test_per_list(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "SHARED_LIST_SIGNUPS_PER_LIST_PER_DAY", 1)
        list_id = uuid.uuid4()
        await guest_quota.admit_list_signup(db_session, shared_list_id=list_id)
        await _log(db_session, kind="signup", shared_list_id=list_id)
        with pytest.raises(HTTPException) as refused:
            await guest_quota.admit_list_signup(db_session, shared_list_id=list_id)
        assert refused.value.status_code == 429
        assert _code(refused) == "shared_list.daily_limit"
        await guest_quota.admit_list_signup(db_session, shared_list_id=uuid.uuid4())


async def test_nothing_is_counted_under_testing(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "GUEST_SIGNUPS_PER_ADDRESS_PER_DAY", 0)
    monkeypatch.setattr(settings, "SHARED_LIST_SIGNUPS_PER_LIST_PER_DAY", 0)
    await guest_quota.admit_signup(
        db_session, hashed=address_hash(ADDRESS), event_id=uuid.uuid4()
    )
    await guest_quota.admit_list_signup(db_session, shared_list_id=uuid.uuid4())


class TestReserveMail:
    async def test_without_smtp_nothing_is_reserved(
        self,
        db_session: AsyncSession,
        caplog: pytest.LogCaptureFixture,
        test_event: Event,
    ) -> None:
        with caplog.at_level(logging.INFO):
            reserved = await guest_quota.reserve_mail(
                db_session,
                address=ADDRESS,
                kind="reminder",
                event_id=test_event.id,
                booking_id=uuid.uuid4(),
            )
        assert reserved is False
        assert await _rows(db_session, "reminder") == 0
        assert "guest mail not sent: SMTP not configured (reminder)" in caplog.text
        assert ADDRESS not in caplog.text

    @pytest.mark.usefixtures("smtp")
    async def test_a_mail_is_one_row(
        self, db_session: AsyncSession, test_event: Event
    ) -> None:
        """However many shifts it names: the ceilings count mails."""
        booking_id = uuid.uuid4()
        assert await guest_quota.reserve_mail(
            db_session,
            address=ADDRESS,
            kind="cancelled",
            event_id=test_event.id,
            booking_id=booking_id,
        )
        [row] = (
            (
                await db_session.execute(
                    select(GuestActivityLog).where(
                        col(GuestActivityLog.kind) == "cancelled"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert row.booking_id == booking_id
        assert row.address_hash == address_hash(ADDRESS)
        assert row.event_id == test_event.id
        assert row.organiser_id == test_event.created_by_id

    @pytest.mark.usefixtures("smtp")
    async def test_nothing_about_a_demo_event_is_mailed(
        self,
        db_session: AsyncSession,
        caplog: pytest.LogCaptureFixture,
        test_sandbox: SandboxSetup,
    ) -> None:
        """A demo's guest is anonymous: its lists mail no typed address."""
        with caplog.at_level(logging.INFO):
            reserved = await guest_quota.reserve_mail(
                db_session,
                address=ADDRESS,
                kind="confirmation",
                event_id=test_sandbox.event.id,
                booking_id=uuid.uuid4(),
            )

        assert reserved is False
        assert await _rows(db_session, "confirmation") == 0
        assert "guest mail not sent: demo event (confirmation" in caplog.text
        assert ADDRESS not in caplog.text

    @pytest.mark.usefixtures("smtp")
    async def test_an_address_that_opted_out_gets_nothing(
        self, db_session: AsyncSession, test_event: Event
    ) -> None:
        await guest_quota.suppress(db_session, address=ADDRESS)
        await guest_quota.suppress(db_session, address=ADDRESS)
        assert (
            await db_session.scalar(
                select(func.count()).select_from(GuestMailSuppression)
            )
        ) == 1
        assert not await guest_quota.reserve_mail(
            db_session,
            address=ADDRESS,
            kind="confirmation",
            event_id=test_event.id,
            booking_id=uuid.uuid4(),
        )
        assert await _rows(db_session, "confirmation") == 0

    @pytest.mark.usefixtures("smtp", "limits_on")
    @pytest.mark.parametrize("ceiling", ["address", "event", "organiser"])
    async def test_ceilings(
        self,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
        test_event: Event,
        ceiling: str,
    ) -> None:
        monkeypatch.setattr(settings, "GUEST_MAILS_PER_ADDRESS_PER_DAY", 2)
        monkeypatch.setattr(settings, "GUEST_MAILS_PER_EVENT_PER_DAY", 2)
        monkeypatch.setattr(settings, "GUEST_MAILS_PER_ORGANISER_PER_DAY", 2)
        others = {
            "address": {"address_hash": address_hash(ADDRESS)},
            "event": {"event_id": test_event.id},
            "organiser": {"organiser_id": test_event.created_by_id},
        }[ceiling]
        for kind in ("reminder", "moved"):
            await _log(db_session, kind=kind, **others)
        # Sign-ups are no mail.
        await _log(db_session, kind="signup", address_hash=address_hash(ADDRESS))

        with caplog.at_level(logging.INFO):
            reserved = await guest_quota.reserve_mail(
                db_session,
                address=ADDRESS,
                kind="removed",
                event_id=test_event.id,
                booking_id=uuid.uuid4(),
            )

        assert reserved is False
        assert await _rows(db_session, "removed") == 0
        assert f"over the daily {ceiling} ceiling" in caplog.text
        assert str(test_event.id) in caplog.text
        assert ADDRESS not in caplog.text
        assert address_hash(ADDRESS) not in caplog.text

    @pytest.mark.usefixtures("smtp")
    async def test_the_operator_lifts_an_opt_out(
        self, db_session: AsyncSession, test_event: Event
    ) -> None:
        await guest_quota.suppress(db_session, address=ADDRESS)
        assert await guest_quota.lift_suppression(db_session, address=ADDRESS)
        assert not await guest_quota.lift_suppression(db_session, address=ADDRESS)
        assert await guest_quota.reserve_mail(
            db_session,
            address=ADDRESS,
            kind="reminder",
            event_id=test_event.id,
            booking_id=uuid.uuid4(),
        )


@pytest.mark.usefixtures("smtp", "limits_on")
async def test_an_event_whose_organiser_left_keeps_its_own_ceiling(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, test_event: Event
) -> None:
    monkeypatch.setattr(settings, "GUEST_MAILS_PER_EVENT_PER_DAY", 1)
    test_event.created_by_id = None
    db_session.add(test_event)
    await db_session.flush()
    assert await guest_quota.reserve_mail(
        db_session,
        address=ADDRESS,
        kind="moved",
        event_id=test_event.id,
        booking_id=uuid.uuid4(),
    )
    assert not await guest_quota.reserve_mail(
        db_session,
        address="another@example.org",
        kind="moved",
        event_id=test_event.id,
        booking_id=uuid.uuid4(),
    )
