"""Seed a local database with a dev login and a demo event (``just seed``).

Idempotent, so ``just dev`` runs it on every start:

* the dev account (``dev@example.com`` / ``devpassword`` unless overridden by
  ``DEV_SEED_EMAIL`` / ``DEV_SEED_PASSWORD``) is created once as a verified
  platform admin and left alone afterwards;
* the dev account then gets the public demo's event — the same content as the
  sandbox's manager variant (``logic.sandbox.seed``), but as an ordinary,
  permanent event it owns: tasks with shifts around today, a venue plan,
  teammates with bookings and availabilities, a pending invitation and join
  request, five teams with requests to review (the dev account leads the cash
  desk) and an inbox. It is made only while the dev account owns no event of
  that name; ``--force`` adds another, dated around today. ``--lang de`` seeds
  it in German.

Refuses to run outside ``ENVIRONMENT=local``: it writes a well-known password.
"""

import argparse
import asyncio
import datetime as dt
import logging
import os
import sys
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.core.db import async_session
from app.crud.user import user as crud_user
from app.logic.auth.passwords import hash_new_password
from app.logic.auth.service import LOCAL_SUBJECT_PREFIX
from app.logic.sandbox.seed import SEEDED_EVENT_NAMES, seed_dev_event
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.event_team import EventTeam, EventTeamMember
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DEV_EMAIL = os.environ.get("DEV_SEED_EMAIL", "dev@example.com")
DEV_PASSWORD = os.environ.get("DEV_SEED_PASSWORD", "devpassword")


async def ensure_dev_user(db: AsyncSession) -> User:
    """The dev login, created once as a verified platform admin."""
    user = await crud_user.get_by_email(db, email=DEV_EMAIL)
    if user is not None:
        logger.info("Dev account %s already exists", DEV_EMAIL)
        return user
    user = User(
        subject=f"{LOCAL_SUBJECT_PREFIX}{uuid.uuid4().hex}",
        email=DEV_EMAIL,
        name="Dev Admin",
        password_hash=hash_new_password(DEV_PASSWORD),
        email_verified=True,
        is_active=True,
        approval_status="approved",
        roles=["admin"],
    )
    db.add(user)
    await db.flush()
    logger.info("Created dev account %s / %s", DEV_EMAIL, DEV_PASSWORD)
    return user


async def seeded_events(db: AsyncSession, owner: User) -> list[Event]:
    """The demo events ``owner`` already has from an earlier run.

    Matched by the seeder's event name *and* creator, and never a sandbox, so a
    guest's demo or an event someone happened to give the same name does not
    count.
    """
    rows = await db.execute(
        select(Event).where(
            col(Event.created_by_id) == owner.id,
            col(Event.name).in_(SEEDED_EVENT_NAMES),
            col(Event.is_sandbox).is_(False),
        )
    )
    return list(rows.scalars())


async def seed_event(
    db: AsyncSession,
    *,
    owner: User,
    language: str,
    force: bool,
    now: dt.datetime | None = None,
) -> Event | None:
    """Seed the demo event for ``owner`` unless it has one. Returns what it made."""
    existing = await seeded_events(db, owner)
    if existing and not force:
        logger.info(
            "Demo event %r already present, skipping (--force adds another)",
            existing[0].name,
        )
        return None

    event = await seed_dev_event(
        db,
        owner=owner,
        language=language,
        now=now or dt.datetime.now(dt.UTC).replace(tzinfo=None),
    )
    # Open the app on it rather than on the event picker, the first time.
    if owner.selected_event_id is None:
        owner.selected_event_id = event.id
        db.add(owner)
        await db.flush()
    await _log_summary(db, event)
    return event


async def _log_summary(db: AsyncSession, event: Event) -> None:
    tasks = (
        await db.execute(
            select(func.count()).select_from(Task).where(col(Task.event_id) == event.id)
        )
    ).scalar_one()
    shifts = (
        await db.execute(
            select(func.count())
            .select_from(Shift)
            .join(Task, col(Task.id) == col(Shift.task_id))
            .where(col(Task.event_id) == event.id)
        )
    ).scalar_one()
    members = (
        await db.execute(
            select(func.count())
            .select_from(EventMembership)
            .where(col(EventMembership.event_id) == event.id)
        )
    ).scalar_one()
    teams = (
        await db.execute(
            select(func.count())
            .select_from(EventTeam)
            .where(col(EventTeam.event_id) == event.id)
        )
    ).scalar_one()
    pending = (
        await db.execute(
            select(func.count())
            .select_from(EventTeamMember)
            .join(EventTeam, col(EventTeam.id) == col(EventTeamMember.team_id))
            .where(
                col(EventTeam.event_id) == event.id,
                col(EventTeamMember.status) == "pending",
            )
        )
    ).scalar_one()
    logger.info(
        "Seeded %r (%s to %s): %d tasks, %d shifts, %d members, %d teams, "
        "%d team requests",
        event.name,
        event.start_date.isoformat(),
        event.end_date.isoformat(),
        tasks,
        shifts,
        members,
        teams,
        pending,
    )


async def seed(*, force: bool, language: str) -> None:
    async with async_session.begin() as db:
        user = await ensure_dev_user(db)
        _ = await seed_event(db, owner=user, language=language, force=force)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a dev login and a demo event.")
    _ = parser.add_argument(
        "--force", action="store_true", help="add another demo event even if one exists"
    )
    _ = parser.add_argument(
        "--lang",
        choices=("en", "de"),
        default="en",
        help="language of the demo event (default: en)",
    )
    args = parser.parse_args()

    if settings.ENVIRONMENT != "local":
        sys.exit(f"Refusing to seed with ENVIRONMENT={settings.ENVIRONMENT}")
    asyncio.run(seed(force=bool(args.force), language=str(args.lang)))


if __name__ == "__main__":
    main()
