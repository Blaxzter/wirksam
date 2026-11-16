"""Testing endpoints for E2E test isolation.

Only registered when TESTING=true. Provides user seeding and data reset
so that Playwright tests can run without Auth0, and the link a guest's mail
would carry, since the E2E suite has no mailbox.
"""

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, exists, select
from sqlmodel import col

from app.api.deps import DBDep
from app.core.errors import raise_problem
from app.crud.user import user as crud_user
from app.logic.shared_lists import guest_tokens
from app.models.shared_list import SharedListGuest
from app.models.user import User
from app.schemas.public_shared_list import GuestTokenRequest
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

    Generates a deterministic subject from the email so re-seeding
    is idempotent.
    """
    subject = f"{TEST_SUB_PREFIX}{body.email}"

    existing = await crud_user.get_by_email(session, email=body.email)
    if existing:
        existing.name = body.name
        existing.roles = body.roles
        existing.is_active = body.is_active
        existing.preferred_language = body.preferred_language
        existing.subject = subject
        session.add(existing)
        await session.flush()
        await session.refresh(existing)
        return existing

    user_in = UserCreate(
        subject=subject,
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
    """Delete all test users (subject starting with 'test|') and their data.

    Dependent rows are cleaned up by ON DELETE CASCADE / SET NULL constraints.
    The guests of the test events' shared lists are no test users, but their
    contact rows went with those events, and every guest left without one is
    deleted too.
    """
    result = await session.execute(
        select(col(User.id)).where(col(User.subject).startswith(TEST_SUB_PREFIX))
    )
    test_user_ids = list(result.scalars().all())
    if test_user_ids:
        await session.execute(delete(User).where(col(User.id).in_(test_user_ids)))
        await session.flush()

    guests = await session.execute(
        delete(User)
        .where(
            col(User.is_list_guest).is_(True),
            ~exists().where(col(SharedListGuest.user_id) == col(User.id)),
        )
        .returning(col(User.id))
    )
    return {
        "deleted_users": len(test_user_ids),
        "deleted_list_guests": len(guests.all()),
    }


@router.post("/guest-mail-link", response_model=GuestTokenRequest)
async def guest_mail_link(body: GuestTokenRequest, session: DBDep) -> GuestTokenRequest:
    """The mail token of the guest behind a manage token, as the link in their
    confirmation mail carries it. 404 ``guest_signup.not_found`` for a token
    that does not resolve."""
    key = await guest_tokens.resolve(session, body.token)
    if key is None:
        raise_problem(
            404,
            code="guest_signup.not_found",
            detail="This link does not work (any more)",
        )
    return GuestTokenRequest(token=guest_tokens.mail_token(key.guest))
