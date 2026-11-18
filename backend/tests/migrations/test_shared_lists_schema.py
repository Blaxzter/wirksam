"""The schema ``20261110_0001_shared_lists`` creates, and its way back.

``alembic check`` sees neither CHECK constraints nor server defaults nor which
references deliberately have no foreign key, so these read the catalogue of the
test database, which is built by running the migrations. What matters most:
every foreign key of the new tables cascades (SET NULL next to an event
reference is the trap in app/models/CLAUDE.md), and the rows that must outlive
a delete (``bookings.shared_list_id``, the activity log, the merged chain an
alias names) have none at all.

The round trip runs on a database of its own, so a failing downgrade cannot
take the shared test database down with it. It goes through the alembic CLI,
never importing the migration, which would only add its lines to coverage.
"""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings
from tests.fixtures.database import TEST_DB_NAME

BACKEND_DIR = Path(__file__).resolve().parents[2]
REVISION = "20261110_0001"

NEW_TABLES = (
    "shared_lists",
    "shared_list_tasks",
    "shared_list_excluded_shifts",
    "shared_list_guests",
    "shared_list_guest_aliases",
    "guest_activity_log",
    "guest_mail_suppressions",
)
NEW_COLUMNS = (
    ("users", "is_list_guest"),
    ("bookings", "shared_list_id"),
    ("bookings", "show_first_name"),
    ("bookings", "guest_name"),
    ("bookings", "guest_phone"),
    ("events", "managers_share_lists"),
)

_FK_ACTIONS = text(
    """
    SELECT conrelid::regclass::text AS tbl,
           confrelid::regclass::text AS ref,
           confdeltype::text AS action
    FROM pg_constraint
    WHERE contype = 'f' AND conrelid::regclass::text = ANY(:tables)
    """
)


@pytest.mark.asyncio
async def test_every_foreign_key_of_the_new_tables_cascades(
    db_session: AsyncSession,
) -> None:
    rows = (await db_session.execute(_FK_ACTIONS, {"tables": list(NEW_TABLES)})).all()
    assert sorted((r.tbl, r.ref, r.action) for r in rows) == [
        ("shared_list_excluded_shifts", "shared_lists", "c"),
        ("shared_list_excluded_shifts", "shifts", "c"),
        ("shared_list_guest_aliases", "users", "c"),
        ("shared_list_guests", "events", "c"),
        ("shared_list_guests", "users", "c"),
        ("shared_list_tasks", "shared_lists", "c"),
        ("shared_list_tasks", "tasks", "c"),
        ("shared_lists", "events", "c"),
    ]


@pytest.mark.asyncio
async def test_a_bookings_list_is_not_a_foreign_key(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            """
            SELECT count(*) FROM pg_constraint c
            JOIN pg_attribute a
              ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            WHERE c.contype = 'f'
              AND c.conrelid = 'bookings'::regclass
              AND a.attname = 'shared_list_id'
            """
        )
    )
    assert result.scalar_one() == 0


@pytest.mark.asyncio
async def test_the_check_constraints_exist(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT conname FROM pg_constraint "
            "WHERE contype = 'c' AND conrelid::regclass::text = ANY(:tables)"
        ),
        {"tables": list(NEW_TABLES)},
    )
    assert set(result.scalars()) == {
        "ck_shared_lists_status",
        "ck_shared_lists_ends_mode",
        "ck_shared_lists_ends_on",
        "ck_shared_lists_ask_email",
        "ck_shared_lists_ask_phone",
        "ck_shared_lists_show_names",
        "ck_shared_lists_max_per_person",
        "ck_guest_activity_log_kind",
    }


@pytest.mark.asyncio
async def test_existing_rows_get_the_defaults(db_session: AsyncSession) -> None:
    """Server defaults, so the upgrade fills existing users, bookings and
    events: no one is a guest, no booking names anyone publicly, and people in
    charge may share."""
    result = await db_session.execute(
        text(
            "SELECT table_name, column_default FROM information_schema.columns "
            "WHERE (table_name, column_name) IN "
            "(('users', 'is_list_guest'), ('events', 'managers_share_lists'), "
            "('bookings', 'show_first_name'))"
        )
    )
    assert dict(result.all()) == {
        "users": "false",
        "events": "true",
        "bookings": "false",
    }


@pytest.mark.asyncio
async def test_a_sign_ups_person_lives_on_the_booking(
    db_session: AsyncSession,
) -> None:
    """The consent, name and phone moved from the chain to each booking."""
    result = await db_session.execute(
        text(
            "SELECT table_name || '.' || column_name, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name IN ('bookings', 'shared_list_guests') AND column_name "
            "IN ('show_first_name', 'guest_name', 'guest_phone', 'confirmed_at')"
        )
    )
    assert dict(result.all()) == {
        "bookings.show_first_name": "NO",
        "bookings.guest_name": "YES",
        "bookings.guest_phone": "YES",
        "shared_list_guests.confirmed_at": "YES",
    }


@pytest.mark.asyncio
async def test_one_account_per_event_and_address(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'uq_shared_list_guests_account'"
        )
    )
    definition = result.scalar_one()
    assert definition.startswith("CREATE UNIQUE INDEX")
    assert "(event_id, lower((email)::text))" in definition
    assert definition.endswith("WHERE (confirmed_at IS NOT NULL)")


@pytest.mark.asyncio
async def test_an_alias_names_a_deleted_user_and_dies_with_its_account(
    db_session: AsyncSession,
) -> None:
    result = await db_session.execute(
        text(
            "SELECT indexname, indexdef LIKE 'CREATE UNIQUE%' FROM pg_indexes "
            "WHERE tablename = 'shared_list_guest_aliases'"
        )
    )
    assert dict(result.all()) == {
        "shared_list_guest_aliases_pkey": True,
        "ix_shared_list_guest_aliases_id": False,
        "ix_shared_list_guest_aliases_user_id": True,
        "ix_shared_list_guest_aliases_account_user_id": False,
    }
    keys = await db_session.execute(
        text(
            "SELECT a.attname FROM pg_constraint c JOIN pg_attribute a "
            "ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
            "WHERE c.contype = 'f' "
            "AND c.conrelid = 'shared_list_guest_aliases'::regclass"
        )
    )
    assert list(keys.scalars()) == ["account_user_id"]


@pytest.mark.asyncio
async def test_a_code_and_a_guest_user_are_unique(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes WHERE indexdef LIKE 'CREATE UNIQUE%' "
            "AND indexname IN ('ix_shared_lists_code', 'ix_shared_list_guests_user_id', "
            "'ix_guest_mail_suppressions_address_hash', 'ix_shared_list_guests_email_lower')"
        )
    )
    assert set(result.scalars()) == {
        "ix_shared_lists_code",
        "ix_shared_list_guests_user_id",
        "ix_guest_mail_suppressions_address_hash",
    }


def _alembic(database_url: str, *args: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    subprocess.run(
        ["alembic", *args], cwd=BACKEND_DIR, check=True, capture_output=True, env=env
    )


@pytest.mark.asyncio
async def test_downgrade_and_upgrade_again() -> None:
    scratch = f"{TEST_DB_NAME}_shared_lists_round_trip"
    server_url = str(settings.SQLALCHEMY_DATABASE_URI)
    admin = create_async_engine(
        server_url.replace(f"/{settings.POSTGRES_DB}", "/postgres"),
        isolation_level="AUTOCOMMIT",
    )
    scratch_url = server_url.replace(f"/{settings.POSTGRES_DB}", f"/{scratch}")
    alembic_url = scratch_url.replace("postgresql+asyncpg", "postgresql+psycopg")
    async with admin.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {scratch}"))
        await conn.execute(text(f"CREATE DATABASE {scratch}"))
    try:
        _alembic(alembic_url, "upgrade", "head")
        # One step below this revision, whatever comes after it by then.
        _alembic(alembic_url, "downgrade", f"{REVISION}-1")

        engine = create_async_engine(scratch_url)
        try:
            async with engine.connect() as conn:
                tables = await conn.execute(
                    text("SELECT to_regclass(t) FROM unnest(CAST(:t AS text[])) AS t"),
                    {"t": list(NEW_TABLES)},
                )
                assert set(tables.scalars()) == {None}
                columns = await conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_name || '.' || column_name = ANY(:columns)"
                    ),
                    {"columns": [f"{table}.{column}" for table, column in NEW_COLUMNS]},
                )
                assert columns.scalar_one() == 0
        finally:
            await engine.dispose()

        _alembic(alembic_url, "upgrade", "head")
        _alembic(alembic_url, "check")
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {scratch} WITH (FORCE)"))
        await admin.dispose()
