"""``just seed``: the dev login and the public demo's event as a permanent one.

The event is built by the same seeder as the sandbox, so its content is
covered by ``tests/logic/test_sandbox_seed.py``. What is tested here is what
differs: nothing in it may be a sandbox row (or the TTL sweep and the
visibility filters would treat the dev database's main event as a guest's
demo), the made-up people must still be undeliverable, and the script must be
safe to run on every ``just dev``.
"""

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.logic.notifications.channels.base import is_undeliverable
from app.logic.sandbox.cleanup import sweep_expired
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.event_team import EventTeam, EventTeamMember
from app.models.task import Task
from app.models.user import User
from app.scripts import seed_demo


async def _people(db: AsyncSession, event: Event) -> list[User]:
    rows = await db.execute(
        select(User)
        .join(EventMembership, col(EventMembership.user_id) == col(User.id))
        .where(col(EventMembership.event_id) == event.id)
    )
    return list(rows.scalars())


@pytest.mark.asyncio
class TestSeedDemo:
    async def test_the_dev_account_is_made_once(self, db_session: AsyncSession) -> None:
        """Test that the login is a verified platform admin, and is not remade."""
        user = await seed_demo.ensure_dev_user(db_session)
        again = await seed_demo.ensure_dev_user(db_session)

        assert again.id == user.id
        assert user.email == seed_demo.DEV_EMAIL
        assert user.roles == ["admin"]
        assert user.email_verified is True
        assert user.password_hash

    async def test_it_seeds_an_ordinary_event_the_dev_account_owns(
        self, db_session: AsyncSession
    ) -> None:
        """Test that nothing in the dev event is a sandbox row."""
        user = await seed_demo.ensure_dev_user(db_session)
        event = await seed_demo.seed_event(
            db_session, owner=user, language="en", force=False
        )

        assert event is not None
        assert event.is_sandbox is False
        assert event.sandbox_expires_at is None
        assert event.created_by_id == user.id
        assert user.selected_event_id == event.id

        role = (
            await db_session.execute(
                select(col(EventMembership.role)).where(
                    col(EventMembership.event_id) == event.id,
                    col(EventMembership.user_id) == user.id,
                )
            )
        ).scalar_one()
        assert role == "owner"

        tasks = list(
            (
                await db_session.execute(
                    select(Task).where(col(Task.event_id) == event.id)
                )
            ).scalars()
        )
        assert tasks
        assert not any(task.is_sandbox for task in tasks)

        others = [
            person
            for person in await _people(db_session, event)
            if person.id != user.id
        ]
        assert others
        for person in others:
            assert person.is_sandbox is False
            assert person.subject.startswith("demo|")
            assert person.email is None
            assert is_undeliverable(person)

    async def test_the_dev_account_leads_the_cash_desk_with_requests_waiting(
        self, db_session: AsyncSession
    ) -> None:
        """Test that the team screens have the manager variant's content."""
        user = await seed_demo.ensure_dev_user(db_session)
        event = await seed_demo.seed_event(
            db_session, owner=user, language="de", force=False
        )
        assert event is not None

        rows = (
            await db_session.execute(
                select(EventTeam, EventTeamMember)
                .join(
                    EventTeamMember,
                    col(EventTeamMember.team_id) == col(EventTeam.id),
                )
                .where(col(EventTeam.event_id) == event.id)
            )
        ).all()

        assert event.name == "Sommerfest am Fluss"
        assert ("Kasse", "lead") in {
            (team.name, member.role)
            for team, member in rows
            if member.user_id == user.id
        }
        assert sum(1 for _, member in rows if member.status == "pending") == 5

    async def test_it_is_idempotent_and_force_adds_another(
        self, db_session: AsyncSession
    ) -> None:
        """Test that ``just dev`` reruns are no-ops and ``--force`` is not."""
        user = await seed_demo.ensure_dev_user(db_session)
        first = await seed_demo.seed_event(
            db_session, owner=user, language="en", force=False
        )
        skipped = await seed_demo.seed_event(
            db_session, owner=user, language="de", force=False
        )
        forced = await seed_demo.seed_event(
            db_session, owner=user, language="en", force=True
        )

        assert first is not None
        assert skipped is None
        assert forced is not None and forced.id != first.id
        assert {e.id for e in await seed_demo.seeded_events(db_session, user)} == {
            first.id,
            forced.id,
        }

    async def test_the_sandbox_sweep_leaves_it_alone(
        self, db_session: AsyncSession
    ) -> None:
        """Test that the TTL purge never mistakes the dev event for a demo."""
        user = await seed_demo.ensure_dev_user(db_session)
        event = await seed_demo.seed_event(
            db_session, owner=user, language="en", force=False
        )
        assert event is not None

        _ = await sweep_expired(
            db_session,
            now=dt.datetime.now(dt.UTC).replace(tzinfo=None) + dt.timedelta(days=365),
        )

        still_there = (
            await db_session.execute(select(Event).where(col(Event.id) == event.id))
        ).scalar_one_or_none()
        assert still_there is not None


def test_it_refuses_outside_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that a well-known password never reaches a real deployment."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr("sys.argv", ["seed_demo"])

    with pytest.raises(SystemExit, match="Refusing to seed"):
        seed_demo.main()
