"""An event's look: its colours, its base tone and its logos.

Covers ``app/api/routes/event_logos.py``, ``app/crud/event_logo.py``, the
``primary_color``, ``secondary_color``, ``base_color`` and ``logo_dark_tile``
fields on ``PATCH /events/{id}``, and what a clone and an invitation preview
carry over.

Cast (see ``tests/fixtures/events.py``): on ``test_event`` the default
``async_client`` identity ``test_user`` is a plain *member* and
``test_event_admin_user`` (``as_event_admin``) an *admin*.
"""

import datetime as dt
import io
import typing
import uuid

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.event_invitation import event_invitation as crud_invitation
from app.models.event import (
    EVENT_BASE_COLORS,
    EVENT_PRIMARY_COLORS,
    EVENT_SECONDARY_COLORS,
    Event,
)
from app.models.event_logo import EventLogo
from app.models.event_membership import EventMembership
from app.models.user import User
from app.schemas.event import EventBaseColor, EventPrimaryColor, EventSecondaryColor
from tests.fixtures.storage import drop_file, fetch_file, stored_bytes

API = "/api/v1"


def logo_upload(
    size: tuple[int, int] = (64, 64), mode: str = "RGBA"
) -> dict[str, tuple[str, bytes, str]]:
    """A PNG logo: a red square, on a transparent ground when ``mode`` is RGBA."""
    width, height = size
    if mode == "RGBA":
        img = Image.new("RGBA", size, (0, 0, 0, 0))
    else:
        img = Image.new("RGB", size, (255, 255, 255))
    img.paste((200, 40, 40), (width // 4, height // 4, 3 * width // 4, 3 * height // 4))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {"file": ("logo.png", buf.getvalue(), "image/png")}


async def logo_rows(
    db: AsyncSession, event_id: uuid.UUID, variant: str | None = None
) -> list[EventLogo]:
    query = select(EventLogo).where(col(EventLogo.event_id) == event_id)
    if variant is not None:
        query = query.where(col(EventLogo.variant) == variant)
    result = await db.execute(query)
    return list(result.scalars().all())


async def queued_keys(db: AsyncSession) -> set[str]:
    rows = await db.execute(text("SELECT key FROM storage_deletions"))
    return set(rows.scalars())


def test_model_and_schema_name_the_same_colours() -> None:
    assert set(typing.get_args(EventPrimaryColor)) == set(EVENT_PRIMARY_COLORS)
    assert set(typing.get_args(EventSecondaryColor)) == set(EVENT_SECONDARY_COLORS)
    assert set(typing.get_args(EventBaseColor)) == set(EVENT_BASE_COLORS)


# ── Colours ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestColours:
    async def test_admin_sets_and_clears_it(
        self, async_client: AsyncClient, as_event_admin: None, test_event: Event
    ) -> None:
        r = await async_client.patch(
            f"{API}/events/{test_event.id}",
            json={"primary_color": "teal", "secondary_color": "yellow"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["primary_color"] == "teal"
        assert r.json()["secondary_color"] == "yellow"

        r = await async_client.get(f"{API}/events/{test_event.id}")
        assert r.json()["primary_color"] == "teal"
        assert r.json()["secondary_color"] == "yellow"

        # An explicit null goes back to the app's own colour, one at a time.
        r = await async_client.patch(
            f"{API}/events/{test_event.id}", json={"primary_color": None}
        )
        assert r.status_code == 200
        assert r.json()["primary_color"] is None
        assert r.json()["secondary_color"] == "yellow"

    async def test_admin_sets_and_clears_the_base_tone(
        self, async_client: AsyncClient, as_event_admin: None, test_event: Event
    ) -> None:
        r = await async_client.get(f"{API}/events/{test_event.id}")
        assert r.json()["base_color"] is None

        for tone in ("blue", "primary", "neutral"):
            r = await async_client.patch(
                f"{API}/events/{test_event.id}", json={"base_color": tone}
            )
            assert r.status_code == 200, r.text
            assert r.json()["base_color"] == tone

        r = await async_client.patch(
            f"{API}/events/{test_event.id}", json={"base_color": None}
        )
        assert r.status_code == 200
        assert r.json()["base_color"] is None

    async def test_takes_an_own_colour_in_lower_case(
        self, async_client: AsyncClient, as_event_admin: None, test_event: Event
    ) -> None:
        r = await async_client.patch(
            f"{API}/events/{test_event.id}",
            json={
                "primary_color": "#1E6BB8",
                "secondary_color": "#ffcc00",
                "base_color": "#2E7D32",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["primary_color"] == "#1e6bb8"
        assert r.json()["secondary_color"] == "#ffcc00"
        assert r.json()["base_color"] == "#2e7d32"

        # Any colour: the frontend makes it readable, so a pale one is fine too.
        r = await async_client.patch(
            f"{API}/events/{test_event.id}", json={"primary_color": "#fffde7"}
        )
        assert r.status_code == 200
        assert r.json()["primary_color"] == "#fffde7"

    async def test_dark_tile_is_on_until_switched_off(
        self, async_client: AsyncClient, as_event_admin: None, test_event: Event
    ) -> None:
        r = await async_client.get(f"{API}/events/{test_event.id}")
        assert r.json()["logo_dark_tile"] is True

        r = await async_client.patch(
            f"{API}/events/{test_event.id}", json={"logo_dark_tile": False}
        )
        assert r.status_code == 200, r.text
        assert r.json()["logo_dark_tile"] is False

        # NOT NULL: an explicit null leaves it.
        r = await async_client.patch(
            f"{API}/events/{test_event.id}", json={"logo_dark_tile": None}
        )
        assert r.status_code == 200
        assert r.json()["logo_dark_tile"] is False

    async def test_leaving_it_out_keeps_it(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        test_event.primary_color = "blue"
        test_event.secondary_color = "green"
        test_event.base_color = "rose"
        await db_session.flush()
        r = await async_client.patch(
            f"{API}/events/{test_event.id}", json={"name": "Renamed"}
        )
        assert r.status_code == 200
        assert r.json()["primary_color"] == "blue"
        assert r.json()["secondary_color"] == "green"
        assert r.json()["base_color"] == "rose"

    async def test_unknown_colour_is_422(
        self, async_client: AsyncClient, as_event_admin: None, test_event: Event
    ) -> None:
        for body in (
            # Yellow is too light to read as text, so only a secondary colour.
            {"primary_color": "yellow"},
            {"secondary_color": "chartreuse"},
            {"base_color": "cream"},
            {"primary_color": "#12345"},
            {"primary_color": "#1234567"},
            {"secondary_color": "1e6bb8"},
            {"secondary_color": "#gggggg"},
            {"base_color": "rgb(30, 107, 184)"},
        ):
            r = await async_client.patch(f"{API}/events/{test_event.id}", json=body)
            assert r.status_code == 422, body

    async def test_member_may_not_set_it(
        self, async_client: AsyncClient, test_event: Event
    ) -> None:
        r = await async_client.patch(
            f"{API}/events/{test_event.id}", json={"primary_color": "red"}
        )
        assert r.status_code == 403

    async def test_database_takes_an_own_colour(
        self, db_session: AsyncSession, test_event: Event
    ) -> None:
        for column in ("primary_color", "secondary_color", "base_color"):
            await db_session.execute(
                text(f"UPDATE events SET {column} = '#1e6bb8' WHERE id = :id"),
                {"id": test_event.id},
            )

    async def test_database_refuses_an_unknown_colour(
        self, db_session: AsyncSession, test_event: Event
    ) -> None:
        """The CHECKs back the schema up for writes that bypass it."""
        for column, value in (
            ("primary_color", "chartreuse"),
            ("primary_color", "yellow"),
            ("secondary_color", "chartreuse"),
            ("base_color", "cream"),
            # Own colours only as the schema stores them: six lower-case digits.
            ("primary_color", "#1E6BB8"),
            ("secondary_color", "#12345"),
            ("base_color", "1e6bb8"),
        ):
            with pytest.raises(IntegrityError):
                async with db_session.begin_nested():
                    await db_session.execute(
                        text(f"UPDATE events SET {column} = :v WHERE id = :id"),
                        {"v": value, "id": test_event.id},
                    )


# ── Logo ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestUploadLogo:
    async def test_admin_uploads_and_anyone_can_fetch_it(
        self,
        async_client: AsyncClient,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        r = await async_client.put(
            f"{API}/events/{test_event.id}/logo", files=logo_upload()
        )
        assert r.status_code == 200, r.text
        etag = r.json()["logo_etag"]
        assert isinstance(etag, str) and len(etag) == 64
        # Decorated like every other EventRead.
        assert r.json()["my_role"] == "admin"

        rows = await logo_rows(db_session, test_event.id)
        assert len(rows) == 1
        assert rows[0].etag == etag
        assert rows[0].content_type == "image/webp"
        assert rows[0].storage_key.startswith("event-logos/")

        # The event carries the version and size, so lists can show the logo.
        r = await async_client.get(f"{API}/events/{test_event.id}")
        assert r.json()["logo_etag"] == etag
        assert (r.json()["logo_width"], r.json()["logo_height"]) == (64, 64)

        # No token needed: <img> tags and the invitation page fetch it.
        served = await fetch_file(
            unauthenticated_client, f"{API}/events/{test_event.id}/logo?v={etag}"
        )
        assert served.status_code == 200
        assert served.content == await stored_bytes(db_session, rows[0].storage_key)

    async def test_transparency_survives(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        r = await async_client.put(
            f"{API}/events/{test_event.id}/logo", files=logo_upload()
        )
        assert r.status_code == 200
        [row] = await logo_rows(db_session, test_event.id)
        data = await stored_bytes(db_session, row.storage_key)
        assert data is not None
        with Image.open(io.BytesIO(data)) as img:
            assert img.mode == "RGBA"

    async def test_wide_logo_keeps_its_proportions(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        r = await async_client.put(
            f"{API}/events/{test_event.id}/logo",
            files=logo_upload(size=(2000, 500), mode="RGB"),
        )
        assert r.status_code == 200
        # The size it was stored at, which tells the sidebar it is a wordmark.
        assert (r.json()["logo_width"], r.json()["logo_height"]) == (512, 128)
        [row] = await logo_rows(db_session, test_event.id)
        data = await stored_bytes(db_session, row.storage_key)
        assert data is not None
        with Image.open(io.BytesIO(data)) as img:
            assert img.size == (512, 128)

    async def test_replacing_queues_the_old_file(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        first = await async_client.put(
            f"{API}/events/{test_event.id}/logo", files=logo_upload()
        )
        assert first.status_code == 200
        [old] = await logo_rows(db_session, test_event.id)
        old_key = old.storage_key

        second = await async_client.put(
            f"{API}/events/{test_event.id}/logo",
            files=logo_upload(size=(80, 40), mode="RGB"),
        )
        assert second.status_code == 200
        assert second.json()["logo_etag"] != first.json()["logo_etag"]
        assert (second.json()["logo_width"], second.json()["logo_height"]) == (80, 40)

        rows = await logo_rows(db_session, test_event.id)
        assert len(rows) == 1
        assert rows[0].storage_key != old_key
        assert old_key in await queued_keys(db_session)

    async def test_not_an_image_is_400(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        r = await async_client.put(
            f"{API}/events/{test_event.id}/logo",
            files={"file": ("logo.png", b"not an image", "image/png")},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "event.invalid_logo"
        assert await logo_rows(db_session, test_event.id) == []

    async def test_member_may_not_upload(
        self, async_client: AsyncClient, test_event: Event
    ) -> None:
        r = await async_client.put(
            f"{API}/events/{test_event.id}/logo", files=logo_upload()
        )
        assert r.status_code == 403

    async def test_refused_in_a_demo_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        event = Event(
            name="Demo",
            start_date=dt.date(2026, 10, 10),
            end_date=dt.date(2026, 10, 14),
            status="published",
            visibility="private",
            created_by_id=test_user.id,
            is_sandbox=True,
        )
        db_session.add(event)
        await db_session.flush()
        db_session.add(
            EventMembership(user_id=test_user.id, event_id=event.id, role="owner")
        )
        await db_session.flush()

        r = await async_client.put(f"{API}/events/{event.id}/logo", files=logo_upload())
        assert r.status_code == 403
        assert r.json()["code"] == "sandbox.upload_disabled"

        # The colour stays open to the guest.
        r = await async_client.patch(
            f"{API}/events/{event.id}", json={"primary_color": "violet"}
        )
        assert r.status_code == 200


@pytest.mark.asyncio
class TestServeLogo:
    async def test_conditional_get_is_304(
        self,
        async_client: AsyncClient,
        unauthenticated_client: AsyncClient,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        r = await async_client.put(
            f"{API}/events/{test_event.id}/logo", files=logo_upload()
        )
        etag = r.json()["logo_etag"]
        r = await unauthenticated_client.get(
            f"{API}/events/{test_event.id}/logo",
            headers={"If-None-Match": f'"{etag}"'},
        )
        assert r.status_code == 304
        assert r.headers["etag"] == f'"{etag}"'

    async def test_no_logo_is_404(
        self, unauthenticated_client: AsyncClient, test_event: Event
    ) -> None:
        r = await unauthenticated_client.get(f"{API}/events/{test_event.id}/logo")
        assert r.status_code == 404
        assert r.json()["code"] == "event.logo_not_found"

    async def test_lost_file_is_404(
        self,
        async_client: AsyncClient,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        await async_client.put(
            f"{API}/events/{test_event.id}/logo", files=logo_upload()
        )
        [row] = await logo_rows(db_session, test_event.id)
        await drop_file(db_session, row.storage_key)
        r = await fetch_file(
            unauthenticated_client, f"{API}/events/{test_event.id}/logo"
        )
        assert r.status_code == 404


@pytest.mark.asyncio
class TestDeleteLogo:
    async def test_admin_removes_it(
        self,
        async_client: AsyncClient,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        await async_client.put(
            f"{API}/events/{test_event.id}/logo", files=logo_upload()
        )
        [row] = await logo_rows(db_session, test_event.id)

        r = await async_client.delete(f"{API}/events/{test_event.id}/logo")
        assert r.status_code == 200
        assert r.json()["logo_etag"] is None
        assert r.json()["logo_width"] is None
        assert r.json()["logo_height"] is None
        assert await logo_rows(db_session, test_event.id) == []
        assert row.storage_key in await queued_keys(db_session)

        r = await unauthenticated_client.get(f"{API}/events/{test_event.id}/logo")
        assert r.status_code == 404

    async def test_removing_none_is_fine(
        self, async_client: AsyncClient, as_event_admin: None, test_event: Event
    ) -> None:
        r = await async_client.delete(f"{API}/events/{test_event.id}/logo")
        assert r.status_code == 200
        assert r.json()["logo_etag"] is None

    async def test_member_may_not_remove_it(
        self, async_client: AsyncClient, test_event: Event
    ) -> None:
        r = await async_client.delete(f"{API}/events/{test_event.id}/logo")
        assert r.status_code == 403

    async def test_deleting_the_event_queues_the_file(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        await async_client.put(
            f"{API}/events/{test_event.id}/logo", files=logo_upload()
        )
        [row] = await logo_rows(db_session, test_event.id)
        key = row.storage_key

        # The database cascade, which no Python code sees.
        await db_session.execute(
            text("DELETE FROM events WHERE id = :id"), {"id": test_event.id}
        )
        assert key in await queued_keys(db_session)


# ── Logo for dark mode ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDarkLogo:
    async def test_admin_uploads_it_beside_the_logo(
        self,
        async_client: AsyncClient,
        unauthenticated_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        light = await async_client.put(
            f"{API}/events/{test_event.id}/logo", files=logo_upload()
        )
        r = await async_client.put(
            f"{API}/events/{test_event.id}/logo/dark",
            files=logo_upload(size=(400, 100)),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        dark_etag = body["logo_dark_etag"]
        assert isinstance(dark_etag, str) and len(dark_etag) == 64
        assert (body["logo_dark_width"], body["logo_dark_height"]) == (400, 100)
        # The logo itself is untouched.
        assert body["logo_etag"] == light.json()["logo_etag"]
        assert (body["logo_width"], body["logo_height"]) == (64, 64)

        [row] = await logo_rows(db_session, test_event.id, "dark")
        assert row.etag == dark_etag
        assert len(await logo_rows(db_session, test_event.id)) == 2

        served = await fetch_file(
            unauthenticated_client,
            f"{API}/events/{test_event.id}/logo/dark?v={dark_etag}",
        )
        assert served.status_code == 200
        assert served.content == await stored_bytes(db_session, row.storage_key)

    async def test_without_one_it_is_404(
        self,
        async_client: AsyncClient,
        unauthenticated_client: AsyncClient,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        # A logo alone is not a dark one.
        await async_client.put(
            f"{API}/events/{test_event.id}/logo", files=logo_upload()
        )
        r = await unauthenticated_client.get(f"{API}/events/{test_event.id}/logo/dark")
        assert r.status_code == 404
        assert r.json()["code"] == "event.logo_not_found"

    async def test_each_is_removed_on_its_own(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        await async_client.put(
            f"{API}/events/{test_event.id}/logo", files=logo_upload()
        )
        await async_client.put(
            f"{API}/events/{test_event.id}/logo/dark", files=logo_upload()
        )
        [dark] = await logo_rows(db_session, test_event.id, "dark")

        r = await async_client.delete(f"{API}/events/{test_event.id}/logo/dark")
        assert r.status_code == 200
        assert r.json()["logo_dark_etag"] is None
        assert r.json()["logo_dark_width"] is None
        assert r.json()["logo_etag"] is not None
        assert await logo_rows(db_session, test_event.id, "dark") == []
        assert dark.storage_key in await queued_keys(db_session)

        # The logo takes its dark version with it.
        await async_client.put(
            f"{API}/events/{test_event.id}/logo/dark", files=logo_upload()
        )
        r = await async_client.delete(f"{API}/events/{test_event.id}/logo")
        assert r.status_code == 200
        assert r.json()["logo_etag"] is None
        assert r.json()["logo_dark_etag"] is None
        assert await logo_rows(db_session, test_event.id) == []

    async def test_needs_the_logo_first(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        r = await async_client.put(
            f"{API}/events/{test_event.id}/logo/dark", files=logo_upload()
        )
        assert r.status_code == 409
        assert r.json()["code"] == "event.logo_required"
        assert await logo_rows(db_session, test_event.id) == []

    async def test_member_may_not_touch_it(
        self, async_client: AsyncClient, test_event: Event
    ) -> None:
        r = await async_client.put(
            f"{API}/events/{test_event.id}/logo/dark", files=logo_upload()
        )
        assert r.status_code == 403
        r = await async_client.delete(f"{API}/events/{test_event.id}/logo/dark")
        assert r.status_code == 403

    async def test_database_holds_one_per_variant(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        await async_client.put(
            f"{API}/events/{test_event.id}/logo", files=logo_upload()
        )
        await async_client.put(
            f"{API}/events/{test_event.id}/logo/dark", files=logo_upload()
        )
        for variant in ("dark", "sepia"):
            with pytest.raises(IntegrityError):
                async with db_session.begin_nested():
                    await db_session.execute(
                        text(
                            "INSERT INTO event_logos (id, created_at, updated_at, "
                            "event_id, storage_key, etag, variant) VALUES "
                            "(:id, now(), now(), :event, :key, :etag, :variant)"
                        ),
                        {
                            "id": uuid.uuid4(),
                            "event": test_event.id,
                            "key": f"event-logos/{uuid.uuid4()}",
                            "etag": "b" * 64,
                            "variant": variant,
                        },
                    )


# ── Carried along ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCarriedAlong:
    async def test_a_clone_wears_the_same_look(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        as_event_admin: None,
        test_event: Event,
    ) -> None:
        await async_client.patch(
            f"{API}/events/{test_event.id}",
            json={
                "primary_color": "orange",
                "secondary_color": "teal",
                "base_color": "green",
                "logo_dark_tile": False,
            },
        )
        up = await async_client.put(
            f"{API}/events/{test_event.id}/logo",
            files=logo_upload(size=(300, 100), mode="RGB"),
        )
        etag = up.json()["logo_etag"]
        up = await async_client.put(
            f"{API}/events/{test_event.id}/logo/dark",
            files=logo_upload(size=(200, 100)),
        )
        dark_etag = up.json()["logo_dark_etag"]

        r = await async_client.post(
            f"{API}/events/{test_event.id}/clone",
            json={"name": "Next year", "start_date": "2027-06-01", "tasks": []},
        )
        assert r.status_code == 201, r.text
        clone = r.json()["event"]
        assert clone["primary_color"] == "orange"
        assert clone["secondary_color"] == "teal"
        assert clone["base_color"] == "green"
        assert clone["logo_dark_tile"] is False
        assert clone["logo_etag"] == etag
        assert (clone["logo_width"], clone["logo_height"]) == (300, 100)
        assert clone["logo_dark_etag"] == dark_etag
        assert (clone["logo_dark_width"], clone["logo_dark_height"]) == (200, 100)

        # Its own files, so removing one event's logo leaves the other's.
        for variant in ("light", "dark"):
            [source_logo] = await logo_rows(db_session, test_event.id, variant)
            [clone_logo] = await logo_rows(db_session, uuid.UUID(clone["id"]), variant)
            assert clone_logo.storage_key != source_logo.storage_key
            assert await stored_bytes(db_session, clone_logo.storage_key) == (
                await stored_bytes(db_session, source_logo.storage_key)
            )

    async def test_a_clone_without_a_logo_has_none(
        self, async_client: AsyncClient, as_event_admin: None, test_event: Event
    ) -> None:
        r = await async_client.post(
            f"{API}/events/{test_event.id}/clone",
            json={"name": "Next year", "start_date": "2027-06-01", "tasks": []},
        )
        assert r.status_code == 201, r.text
        assert r.json()["event"]["logo_etag"] is None
        assert r.json()["event"]["logo_dark_etag"] is None
        assert r.json()["event"]["primary_color"] is None
        assert r.json()["event"]["secondary_color"] is None
        assert r.json()["event"]["base_color"] is None
        assert r.json()["event"]["logo_dark_tile"] is True

    async def test_the_invitation_shows_it(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_private_event: Event,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        test_private_event.primary_color = "#1e6bb8"
        test_private_event.secondary_color = "yellow"
        test_private_event.logo_etag = "a" * 64
        test_private_event.logo_width, test_private_event.logo_height = 400, 100
        test_private_event.base_color = "violet"
        test_private_event.logo_dark_etag = "c" * 64
        test_private_event.logo_dark_width = 300
        test_private_event.logo_dark_height = 100
        test_private_event.logo_dark_tile = False
        await db_session.flush()
        invitation = await crud_invitation.create(
            db_session,
            event_id=test_private_event.id,
            email=test_user.email,
            role="member",
            invited_by_id=test_admin_user.id,
            expires_in_days=14,
        )
        r = await async_client.get(f"{API}/invitations/{invitation.token}")
        assert r.status_code == 200
        assert r.json()["event_primary_color"] == "#1e6bb8"
        assert r.json()["event_secondary_color"] == "yellow"
        assert r.json()["event_logo_etag"] == "a" * 64
        assert r.json()["event_logo_width"] == 400
        assert r.json()["event_logo_height"] == 100
        assert r.json()["event_base_color"] == "violet"
        assert r.json()["event_logo_dark_etag"] == "c" * 64
        assert r.json()["event_logo_dark_width"] == 300
        assert r.json()["event_logo_dark_height"] == 100
        assert r.json()["event_logo_dark_tile"] is False
