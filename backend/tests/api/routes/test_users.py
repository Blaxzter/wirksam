import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.users import get_current_user_profile, update_user_profile
from app.crud.user import user as crud_user
from app.models.user import User
from app.schemas.users import UserProfileUpdate


@pytest.mark.asyncio
class TestUserRoutes:
    async def test_list_users(
        self, async_client: AsyncClient, test_user: User, as_admin: None
    ):
        response = await async_client.get("/api/v1/users/")
        assert response.status_code == 200
        data = response.json()
        assert any(item["id"] == str(test_user.id) for item in data["items"])
        assert data["counts"]["all"] >= 1

    async def test_list_users_search(
        self, async_client: AsyncClient, test_user: User, as_admin: None
    ):
        assert test_user.email is not None
        q = test_user.email.split("@")[0]
        response = await async_client.get(f"/api/v1/users/?q={q}")
        assert response.status_code == 200
        data = response.json()
        assert data["counts"]["all"] >= 1
        assert all(
            q.lower() in (item["email"] or "").lower()
            or q.lower() in (item["name"] or "").lower()
            for item in data["items"]
        )

    async def test_list_users_status_filter_and_counts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_admin: None,
    ):
        # "pending" and "rejected" are the registration queue; "suspended" is
        # moderation of an approved account. The four never overlap.
        pending = User(
            subject="local|pending_filter_test",
            email="pending-filter@example.com",
            name="Pending Filter",
            approval_status="pending",
        )
        rejected = User(
            subject="local|rejected_filter_test",
            email="rejected-filter@example.com",
            name="Rejected Filter",
            approval_status="rejected",
            rejection_reason="spam",
        )
        suspended = User(
            subject="local|suspended_filter_test",
            email="suspended-filter@example.com",
            name="Suspended Filter",
            is_active=False,
            rejection_reason="abuse",
        )
        db_session.add_all([pending, rejected, suspended])
        await db_session.commit()

        async def ids_for(status_filter: str) -> set[str]:
            response = await async_client.get(
                f"/api/v1/users/?status_filter={status_filter}&limit=100"
            )
            assert response.status_code == 200
            return {item["id"] for item in response.json()["items"]}

        r_pending = await async_client.get("/api/v1/users/?status_filter=pending")
        assert r_pending.status_code == 200
        counts = r_pending.json()["counts"]
        # counts ignore status_filter — they reflect all statuses
        assert counts["pending"] >= 1
        assert counts["rejected"] >= 1
        assert counts["suspended"] >= 1
        assert counts["active"] >= 1
        assert counts["all"] == (
            counts["active"]
            + counts["pending"]
            + counts["rejected"]
            + counts["suspended"]
        )

        assert await ids_for("pending") & {
            str(pending.id),
            str(rejected.id),
            str(suspended.id),
        } == {str(pending.id)}
        assert await ids_for("rejected") & {
            str(pending.id),
            str(rejected.id),
            str(suspended.id),
        } == {str(rejected.id)}
        assert await ids_for("suspended") & {
            str(pending.id),
            str(rejected.id),
            str(suspended.id),
        } == {str(suspended.id)}
        assert not await ids_for("active") & {
            str(pending.id),
            str(rejected.id),
            str(suspended.id),
        }

        # "active" is the third branch of the same filter and the one the
        # moderation screen opens on, so it is asserted rather than assumed.
        r_active = await async_client.get("/api/v1/users/?status_filter=active")
        active_ids = {item["id"] for item in r_active.json()["items"]}
        assert str(pending.id) not in active_ids
        assert str(rejected.id) not in active_ids
        assert all(item["is_active"] for item in r_active.json()["items"])

    async def test_list_users_pagination(
        self, async_client: AsyncClient, as_admin: None
    ):
        response = await async_client.get("/api/v1/users/?skip=0&limit=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 1
        assert data["skip"] == 0
        assert data["limit"] == 1

    async def test_get_user(
        self, async_client: AsyncClient, test_user: User, as_admin: None
    ):
        response = await async_client.get(f"/api/v1/users/{test_user.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["email"] == test_user.email

    async def test_create_user(self, async_client: AsyncClient, as_admin: None):
        payload = {
            "subject": "local|created123",
            "email": "created@example.com",
            "name": "Created User",
            "roles": ["user"],
            "is_active": True,
        }
        response = await async_client.post("/api/v1/users/", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["subject"] == payload["subject"]
        assert data["email"] == payload["email"]
        assert data["name"] == payload["name"]
        assert data["roles"] == ["user"]

    async def test_update_user(
        self, async_client: AsyncClient, test_user: User, as_admin: None
    ):
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
        as_admin: None,
    ):
        response = await async_client.delete(f"/api/v1/users/{test_user.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)

        deleted = await crud_user.get(db_session, id=test_user.id)
        assert deleted is None


@pytest.mark.asyncio
class TestUserRouteHelpers:
    async def test_get_current_user_profile(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """The profile is now read straight off the row, with nothing upserted.

        It used to be a POST that took the identity provider's ID token in the
        body and lazily wrote ``name``/``email`` onto the user, so the natural
        assertion was against the claims that had been sent in. There are no
        claims any more: ``sub`` is the account's own ``subject`` column, and
        every field below is one the database already held.
        """
        profile = await get_current_user_profile(
            user=test_user,
            session=db_session,
        )
        assert profile.id == test_user.id
        assert profile.sub == test_user.subject
        assert profile.email == test_user.email
        assert profile.roles == test_user.roles
        assert profile.is_admin is False

    async def test_update_user_profile(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """``nickname`` now persists instead of being faked into the response.

        Both fields used to live in the identity provider, so this endpoint
        made a Management API call (monkeypatched out here) and then patched
        the values back into its own response with ``model_copy`` — the reply
        looked right and the next profile load lost the edit. Re-reading the
        row is therefore the assertion that matters.
        """
        update = UserProfileUpdate(name="Updated Name", nickname="updated")  # type: ignore[reportCallIssue]
        profile = await update_user_profile(
            user_update=update,
            current_user=test_user,
            session=db_session,
        )

        assert profile.name == "Updated Name"
        assert profile.nickname == "updated"
        assert profile.roles == test_user.roles

        await db_session.refresh(test_user)
        assert test_user.name == "Updated Name"
        assert test_user.nickname == "updated"
