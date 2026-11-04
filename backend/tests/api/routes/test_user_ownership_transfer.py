"""Tests for the event/task ownership transfer flow before user deletion."""

import datetime as dt
import uuid
from collections.abc import Callable

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.event import event as crud_event
from app.crud.event_membership import event_membership as crud_membership
from app.crud.task import task as crud_task
from app.crud.user import user as crud_user
from app.models.booking import Booking
from app.models.event import Event
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User


@pytest_asyncio.fixture
async def owned_event(
    db_session: AsyncSession, test_user: User, test_event: Event
) -> Event:
    """Make ``test_user`` the owner of ``test_event``.

    Ownership is a membership row now, not just ``created_by_id``, so the
    transfer flow has to move both — this fixture sets up the "before".
    """
    await crud_membership.upsert(
        db_session, user_id=test_user.id, event_id=test_event.id, role="owner"
    )
    test_event.created_by_id = test_user.id
    db_session.add(test_event)
    await db_session.flush()
    await db_session.refresh(test_event)
    return test_event


@pytest_asyncio.fixture
async def transfer_target_user(db_session: AsyncSession) -> User:
    """An active user that can receive ownership."""
    user = User(
        subject="local|transfer_target",
        email="transfer-target@example.com",
        name="Transfer Target",
        roles=[],
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
class TestOwnedContent:
    async def test_owned_content_counts(
        self,
        async_client: AsyncClient,
        test_user: User,
        owned_event: Event,
        test_task: Task,
        as_admin: None,
    ):
        response = await async_client.get(f"/api/v1/users/{test_user.id}/owned-content")
        assert response.status_code == 200
        data = response.json()
        assert data["events"] == 1
        assert data["tasks"] == 1
        assert data["total"] == 2

    async def test_owned_content_empty(
        self,
        async_client: AsyncClient,
        transfer_target_user: User,
        as_admin: None,
    ):
        response = await async_client.get(
            f"/api/v1/users/{transfer_target_user.id}/owned-content"
        )
        assert response.status_code == 200
        data = response.json()
        assert data == {"events": 0, "tasks": 0, "total": 0}

    async def test_owned_content_user_not_found(
        self, async_client: AsyncClient, as_admin: None
    ):
        response = await async_client.get(f"/api/v1/users/{uuid.uuid4()}/owned-content")
        assert response.status_code == 404

    async def test_owned_content_forbidden_for_non_admin(
        self, async_client: AsyncClient, test_user: User
    ):
        response = await async_client.get(f"/api/v1/users/{test_user.id}/owned-content")
        assert response.status_code == 403


@pytest.mark.asyncio
class TestTransferOwnership:
    async def test_transfer_happy_path(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        owned_event: Event,
        test_task: Task,
        transfer_target_user: User,
        as_admin: None,
    ):
        response = await async_client.post(
            f"/api/v1/users/{test_user.id}/transfer-ownership",
            json={"target_user_id": str(transfer_target_user.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["events_transferred"] == 1
        assert data["tasks_transferred"] == 1

        await db_session.refresh(owned_event)
        await db_session.refresh(test_task)
        assert owned_event.created_by_id == transfer_target_user.id
        assert test_task.created_by_id == transfer_target_user.id

    async def test_transfer_nothing_owned_is_noop(
        self,
        async_client: AsyncClient,
        transfer_target_user: User,
        test_admin_user: User,
        as_admin: None,
    ):
        response = await async_client.post(
            f"/api/v1/users/{transfer_target_user.id}/transfer-ownership",
            json={"target_user_id": str(test_admin_user.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["events_transferred"] == 0
        assert data["tasks_transferred"] == 0

    async def test_transfer_source_not_found(
        self,
        async_client: AsyncClient,
        transfer_target_user: User,
        as_admin: None,
    ):
        response = await async_client.post(
            f"/api/v1/users/{uuid.uuid4()}/transfer-ownership",
            json={"target_user_id": str(transfer_target_user.id)},
        )
        assert response.status_code == 404

    async def test_transfer_target_not_found(
        self,
        async_client: AsyncClient,
        test_user: User,
        as_admin: None,
    ):
        response = await async_client.post(
            f"/api/v1/users/{test_user.id}/transfer-ownership",
            json={"target_user_id": str(uuid.uuid4())},
        )
        assert response.status_code == 404
        assert response.json()["code"] == "user.transfer_target_not_found"

    async def test_transfer_target_inactive(
        self,
        async_client: AsyncClient,
        test_user: User,
        test_inactive_user: User,
        as_admin: None,
    ):
        response = await async_client.post(
            f"/api/v1/users/{test_user.id}/transfer-ownership",
            json={"target_user_id": str(test_inactive_user.id)},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "user.transfer_target_inactive"

    async def test_transfer_to_same_user(
        self,
        async_client: AsyncClient,
        test_user: User,
        as_admin: None,
    ):
        response = await async_client.post(
            f"/api/v1/users/{test_user.id}/transfer-ownership",
            json={"target_user_id": str(test_user.id)},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "user.transfer_same_user"

    async def test_transfer_forbidden_for_non_admin(
        self,
        async_client: AsyncClient,
        test_user: User,
        transfer_target_user: User,
    ):
        response = await async_client.post(
            f"/api/v1/users/{test_user.id}/transfer-ownership",
            json={"target_user_id": str(transfer_target_user.id)},
        )
        assert response.status_code == 403

    async def test_transfer_forbidden_for_event_admin(
        self,
        async_client: AsyncClient,
        test_user: User,
        transfer_target_user: User,
        as_event_admin: None,
    ):
        response = await async_client.post(
            f"/api/v1/users/{test_user.id}/transfer-ownership",
            json={"target_user_id": str(transfer_target_user.id)},
        )
        assert response.status_code == 403

    async def test_the_source_users_unfinished_bookings_are_cancelled(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        owned_event: Event,
        test_task: Task,
        transfer_target_user: User,
        as_admin: None,
        wall_clock: Callable[[dt.datetime], None],
    ):
        """The source account survives but has left the event (its owner row
        moved), so, as when anyone leaves, its bookings on shifts still to
        come go and those on shifts already over stay: that work happened."""
        wall_clock(dt.datetime(2026, 6, 11, 15, 0))
        ended = Shift(
            task_id=test_task.id,
            title="Aufbau",
            date=dt.date(2026, 6, 11),
            start_time=dt.time(8),
            end_time=dt.time(12),
            max_bookings=2,
        )
        future = Shift(
            task_id=test_task.id,
            title="Abbau",
            date=dt.date(2026, 6, 13),
            start_time=dt.time(18),
            end_time=dt.time(22),
            max_bookings=2,
        )
        db_session.add_all([ended, future])
        await db_session.flush()
        worked = Booking(shift_id=ended.id, user_id=test_user.id, status="confirmed")
        to_come = Booking(shift_id=future.id, user_id=test_user.id, status="confirmed")
        db_session.add_all([worked, to_come])
        await db_session.flush()

        response = await async_client.post(
            f"/api/v1/users/{test_user.id}/transfer-ownership",
            json={"target_user_id": str(transfer_target_user.id)},
        )
        assert response.status_code == 200
        assert response.json()["events_transferred"] == 1

        await db_session.refresh(worked)
        await db_session.refresh(to_come)
        assert worked.status == "confirmed"
        assert to_come.status == "cancelled"
        assert to_come.cancelled_task_name == test_task.name
        assert to_come.cancelled_shift_title == "Abbau"
        assert to_come.cancelled_shift_date == dt.date(2026, 6, 13)
        assert (
            await crud_membership.get(
                db_session, user_id=test_user.id, event_id=owned_event.id
            )
            is None
        )


@pytest.mark.asyncio
class TestGuardedDelete:
    async def test_delete_blocked_when_user_owns_content(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        owned_event: Event,
        test_task: Task,
        as_admin: None,
    ):
        response = await async_client.delete(f"/api/v1/users/{test_user.id}")
        assert response.status_code == 409
        assert response.json()["code"] == "user.owns_content"

        still_there = await crud_user.get(db_session, id=test_user.id)
        assert still_there is not None

    async def test_delete_with_transfer_target(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        owned_event: Event,
        test_task: Task,
        transfer_target_user: User,
        as_admin: None,
    ):
        response = await async_client.delete(
            f"/api/v1/users/{test_user.id}",
            params={"transfer_to_user_id": str(transfer_target_user.id)},
        )
        assert response.status_code == 200
        assert response.json()["id"] == str(test_user.id)

        deleted = await crud_user.get(db_session, id=test_user.id)
        assert deleted is None

        # Owned content survived and now belongs to the target
        event = await crud_event.get(db_session, id=owned_event.id)
        task = await crud_task.get(db_session, id=test_task.id)
        assert event is not None
        assert task is not None
        assert event.created_by_id == transfer_target_user.id
        assert task.created_by_id == transfer_target_user.id

    async def test_delete_with_invalid_transfer_target_keeps_user(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        owned_event: Event,
        test_inactive_user: User,
        as_admin: None,
    ):
        response = await async_client.delete(
            f"/api/v1/users/{test_user.id}",
            params={"transfer_to_user_id": str(test_inactive_user.id)},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "user.transfer_target_inactive"

        still_there = await crud_user.get(db_session, id=test_user.id)
        assert still_there is not None

    async def test_delete_without_owned_content_still_works(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        transfer_target_user: User,
        as_admin: None,
    ):
        response = await async_client.delete(f"/api/v1/users/{transfer_target_user.id}")
        assert response.status_code == 200

        deleted = await crud_user.get(db_session, id=transfer_target_user.id)
        assert deleted is None
