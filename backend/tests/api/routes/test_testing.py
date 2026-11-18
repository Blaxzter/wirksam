"""``POST /testing/reset``, the clean slate the E2E suite starts from, and
``POST /testing/guest-mail-link``, the link a guest's mail would carry."""

import datetime as dt

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.shared_lists import guest_tokens
from app.models.event import Event
from app.models.shared_list import SharedList
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from tests.fixtures.shared_lists import ListGuestFactory, SharedListFactory


@pytest.mark.asyncio
class TestReset:
    async def test_guests_of_a_test_event_go_with_it_and_no_others(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_shift: Shift,
        test_shared_list: SharedList,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """Deleting a test user takes their event, and with it the contact
        rows of its guests. The guests themselves are no test users and would
        stay behind, booked on the orphaned task, for ever."""
        owner = User(
            subject="test|reset-owner@example.com",
            email="reset-owner@example.com",
            name="Reset Owner",
        )
        db_session.add(owner)
        await db_session.flush()
        event = Event(
            name="E2E event",
            start_date=dt.date(2026, 6, 10),
            end_date=dt.date(2026, 6, 14),
            status="published",
            created_by_id=owner.id,
        )
        db_session.add(event)
        await db_session.flush()
        task = Task(
            name="Theke",
            start_date=dt.date(2026, 6, 12),
            end_date=dt.date(2026, 6, 12),
            status="published",
            created_by_id=owner.id,
            event_id=event.id,
        )
        db_session.add(task)
        await db_session.flush()
        shift = Shift(task_id=task.id, title="Theke", date=dt.date(2026, 6, 12))
        db_session.add(shift)
        await db_session.flush()
        e2e_list = await make_shared_list(event=event, tasks=[task], created_by=owner)
        of_test_event = await make_list_guest(e2e_list, shifts=[shift])
        of_real_event = await make_list_guest(test_shared_list, shifts=[test_shift])

        r = await async_client.post("/api/v1/testing/reset")

        assert r.status_code == 200
        assert r.json()["deleted_list_guests"] >= 1
        remaining = await db_session.execute(
            select(col(User.id)).where(
                col(User.id).in_(
                    [owner.id, of_test_event.user.id, of_real_event.user.id]
                )
            )
        )
        assert set(remaining.scalars()) == {of_real_event.user.id}


@pytest.mark.asyncio
class TestGuestMailLink:
    async def test_the_mail_token_behind_a_sign_ups_token(
        self,
        async_client: AsyncClient,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        """E2E has no mailbox; this is how it opens a guest's mail link."""
        signed = await make_list_guest(test_shared_list, email="e2e@example.org")

        response = await async_client.post(
            "/api/v1/testing/guest-mail-link",
            json={"token": guest_tokens.manage_token(signed.guest)},
        )
        missing = await async_client.post(
            "/api/v1/testing/guest-mail-link", json={"token": "nothing.here"}
        )

        assert response.status_code == 200
        assert response.json() == {"token": guest_tokens.mail_token(signed.guest)}
        assert missing.status_code == 404
