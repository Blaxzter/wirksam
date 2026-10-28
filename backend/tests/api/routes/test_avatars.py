"""HTTP + persistence tests for the avatar endpoints.

Covers ``app/api/routes/avatars.py`` (upload / delete / serve, including the
conditional-GET 304 path) and ``app/crud/user_avatar.py``. Pure image
normalization behaviour lives in ``tests/logic/test_avatar.py``.
"""

import io
import uuid

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.user_avatar import user_avatar as crud_avatar
from app.models.user import User
from app.models.user_avatar import UserAvatar
from tests.fixtures.storage import drop_file, stored_bytes

AVATAR_URL = "/api/v1/users/me/avatar"


def make_png(color: tuple[int, int, int] = (12, 200, 90), size: int = 64) -> bytes:
    """Build a tiny solid-colour PNG in memory."""
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buf, format="PNG")
    return buf.getvalue()


def png_upload(
    color: tuple[int, int, int] = (12, 200, 90), size: int = 64
) -> dict[str, tuple[str, bytes, str]]:
    """Multipart ``files=`` payload for a valid PNG upload."""
    return {"file": ("a.png", make_png(color, size), "image/png")}


async def fetch_rows(db_session: AsyncSession, user_id: uuid.UUID) -> list[UserAvatar]:
    """All avatar rows belonging to ``user_id`` (should never exceed one)."""
    result = await db_session.execute(
        select(UserAvatar).where(col(UserAvatar.user_id) == user_id)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
class TestUploadAvatar:
    """Test suite for PUT /api/v1/users/me/avatar."""

    async def test_upload_valid_png(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test uploading a valid PNG stores a row and updates avatar_etag."""
        r = await async_client.put(AVATAR_URL, files=png_upload())

        assert r.status_code == 200
        etag = r.json()["etag"]
        assert isinstance(etag, str)
        assert len(etag) == 64  # sha256 hex digest

        rows = await fetch_rows(db_session, test_user.id)
        assert len(rows) == 1
        assert rows[0].etag == etag
        assert rows[0].content_type == "image/webp"
        stored = await stored_bytes(db_session, rows[0].storage_key)
        assert stored is not None and len(stored) > 0

        await db_session.refresh(test_user)
        assert test_user.avatar_etag == etag

    async def test_upload_invalid_bytes_returns_400(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test that non-image bytes are rejected with the processing error."""
        r = await async_client.put(
            AVATAR_URL,
            files={"file": ("a.png", b"definitely not an image", "image/png")},
        )

        assert r.status_code == 400
        assert r.json()["detail"] == "File is not a valid image"
        assert await fetch_rows(db_session, test_user.id) == []

    async def test_upload_empty_file_returns_400(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test that an empty upload is rejected before any row is written."""
        r = await async_client.put(
            AVATAR_URL,
            files={"file": ("a.png", b"", "image/png")},
        )

        assert r.status_code == 400
        assert r.json()["detail"] == "Empty file"
        assert await fetch_rows(db_session, test_user.id) == []

    async def test_upload_twice_upserts(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test that a second upload replaces the row rather than adding one."""
        first = await async_client.put(AVATAR_URL, files=png_upload((10, 20, 30)))
        assert first.status_code == 200
        first_etag = first.json()["etag"]

        rows = await fetch_rows(db_session, test_user.id)
        assert len(rows) == 1
        first_row_id = rows[0].id

        second = await async_client.put(AVATAR_URL, files=png_upload((240, 15, 200)))
        assert second.status_code == 200
        second_etag = second.json()["etag"]
        assert second_etag != first_etag

        rows = await fetch_rows(db_session, test_user.id)
        assert len(rows) == 1
        assert rows[0].id == first_row_id
        assert rows[0].etag == second_etag

        await db_session.refresh(test_user)
        assert test_user.avatar_etag == second_etag


@pytest.mark.asyncio
class TestServeAvatar:
    """Test suite for GET /api/v1/users/{user_id}/avatar."""

    @pytest.mark.usefixtures("streamed")
    async def test_get_existing_avatar(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test serving stored bytes with ETag and Cache-Control headers."""
        upload = await async_client.put(AVATAR_URL, files=png_upload())
        etag = upload.json()["etag"]
        rows = await fetch_rows(db_session, test_user.id)
        stored = await stored_bytes(db_session, rows[0].storage_key)

        r = await async_client.get(f"/api/v1/users/{test_user.id}/avatar")

        assert r.status_code == 200
        assert r.content == stored
        assert r.headers["content-type"] == "image/webp"
        assert r.headers["etag"] == f'"{etag}"'
        assert "max-age" in r.headers["cache-control"]

    async def test_get_with_matching_if_none_match_returns_304(
        self,
        async_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test that a matching If-None-Match yields 304 with an empty body."""
        upload = await async_client.put(AVATAR_URL, files=png_upload())
        etag_header = f'"{upload.json()["etag"]}"'

        r = await async_client.get(
            f"/api/v1/users/{test_user.id}/avatar",
            headers={"If-None-Match": etag_header},
        )

        assert r.status_code == 304
        assert r.headers["etag"] == etag_header
        assert r.content == b""

    @pytest.mark.usefixtures("streamed")
    async def test_get_with_non_matching_if_none_match_returns_body(
        self,
        async_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test that a stale If-None-Match yields the full 200 response."""
        upload = await async_client.put(AVATAR_URL, files=png_upload())
        etag_header = f'"{upload.json()["etag"]}"'

        r = await async_client.get(
            f"/api/v1/users/{test_user.id}/avatar",
            headers={"If-None-Match": '"0000000000000000"'},
        )

        assert r.status_code == 200
        assert len(r.content) > 0
        assert r.headers["etag"] == etag_header

    @pytest.mark.usefixtures("streamed")
    async def test_get_with_unquoted_if_none_match_returns_body(
        self,
        async_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test that an unquoted ETag value is not treated as a match."""
        upload = await async_client.put(AVATAR_URL, files=png_upload())
        etag = upload.json()["etag"]

        r = await async_client.get(
            f"/api/v1/users/{test_user.id}/avatar",
            headers={"If-None-Match": etag},
        )

        assert r.status_code == 200
        assert len(r.content) > 0

    async def test_get_user_without_avatar_returns_404(
        self,
        async_client: AsyncClient,
        test_user: User,
    ) -> None:
        """Test that an existing user with no avatar returns 404."""
        r = await async_client.get(f"/api/v1/users/{test_user.id}/avatar")

        assert r.status_code == 404
        assert r.json()["detail"] == "Avatar not found"

    @pytest.mark.usefixtures("streamed")
    async def test_get_avatar_whose_file_is_gone_returns_404(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test a row whose stored file is missing answers 404, not 500."""
        await async_client.put(AVATAR_URL, files=png_upload())
        rows = await fetch_rows(db_session, test_user.id)
        await drop_file(db_session, rows[0].storage_key)

        r = await async_client.get(f"/api/v1/users/{test_user.id}/avatar")

        assert r.status_code == 404

    async def test_get_unknown_user_returns_404(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that an unknown user id returns the same 404 (no enumeration)."""
        r = await async_client.get(f"/api/v1/users/{uuid.uuid4()}/avatar")

        assert r.status_code == 404
        assert r.json()["detail"] == "Avatar not found"

    async def test_get_invalid_uuid_returns_422(
        self,
        async_client: AsyncClient,
    ) -> None:
        """Test that a malformed user id fails path validation."""
        r = await async_client.get("/api/v1/users/not-a-uuid/avatar")

        assert r.status_code == 422


@pytest.mark.asyncio
class TestDeleteAvatar:
    """Test suite for DELETE /api/v1/users/me/avatar."""

    async def test_delete_removes_row_and_clears_etag(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test that deleting drops the row and nulls the user's avatar_etag."""
        upload = await async_client.put(AVATAR_URL, files=png_upload())
        assert upload.status_code == 200
        assert len(await fetch_rows(db_session, test_user.id)) == 1

        r = await async_client.delete(AVATAR_URL)

        assert r.status_code == 204
        assert r.content == b""
        assert await fetch_rows(db_session, test_user.id) == []

        await db_session.refresh(test_user)
        assert test_user.avatar_etag is None

        follow_up = await async_client.get(f"/api/v1/users/{test_user.id}/avatar")
        assert follow_up.status_code == 404

    async def test_delete_without_avatar_is_still_204(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test that deleting a non-existent avatar is idempotent (204)."""
        r = await async_client.delete(AVATAR_URL)

        assert r.status_code == 204
        assert await fetch_rows(db_session, test_user.id) == []

        await db_session.refresh(test_user)
        assert test_user.avatar_etag is None


@pytest.mark.asyncio
class TestCRUDUserAvatar:
    """Direct tests for the user_avatar CRUD helpers."""

    async def test_get_by_user_returns_none_when_absent(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test get_by_user returns None for a user without an avatar."""
        assert await crud_avatar.get_by_user(db_session, user_id=test_user.id) is None
        assert await crud_avatar.get_by_user(db_session, user_id=uuid.uuid4()) is None

    async def test_upsert_creates_then_updates(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test upsert inserts on first call and mutates the same row after."""
        created = await crud_avatar.upsert(
            db_session,
            user_id=test_user.id,
            data=b"first-bytes",
            content_type="image/webp",
            etag="etag-one",
        )

        assert created.user_id == test_user.id
        first_key = created.storage_key
        assert await stored_bytes(db_session, first_key) == b"first-bytes"
        assert created.etag == "etag-one"

        updated = await crud_avatar.upsert(
            db_session,
            user_id=test_user.id,
            data=b"second-bytes",
            content_type="image/png",
            etag="etag-two",
        )

        assert updated.id == created.id
        assert updated.storage_key != first_key
        assert await stored_bytes(db_session, updated.storage_key) == b"second-bytes"
        assert updated.content_type == "image/png"
        assert updated.etag == "etag-two"
        assert len(await fetch_rows(db_session, test_user.id)) == 1

        fetched = await crud_avatar.get_by_user(db_session, user_id=test_user.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.etag == "etag-two"

    async def test_delete_by_user_returns_true_then_false(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test delete_by_user reports whether a row was actually removed."""
        await crud_avatar.upsert(
            db_session,
            user_id=test_user.id,
            data=b"bytes",
            content_type="image/webp",
            etag="etag-delete",
        )

        assert (
            await crud_avatar.delete_by_user(db_session, user_id=test_user.id) is True
        )
        assert await fetch_rows(db_session, test_user.id) == []
        assert (
            await crud_avatar.delete_by_user(db_session, user_id=test_user.id) is False
        )

    async def test_delete_by_user_unknown_user_returns_false(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Test delete_by_user is a no-op for an unknown user id."""
        assert (
            await crud_avatar.delete_by_user(db_session, user_id=uuid.uuid4()) is False
        )
