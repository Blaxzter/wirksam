"""FastAPI app and client fixtures for testing."""

from collections.abc import AsyncGenerator
from typing import Any, get_args

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps as deps_module
from app.main import app as fastapi_app
from app.models.user import User


@pytest_asyncio.fixture
async def app(
    db_session: AsyncSession,
    test_user: User,
    test_admin_user: User,
) -> AsyncGenerator[FastAPI, None]:
    """FastAPI app with test dependency overrides."""

    async def override_get_db():
        yield db_session

    async def override_current_user():
        return test_user

    async def override_current_superuser():
        return test_admin_user

    fastapi_app.dependency_overrides[deps_module.get_db] = override_get_db
    fastapi_app.dependency_overrides[
        get_args(deps_module.CurrentUser)[1].dependency
    ] = override_current_user
    fastapi_app.dependency_overrides[
        get_args(deps_module.CurrentSuperuser)[1].dependency
    ] = override_current_superuser

    yield fastapi_app

    fastapi_app.dependency_overrides = {}


@pytest_asyncio.fixture
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def as_admin(app: FastAPI, test_admin_user: User) -> AsyncGenerator[None, None]:
    """Temporarily override CurrentUser to return an admin user."""
    dep: Any = get_args(deps_module.CurrentUser)[1].dependency
    original = app.dependency_overrides.get(dep)

    async def override_current_user():
        return test_admin_user

    app.dependency_overrides[dep] = override_current_user
    yield
    if original:
        app.dependency_overrides[dep] = original
    else:
        app.dependency_overrides.pop(dep, None)
