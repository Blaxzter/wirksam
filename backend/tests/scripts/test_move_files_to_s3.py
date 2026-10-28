"""The copy script that moves files from Postgres into the bucket.

Run on a database holding each kind of file: an avatar, a venue plan picture
and a team document. Afterwards Postgres holds no bytes, the bucket holds all
of them, and the API still serves them.
"""

import datetime as dt
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.storage import PostgresStorage, S3Storage
from app.crud.event_team import event_team as crud_team
from app.crud.user_avatar import user_avatar as crud_avatar
from app.models.event_team import EventTeam, EventTeamMember, EventTeamRequirement
from app.models.stored_object import StoredObject
from app.models.user import User
from app.models.venue_plan import VenuePlan
from app.scripts import move_files_to_s3 as script
from tests.fixtures.storage import SessionsStub, fetch_file, storage_in_use


async def _files_in_postgres(
    db: AsyncSession, user: User, plan: VenuePlan, team: EventTeam
) -> dict[str, bytes]:
    """One file of each kind, written the way the Postgres backend writes them."""
    from app.crud.venue_map import venue_map as crud_venue_map
    from app.logic.images import NormalizedImage

    with storage_in_use(PostgresStorage()):
        avatar = await crud_avatar.upsert(
            db,
            user_id=user.id,
            data=b"avatar",
            content_type="image/webp",
            etag="a" * 64,
        )
        image = await crud_venue_map.upsert_image(
            db,
            plan=plan,
            image=NormalizedImage(b"plan", "image/webp", "b" * 64, 10, 10),
        )
        requirement = EventTeamRequirement(team_id=team.id, label="First aid")
        member = EventTeamMember(team_id=team.id, user_id=user.id, status="pending")
        db.add_all([requirement, member])
        await db.flush()
        doc = await crud_team.upsert_document(
            db,
            member_id=member.id,
            requirement_id=requirement.id,
            filename="card.pdf",
            content_type="application/pdf",
            size=3,
            storage_key=await crud_team.store_document_file(
                db, data=b"pdf", content_type="application/pdf"
            ),
        )
    return {
        avatar.storage_key: b"avatar",
        image.storage_key: b"plan",
        doc.storage_key: b"pdf",
    }


@pytest.fixture
async def team(db_session: AsyncSession, test_venue_plan: VenuePlan) -> EventTeam:
    team = EventTeam(event_id=test_venue_plan.event_id, name="Medics")
    db_session.add(team)
    await db_session.flush()
    return team


class TestMoveFiles:
    async def test_moves_every_kind_of_file(
        self,
        db_session: AsyncSession,
        moto_storage: S3Storage,
        test_user: User,
        test_venue_plan: VenuePlan,
        team: EventTeam,
    ) -> None:
        """Test every file ends up in the bucket and none stays in Postgres."""
        files = await _files_in_postgres(db_session, test_user, test_venue_plan, team)
        in_postgres = set(
            (await db_session.execute(select(col(StoredObject.key)))).scalars()
        )
        assert set(files) <= in_postgres

        moved = await script.move_files(
            moto_storage, sessions=SessionsStub(db_session).as_maker(), batch=2
        )

        assert moved == len(in_postgres)
        assert (await db_session.execute(select(StoredObject))).first() is None
        legacy = PostgresStorage()
        for key, data in files.items():
            assert await legacy.get(db_session, key) is None
            assert await moto_storage.get(db_session, key) == data

    async def test_running_again_moves_nothing(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test the script is a no-op once Postgres holds no files."""
        sessions = SessionsStub(db_session).as_maker()
        await script.move_files(moto_storage, sessions=sessions)
        assert await script.move_files(moto_storage, sessions=sessions) == 0

    async def test_api_serves_a_moved_avatar(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        moto_storage: S3Storage,
        test_user: User,
        test_venue_plan: VenuePlan,
        team: EventTeam,
    ) -> None:
        """Test the avatar endpoint reads the file from the bucket after the move."""
        await _files_in_postgres(db_session, test_user, test_venue_plan, team)
        await script.move_files(
            moto_storage, sessions=SessionsStub(db_session).as_maker()
        )

        with storage_in_use(moto_storage):
            r = await fetch_file(async_client, f"/api/v1/users/{test_user.id}/avatar")
        assert r.status_code == 200
        assert r.content == b"avatar"


class TestSweepOrphans:
    async def test_deletes_only_unreferenced_old_objects(
        self,
        db_session: AsyncSession,
        moto_storage: S3Storage,
        test_user: User,
    ) -> None:
        """Test an object no row points at goes; a referenced one stays."""
        with storage_in_use(moto_storage):
            avatar = await crud_avatar.upsert(
                db_session,
                user_id=test_user.id,
                data=b"kept",
                content_type="image/webp",
                etag="a" * 64,
            )
        await moto_storage.put(db_session, "avatars/orphan", b"lost", "image/webp")

        later = dt.datetime.now(dt.UTC) + dt.timedelta(days=2)
        swept = await script.sweep_orphans(
            moto_storage, sessions=SessionsStub(db_session).as_maker(), now=later
        )

        assert swept == 1
        assert await moto_storage.get(db_session, "avatars/orphan") is None
        assert await moto_storage.get(db_session, avatar.storage_key) == b"kept"

    async def test_recent_objects_are_left_alone(
        self, db_session: AsyncSession, moto_storage: S3Storage
    ) -> None:
        """Test a fresh object (an upload whose row is not committed yet) stays."""
        await moto_storage.put(db_session, "avatars/fresh", b"new", "image/webp")
        swept = await script.sweep_orphans(
            moto_storage, sessions=SessionsStub(db_session).as_maker()
        )
        assert swept == 0
        assert await moto_storage.get(db_session, "avatars/fresh") == b"new"


class TestMain:
    async def test_refuses_without_s3(self) -> None:
        """Test the script stops when the configured backend is Postgres."""
        with (
            patch.object(script, "get_storage", return_value=PostgresStorage()),
            pytest.raises(SystemExit, match="STORAGE_BACKEND=s3"),
        ):
            await script.main([])

    async def test_moves_then_sweeps(
        self, moto_storage: S3Storage, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test main moves the files and sweeps only when asked."""
        with (
            patch.object(script, "get_storage", return_value=moto_storage),
            patch.object(script, "move_files", AsyncMock(return_value=3)) as move,
            patch.object(script, "sweep_orphans", AsyncMock(return_value=1)) as sweep,
        ):
            await script.main([])
            sweep.assert_not_awaited()
            await script.main(["--sweep-orphans"])
        assert move.await_count == 2
        sweep.assert_awaited_once()
        out = capsys.readouterr().out
        assert "Moved 3 files" in out and "Deleted 1 orphaned files" in out
