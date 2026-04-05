"""Testing endpoints for E2E test isolation.

Only registered when TESTING=true. Provides user seeding and data reset
so that Playwright tests can run without Auth0.
"""

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, select
from sqlmodel import col

from app.api.deps import DBDep
from app.crud.user import user as crud_user
from app.models.user import User
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/testing", tags=["testing"])

TEST_SUB_PREFIX = "test|"


class TestUserSeed(BaseModel):
    email: EmailStr
    name: str
    roles: list[str] = []
    is_active: bool = True
    preferred_language: str = "en"


@router.post("/seed", response_model=UserRead)
async def seed_test_user(body: TestUserSeed, session: DBDep) -> User:
    """Create or update a test user directly in the database.

    Generates a deterministic auth0_sub from the email so re-seeding
    is idempotent.
    """
    auth0_sub = f"{TEST_SUB_PREFIX}{body.email}"

    existing = await crud_user.get_by_email(session, email=body.email)
    if existing:
        existing.name = body.name
        existing.roles = body.roles
        existing.is_active = body.is_active
        existing.preferred_language = body.preferred_language
        existing.auth0_sub = auth0_sub
        session.add(existing)
        await session.flush()
        await session.refresh(existing)
        return existing

    user_in = UserCreate(
        auth0_sub=auth0_sub,
        email=body.email,
        name=body.name,
        roles=body.roles,
        is_active=body.is_active,
        email_verified=True,
        preferred_language=body.preferred_language,
    )
    return await crud_user.create(session, obj_in=user_in)


@router.post("/reset")
async def reset_test_data(session: DBDep) -> dict[str, int]:
    """Delete all test users (auth0_sub starting with 'test|') and their data.

    Dependent rows are cleaned up by ON DELETE CASCADE / SET NULL constraints.
    """
    result = await session.execute(
        select(col(User.id)).where(col(User.auth0_sub).startswith(TEST_SUB_PREFIX))
    )
    test_user_ids = list(result.scalars().all())
    if not test_user_ids:
        return {"deleted_users": 0}

    await session.execute(delete(User).where(col(User.id).in_(test_user_ids)))
    await session.flush()
    return {"deleted_users": len(test_user_ids)}
