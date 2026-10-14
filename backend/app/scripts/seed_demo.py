"""Seed a local database with a dev login and demo data (``just seed``).

Idempotent, so ``just dev`` runs it on every start:

* the dev account (``dev@example.com`` / ``devpassword`` unless overridden by
  ``DEV_SEED_EMAIL`` / ``DEV_SEED_PASSWORD``) is created once as a verified
  platform admin and left alone afterwards;
* demo data is generated only while no ``[DEMO]`` event exists. ``--force``
  adds another batch regardless; remove it again from the admin screen or with
  ``DELETE /demo-data``.

Refuses to run outside ``ENVIRONMENT=local``: it writes a well-known password.
"""

import argparse
import asyncio
import logging
import os
import sys
import uuid

from app.core.config import settings
from app.core.db import async_session
from app.crud.user import user as crud_user
from app.logic.auth.passwords import hash_new_password
from app.logic.auth.service import LOCAL_SUBJECT_PREFIX
from app.logic.demo_data import create_demo_data, has_demo_data
from app.models.user import User
from app.schemas.demo_data import DemoDataParams

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DEV_EMAIL = os.environ.get("DEV_SEED_EMAIL", "dev@example.com")
DEV_PASSWORD = os.environ.get("DEV_SEED_PASSWORD", "devpassword")


async def seed(*, force: bool) -> None:
    async with async_session.begin() as db:
        user = await crud_user.get_by_email(db, email=DEV_EMAIL)
        if user is None:
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
        else:
            logger.info("Dev account %s already exists", DEV_EMAIL)

        if await has_demo_data(db) and not force:
            logger.info("Demo data already present, skipping (--force adds more)")
            return

        result = await create_demo_data(db, owner=user, params=DemoDataParams())
        logger.info(
            "Seeded %d events, %d tasks, %d shifts, %d users, %d bookings",
            result.events_created,
            result.tasks_created,
            result.shifts_created,
            result.users_created,
            result.bookings_created,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a dev login and demo data.")
    _ = parser.add_argument(
        "--force", action="store_true", help="add demo data even if some exists"
    )
    args = parser.parse_args()

    if settings.ENVIRONMENT != "local":
        sys.exit(f"Refusing to seed with ENVIRONMENT={settings.ENVIRONMENT}")
    asyncio.run(seed(force=bool(args.force)))


if __name__ == "__main__":
    main()
