"""``serve_file``: a signed redirect to the bucket, or the bytes streamed."""

import requests
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.files import LINK_TTL_SECONDS, serve_file
from app.core.storage import PostgresStorage, S3Storage, new_key
from tests.fixtures.storage import storage_in_use

_PRIVATE = {"Cache-Control": "private, max-age=604800", "ETag": '"abc"'}


async def _body(response: StreamingResponse) -> bytes:
    chunks: list[bytes] = []
    async for chunk in response.body_iterator:
        assert isinstance(chunk, bytes)
        chunks.append(chunk)
    return b"".join(chunks)


class TestSignedLinks:
    async def test_redirects_to_a_link_that_serves_the_file(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test a bucket file is answered with a redirect to a working link."""
        key = new_key("venue-plans")
        await moto_storage.put(db_session, key, b"plan", "image/webp")

        with storage_in_use(moto_storage):
            served = await serve_file(
                db_session, key, media_type="image/webp", headers=_PRIVATE
            )

        assert isinstance(served, RedirectResponse)
        assert served.status_code == 302
        assert served.headers["cache-control"] == (
            f"private, max-age={LINK_TTL_SECONDS // 2}"
        )
        # An ETag would let a browser revalidate the redirect past its link.
        assert "etag" not in served.headers
        followed = requests.get(served.headers["location"], timeout=10)
        assert followed.status_code == 200
        assert followed.content == b"plan"
        assert followed.headers["cache-control"] == "private, max-age=604800"

    async def test_public_file_gets_a_public_redirect(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test a publicly cacheable file keeps that on its redirect."""
        key = new_key("avatars")
        await moto_storage.put(db_session, key, b"face", "image/webp")

        with storage_in_use(moto_storage):
            served = await serve_file(
                db_session,
                key,
                media_type="image/webp",
                headers={"Cache-Control": "public, max-age=86400"},
            )

        assert served is not None
        assert served.headers["cache-control"].startswith("public, ")

    async def test_link_is_signed_for_the_public_endpoint(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test links name the host the browser reaches, not the internal one."""
        import boto3

        signer = boto3.client(  # pyright: ignore[reportUnknownMemberType]
            "s3",
            endpoint_url="https://files.example.org",
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
        storage = S3Storage(moto_storage.client, moto_storage.bucket, signer=signer)

        url = await storage.link(
            db_session, new_key("avatars"), expires_in=60, cache_control="no-store"
        )

        assert url is not None
        assert url.startswith("https://files.example.org/")


class TestStreamed:
    async def test_file_not_moved_yet_is_streamed(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test a file still in Postgres is streamed: the bucket lacks it."""
        key = new_key("avatars")
        await PostgresStorage().put(db_session, key, b"old", "image/webp")

        with storage_in_use(moto_storage):
            served = await serve_file(
                db_session, key, media_type="image/webp", headers=_PRIVATE
            )

        assert isinstance(served, StreamingResponse)
        assert await _body(served) == b"old"
        assert served.headers["etag"] == '"abc"'
        assert served.headers["content-length"] == "3"

    async def test_no_link_when_the_caller_forbids_it(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test ``link=False`` streams even from a bucket."""
        key = new_key("team-documents")
        await moto_storage.put(db_session, key, b"%PDF", "application/pdf")

        with storage_in_use(moto_storage):
            served = await serve_file(
                db_session,
                key,
                media_type="application/pdf",
                headers={"Cache-Control": "private, no-store"},
                link=False,
            )

        assert isinstance(served, StreamingResponse)
        assert await _body(served) == b"%PDF"

    async def test_postgres_streams_and_reports_missing_files(
        self, db_session: AsyncSession
    ) -> None:
        """Test the Postgres store never links, and a missing file is None."""
        key = new_key("avatars")
        with storage_in_use(PostgresStorage()):
            await PostgresStorage().put(db_session, key, b"x", "image/webp")
            served = await serve_file(
                db_session, key, media_type="image/webp", headers=_PRIVATE
            )
            missing = await serve_file(
                db_session, new_key("avatars"), media_type="image/webp", headers={}
            )

        assert isinstance(served, StreamingResponse)
        assert missing is None
