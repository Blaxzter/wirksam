import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.users import get_current_user_profile, update_user_profile
from app.crud.user import user as crud_user
from app.models.user import User
from app.schemas.users import UserProfileUpdate


@pytest.mark.asyncio
class TestUserRoutes:
    async def test_list_users(self, async_client: AsyncClient, test_user: User):
        response = await async_client.get("/api/v1/users/")
        assert response.status_code == 200
        data = response.json()
        assert any(item["id"] == str(test_user.id) for item in data)

    async def test_get_user(self, async_client: AsyncClient, test_user: User):
        response = await async_client.get(f"/api/v1/users/{test_user.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email

    async def test_create_user(self, async_client: AsyncClient):
        payload = {
            "auth0_sub": "auth0|created123",
            "email": "created@example.com",
            "name": "Created User",
            "roles": ["user"],
            "is_active": True,
        }
        response = await async_client.post("/api/v1/users/", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["auth0_sub"] == payload["auth0_sub"]
        assert data["email"] == payload["email"]
        assert data["name"] == payload["name"]
        assert data["roles"] == ["user"]

    async def test_update_user(self, async_client: AsyncClient, test_user: User):
        payload = {"name": "Updated User", "email": "updated@example.com"}
        response = await async_client.patch(
            f"/api/v1/users/{test_user.id}",
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["name"] == "Updated User"
        assert data["email"] == "updated@example.com"

    async def test_delete_user(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        response = await async_client.delete(f"/api/v1/users/{test_user.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)

        deleted = await crud_user.get(db_session, id=test_user.id)
        assert deleted is None

    async def test_get_auth0_management_url(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/users/auth0-management-url")
        assert response.status_code == 200
        data = response.json()
        assert "management_url" in data
        assert "note" in data


@pytest.mark.asyncio
class TestUserRouteHelpers:
    async def test_get_current_user_profile(
        self,
        db_session: AsyncSession,
        test_user: User,
        mock_auth0_claims: dict[str, str],
    ):
        profile = await get_current_user_profile(
            user=test_user,
            profile_init=None,
            session=db_session,
        )
        assert profile.sub == mock_auth0_claims["sub"]
        assert profile.email == mock_auth0_claims["email"]
        assert profile.roles == test_user.roles
        assert profile.is_admin is False

    async def test_update_user_profile(
        self,
        monkeypatch: pytest.MonkeyPatch,
        test_user: User,
    ):
        called = {}

        async def fake_update_auth0_user(user_id: str, update_data: UserProfileUpdate):
            called["user_id"] = user_id
            called["update_data"] = update_data
            return True

        monkeypatch.setattr(
            "app.api.routes.users.update_auth0_user",
            fake_update_auth0_user,
        )

        update = UserProfileUpdate(name="Updated Name", nickname="updated")  # type: ignore[reportCallIssue]
        profile = await update_user_profile(
            user_update=update,
            current_user=test_user,
        )

        assert profile.name == "Updated Name"
        assert profile.nickname == "updated"
        assert profile.roles == test_user.roles
