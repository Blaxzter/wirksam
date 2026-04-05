"""Database setup and session fixtures."""

import os
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# Use separate test database
TEST_DB_NAME = "app_test"


def run_alembic_migrations():
    """Run Alembic migrations for the test database using psycopg driver."""
    backend_dir = Path(__file__).parent.parent.parent

    # Get the test database URL with psycopg driver instead of asyncpg
    test_db_url = (
        str(settings.SQLALCHEMY_DATABASE_URI)
        .replace(f"/{settings.POSTGRES_DB}", f"/{TEST_DB_NAME}")
        .replace("postgresql+asyncpg", "postgresql+psycopg")
    )

    # Set the database URL as environment variable for alembic to use
    env = os.environ.copy()
    env["DATABASE_URL"] = test_db_url

    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=backend_dir,
        check=True,
        capture_output=True,
        env=env,
    )
    print(result.stdout.decode())


@pytest_asyncio.fixture(scope="session")
async def test_db_setup():
    """Set up test database once per session."""
    # Connect to default postgres database to create test database
    default_db_url = str(settings.SQLALCHEMY_DATABASE_URI).replace(
        f"/{settings.POSTGRES_DB}", "/postgres"
    )
    engine = create_async_engine(default_db_url, isolation_level="AUTOCOMMIT")

    async with engine.connect() as conn:
        # Drop test database if it exists
        await conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))
        # Create test database
        await conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))

    await engine.dispose()

    # Run migrations on test database

    original_db = os.environ.get("POSTGRES_DB")
    os.environ["POSTGRES_DB"] = TEST_DB_NAME

    try:
        run_alembic_migrations()
    finally:
        if original_db:
            os.environ["POSTGRES_DB"] = original_db
        else:
            os.environ.pop("POSTGRES_DB", None)

    yield

    # Clean up: drop test database
    engine = create_async_engine(default_db_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        # Terminate existing connections
        await conn.execute(
            text(
                f"SELECT pg_terminate_backend(pg_stat_activity.pid) "
                f"FROM pg_stat_activity "
                f"WHERE pg_stat_activity.datname = '{TEST_DB_NAME}' "
                f"AND pid <> pg_backend_pid()"
            )
        )
        await conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_engine(test_db_setup: None):
    """Create a test database engine."""
    test_db_url = str(settings.SQLALCHEMY_DATABASE_URI).replace(
        f"/{settings.POSTGRES_DB}", f"/{TEST_DB_NAME}"
    )
    engine = create_async_engine(test_db_url, echo=False)

    print(f"Created test database engine with URL: {test_db_setup}")

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with nested transaction rollback."""
    connection = await test_engine.connect()
    transaction = await connection.begin()

    async_session_maker = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        await session.begin_nested()

        @event.listens_for(session.sync_session, "after_transaction_end")
        def _restart_savepoint(sync_session: Any, nested_transaction: Any) -> None:  # pyright: ignore[reportUnusedFunction]
            if nested_transaction.nested and not nested_transaction._parent.nested:
                sync_session.begin_nested()

        yield session

    await transaction.rollback()
    await connection.close()
