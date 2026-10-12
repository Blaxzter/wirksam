"""HTTP tests for the venue map routes (#185).

Covers ``app/api/routes/venue_map.py``: plan CRUD and ordering, the plan
image upload and member-only serve path, markers, and the member map view.

Cast (see ``tests/fixtures/events.py``): on ``test_event`` the default
``async_client`` identity ``test_user`` is a plain *member*,
``test_event_admin_user`` (``as_event_admin``) is an *admin*, and
``test_outsider_user`` (``as_outsider``) belongs to nothing. ``test_event`` is
public and published, so an outsider can see the event itself but not its map.
"""

import datetime as dt
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.booking import Booking
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.location import Location
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.models.venue_plan import VenueMarker, VenuePlan, VenuePlanImage
from tests.fixtures.locations import PLAN_HEIGHT, PLAN_WIDTH, make_png

API = "/api/v1"


def png_upload(
    width: int = 400, height: int = 300
) -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("plan.png", make_png(width, height), "image/png")}


async def _add_location(db_session: AsyncSession, event: Event, name: str) -> Location:
    loc = Location(event_id=event.id, name=name)
    db_session.add(loc)
    await db_session.flush()
    await db_session.refresh(loc)
    return loc


async def _add_plan(
    db_session: AsyncSession, event: Event, name: str, sort_order: int
) -> VenuePlan:
    plan = VenuePlan(event_id=event.id, name=name, sort_order=sort_order)
    db_session.add(plan)
    await db_session.flush()
    await db_session.refresh(plan)
    return plan


# ── Plans ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPlanCrud:
    async def test_admin_creates_plan_appended_after_existing(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_event: Event,
        test_venue_plan: VenuePlan,
    ) -> None:
        r = await async_client.post(
            f"{API}/events/{test_event.id}/venue-plans", json={"name": "  Upstairs "}
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "Upstairs"
        assert body["event_id"] == str(test_event.id)
        assert body["sort_order"] == test_venue_plan.sort_order + 1
        assert body["image_etag"] is None
        assert body["markers"] == []

    async def test_first_plan_gets_sort_order_zero(
        self, async_client: AsyncClient, as_event_admin: None, test_event: Event
    ) -> None:
        r = await async_client.post(
            f"{API}/events/{test_event.id}/venue-plans", json={"name": "Hall"}
        )
        assert r.status_code == 201
        assert r.json()["sort_order"] == 0

    async def test_blank_name_is_422(
        self, async_client: AsyncClient, as_event_admin: None, test_event: Event
    ) -> None:
        r = await async_client.post(
            f"{API}/events/{test_event.id}/venue-plans", json={"name": "   "}
        )
        assert r.status_code == 422

    async def test_member_gets_403(
        self, async_client: AsyncClient, test_event: Event
    ) -> None:
        r = await async_client.post(
            f"{API}/events/{test_event.id}/venue-plans", json={"name": "Hall"}
        )
        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"

    async def test_outsider_gets_404_on_public_event(
        self, async_client: AsyncClient, as_outsider: None, test_event: Event
    ) -> None:
        r = await async_client.post(
            f"{API}/events/{test_event.id}/venue-plans", json={"name": "Hall"}
        )
        assert r.status_code == 404
        assert r.json()["code"] == "event.not_found"

    async def test_non_member_gets_404_on_private_event(
        self, async_client: AsyncClient, test_private_event: Event
    ) -> None:
        r = await async_client.post(
            f"{API}/events/{test_private_event.id}/venue-plans", json={"name": "Hall"}
        )
        assert r.status_code == 404

    async def test_unknown_event_404(self, async_client: AsyncClient) -> None:
        r = await async_client.post(
            f"{API}/events/{uuid.uuid4()}/venue-plans", json={"name": "Hall"}
        )
        assert r.status_code == 404

    async def test_rename(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
        test_location_marker: VenueMarker,
    ) -> None:
        r = await async_client.patch(
            f"{API}/venue-plans/{test_venue_plan.id}", json={"name": "Erdgeschoss"}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "Erdgeschoss"
        assert [m["id"] for m in body["markers"]] == [str(test_location_marker.id)]

    async def test_patch_without_name_is_a_no_op(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
    ) -> None:
        r = await async_client.patch(f"{API}/venue-plans/{test_venue_plan.id}", json={})
        assert r.status_code == 200
        assert r.json()["name"] == test_venue_plan.name

    async def test_rename_member_403_unknown_404(
        self,
        async_client: AsyncClient,
        test_venue_plan: VenuePlan,
    ) -> None:
        url = f"{API}/venue-plans/{test_venue_plan.id}"
        r = await async_client.patch(url, json={"name": "X"})
        assert r.status_code == 403

        r = await async_client.patch(
            f"{API}/venue-plans/{uuid.uuid4()}", json={"name": "X"}
        )
        assert r.status_code == 404
        assert r.json()["code"] == "venue_plan.not_found"

    async def test_rename_outsider_404(
        self,
        async_client: AsyncClient,
        as_outsider: None,
        test_venue_plan: VenuePlan,
    ) -> None:
        r = await async_client.patch(
            f"{API}/venue-plans/{test_venue_plan.id}", json={"name": "X"}
        )
        assert r.status_code == 404
        assert r.json()["code"] == "event.not_found"

    async def test_delete_removes_image_and_markers(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_venue_plan: VenuePlan,
        test_location_marker: VenueMarker,
    ) -> None:
        plan_id = test_venue_plan.id
        marker_id = test_location_marker.id
        r = await async_client.delete(f"{API}/venue-plans/{plan_id}")
        assert r.status_code == 204

        db_session.expunge_all()
        assert await db_session.get(VenuePlan, plan_id) is None
        assert await db_session.get(VenueMarker, marker_id) is None
        images = await db_session.execute(
            select(VenuePlanImage).where(col(VenuePlanImage.plan_id) == plan_id)
        )
        assert images.scalars().first() is None

    async def test_delete_member_403(
        self, async_client: AsyncClient, test_venue_plan: VenuePlan
    ) -> None:
        r = await async_client.delete(f"{API}/venue-plans/{test_venue_plan.id}")
        assert r.status_code == 403

    async def test_delete_unknown_404(
        self, async_client: AsyncClient, as_event_admin: None
    ) -> None:
        r = await async_client.delete(f"{API}/venue-plans/{uuid.uuid4()}")
        assert r.status_code == 404


@pytest.mark.asyncio
class TestPlanOrder:
    async def test_reorder(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
    ) -> None:
        a = await _add_plan(db_session, test_event, "A", 0)
        b = await _add_plan(db_session, test_event, "B", 1)
        c = await _add_plan(db_session, test_event, "C", 2)

        new_order = [str(c.id), str(a.id), str(b.id)]
        r = await async_client.put(
            f"{API}/events/{test_event.id}/venue-plans/order",
            json={"plan_ids": new_order},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert [p["id"] for p in body] == new_order
        assert [p["sort_order"] for p in body] == [0, 1, 2]

    @pytest.mark.parametrize("variant", ["missing", "extra", "duplicate"])
    async def test_mismatch_is_422(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
        variant: str,
    ) -> None:
        a = await _add_plan(db_session, test_event, "A", 0)
        b = await _add_plan(db_session, test_event, "B", 1)
        ids = {
            "missing": [str(a.id)],
            "extra": [str(a.id), str(b.id), str(uuid.uuid4())],
            "duplicate": [str(a.id), str(b.id), str(a.id)],
        }[variant]
        r = await async_client.put(
            f"{API}/events/{test_event.id}/venue-plans/order", json={"plan_ids": ids}
        )
        assert r.status_code == 422
        assert r.json()["code"] == "venue_plan.order_mismatch"

    async def test_member_403(
        self, async_client: AsyncClient, test_event: Event, test_venue_plan: VenuePlan
    ) -> None:
        r = await async_client.put(
            f"{API}/events/{test_event.id}/venue-plans/order",
            json={"plan_ids": [str(test_venue_plan.id)]},
        )
        assert r.status_code == 403


# ── Plan image ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPlanImageUpload:
    async def test_valid_upload_sets_etag_and_size(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
    ) -> None:
        plan = await _add_plan(db_session, test_event, "Hall", 0)
        r = await async_client.put(
            f"{API}/venue-plans/{plan.id}/image", files=png_upload(400, 300)
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["image_etag"]) == 64
        assert (body["image_width"], body["image_height"]) == (400, 300)

        stored = await db_session.execute(
            select(VenuePlanImage).where(col(VenuePlanImage.plan_id) == plan.id)
        )
        row = stored.scalars().one()
        assert row.etag == body["image_etag"]
        assert row.content_type == "image/webp"

    async def test_large_image_is_shrunk_to_plan_max_dim(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
    ) -> None:
        plan = await _add_plan(db_session, test_event, "Hall", 0)
        r = await async_client.put(
            f"{API}/venue-plans/{plan.id}/image", files=png_upload(3000, 1500)
        )
        assert r.status_code == 200, r.text
        assert (r.json()["image_width"], r.json()["image_height"]) == (2560, 1280)

    async def test_replace_keeps_markers_and_changes_etag(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_venue_plan: VenuePlan,
        test_location_marker: VenueMarker,
    ) -> None:
        old_etag = test_venue_plan.image_etag
        r = await async_client.put(
            f"{API}/venue-plans/{test_venue_plan.id}/image", files=png_upload(200, 100)
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["image_etag"] != old_etag
        assert (body["image_width"], body["image_height"]) == (200, 100)
        assert body["markers"] == [
            {
                "id": str(test_location_marker.id),
                "plan_id": str(test_venue_plan.id),
                "kind": "location",
                "location_id": str(test_location_marker.location_id),
                "label": None,
                "x": 0.25,
                "y": 0.75,
            }
        ]
        rows = await db_session.execute(
            select(VenuePlanImage).where(
                col(VenuePlanImage.plan_id) == test_venue_plan.id
            )
        )
        assert len(rows.scalars().all()) == 1

    async def test_invalid_bytes_400(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
    ) -> None:
        r = await async_client.put(
            f"{API}/venue-plans/{test_venue_plan.id}/image",
            files={"file": ("plan.png", b"definitely not an image", "image/png")},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "venue_plan.invalid_image"

    async def test_empty_file_400(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
    ) -> None:
        r = await async_client.put(
            f"{API}/venue-plans/{test_venue_plan.id}/image",
            files={"file": ("plan.png", b"", "image/png")},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "venue_plan.invalid_image"

    async def test_oversized_upload_rejected_before_reading(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Shrink the cap rather than posting 20 MB through the test client.
        monkeypatch.setattr("app.api.routes.venue_map.MAX_INPUT_BYTES", 10)
        r = await async_client.put(
            f"{API}/venue-plans/{test_venue_plan.id}/image", files=png_upload()
        )
        assert r.status_code == 400
        assert r.json()["code"] == "venue_plan.invalid_image"

    async def test_member_403(
        self, async_client: AsyncClient, test_venue_plan: VenuePlan
    ) -> None:
        r = await async_client.put(
            f"{API}/venue-plans/{test_venue_plan.id}/image", files=png_upload()
        )
        assert r.status_code == 403

    async def test_outsider_404(
        self, async_client: AsyncClient, as_outsider: None, test_venue_plan: VenuePlan
    ) -> None:
        r = await async_client.put(
            f"{API}/venue-plans/{test_venue_plan.id}/image", files=png_upload()
        )
        assert r.status_code == 404

    async def test_sandbox_refused(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """A sandbox guest owns their demo, but may not upload images into it."""
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
        plan = await _add_plan(db_session, event, "Venue", 0)

        r = await async_client.put(
            f"{API}/venue-plans/{plan.id}/image", files=png_upload()
        )
        assert r.status_code == 403
        assert r.json()["code"] == "sandbox.upload_disabled"

        # Every other map edit stays open to the guest.
        r = await async_client.patch(
            f"{API}/venue-plans/{plan.id}", json={"name": "Gelände"}
        )
        assert r.status_code == 200

    async def test_sandbox_guest_refused_in_own_regular_event(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """A guest can create a normal event; uploading there is refused too."""
        test_user.is_sandbox = True
        event = Event(
            name="Mine",
            start_date=dt.date(2026, 10, 10),
            end_date=dt.date(2026, 10, 14),
            status="published",
            visibility="private",
            created_by_id=test_user.id,
        )
        db_session.add(event)
        await db_session.flush()
        db_session.add(
            EventMembership(user_id=test_user.id, event_id=event.id, role="owner")
        )
        plan = await _add_plan(db_session, event, "Venue", 0)

        r = await async_client.put(
            f"{API}/venue-plans/{plan.id}/image", files=png_upload()
        )
        assert r.status_code == 403
        assert r.json()["code"] == "sandbox.upload_disabled"

    async def test_over_plan_pixel_cap_400(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # The decoded-size cap, not the file size, is what bounds memory.
        monkeypatch.setattr("app.logic.venue_map.PLAN_MAX_PIXELS", 1000)
        r = await async_client.put(
            f"{API}/venue-plans/{test_venue_plan.id}/image", files=png_upload(40, 30)
        )
        assert r.status_code == 400
        assert r.json()["code"] == "venue_plan.invalid_image"


@pytest.mark.asyncio
class TestPlanImageServe:
    async def test_member_gets_bytes_with_private_caching(
        self, async_client: AsyncClient, test_venue_plan: VenuePlan
    ) -> None:
        r = await async_client.get(f"{API}/venue-plans/{test_venue_plan.id}/image")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert r.headers["etag"] == f'"{test_venue_plan.image_etag}"'
        assert r.headers["cache-control"] == "private, max-age=604800"
        assert r.content == make_png(PLAN_WIDTH, PLAN_HEIGHT)

    async def test_if_none_match_304(
        self, async_client: AsyncClient, test_venue_plan: VenuePlan
    ) -> None:
        etag = f'"{test_venue_plan.image_etag}"'
        r = await async_client.get(
            f"{API}/venue-plans/{test_venue_plan.id}/image",
            headers={"If-None-Match": etag},
        )
        assert r.status_code == 304
        assert r.headers["etag"] == etag
        assert r.content == b""

    async def test_stale_if_none_match_gets_200(
        self, async_client: AsyncClient, test_venue_plan: VenuePlan
    ) -> None:
        r = await async_client.get(
            f"{API}/venue-plans/{test_venue_plan.id}/image",
            headers={"If-None-Match": '"stale"'},
        )
        assert r.status_code == 200

    async def test_non_member_of_public_event_404(
        self, async_client: AsyncClient, as_outsider: None, test_venue_plan: VenuePlan
    ) -> None:
        r = await async_client.get(f"{API}/venue-plans/{test_venue_plan.id}/image")
        assert r.status_code == 404
        assert r.json()["code"] == "event.not_found"

    async def test_non_member_of_private_event_404(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_private_event: Event,
    ) -> None:
        plan = await _add_plan(db_session, test_private_event, "Hidden", 0)
        r = await async_client.get(f"{API}/venue-plans/{plan.id}/image")
        assert r.status_code == 404

    async def test_plan_without_image_404(
        self, async_client: AsyncClient, db_session: AsyncSession, test_event: Event
    ) -> None:
        plan = await _add_plan(db_session, test_event, "Empty", 0)
        r = await async_client.get(f"{API}/venue-plans/{plan.id}/image")
        assert r.status_code == 404
        assert r.json()["code"] == "venue_plan.image_not_found"

    async def test_unknown_plan_404(self, async_client: AsyncClient) -> None:
        r = await async_client.get(f"{API}/venue-plans/{uuid.uuid4()}/image")
        assert r.status_code == 404
        assert r.json()["code"] == "venue_plan.not_found"


# ── Markers ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMarkerCreate:
    async def test_location_marker(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
        test_location: Location,
    ) -> None:
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/markers",
            json={
                "kind": "location",
                "location_id": str(test_location.id),
                "x": 0.5,
                "y": 0.1,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["plan_id"] == str(test_venue_plan.id)
        assert body["location_id"] == str(test_location.id)
        assert (body["x"], body["y"]) == (0.5, 0.1)

    async def test_generic_marker_without_location(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
    ) -> None:
        for _ in range(2):  # generic markers are not limited per plan
            r = await async_client.post(
                f"{API}/venue-plans/{test_venue_plan.id}/markers",
                json={"kind": "first_aid", "label": "Sanitäter", "x": 0, "y": 1},
            )
            assert r.status_code == 201, r.text
            assert r.json()["location_id"] is None
            assert r.json()["label"] == "Sanitäter"

    async def test_location_kind_without_id_422(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
    ) -> None:
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/markers",
            json={"kind": "location", "x": 0.5, "y": 0.5},
        )
        assert r.status_code == 422
        assert "venue_marker.location_required" in r.text

    async def test_id_with_generic_kind_422(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
        test_location: Location,
    ) -> None:
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/markers",
            json={
                "kind": "toilets",
                "location_id": str(test_location.id),
                "x": 0.5,
                "y": 0.5,
            },
        )
        assert r.status_code == 422
        assert "venue_marker.location_required" in r.text

    async def test_out_of_range_422(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
    ) -> None:
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/markers",
            json={"kind": "parking", "x": 1.2, "y": 0.5},
        )
        assert r.status_code == 422

    async def test_foreign_location_422(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_venue_plan: VenuePlan,
        test_draft_event: Event,
    ) -> None:
        foreign = await _add_location(db_session, test_draft_event, "Elsewhere")
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/markers",
            json={"kind": "location", "location_id": str(foreign.id), "x": 0, "y": 0},
        )
        assert r.status_code == 422
        assert r.json()["code"] == "location.wrong_event"

    async def test_duplicate_location_on_same_plan_409(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
        test_location_marker: VenueMarker,
    ) -> None:
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/markers",
            json={
                "kind": "location",
                "location_id": str(test_location_marker.location_id),
                "x": 0.1,
                "y": 0.1,
            },
        )
        assert r.status_code == 409
        assert r.json()["code"] == "venue_marker.duplicate_location"

    async def test_unique_constraint_race_is_409(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_venue_plan: VenuePlan,
        test_location_marker: VenueMarker,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If the pre-check loses a race, the unique constraint still answers 409
        and the request's transaction stays usable."""

        async def _no_clash(*_args: Any, **_kwargs: Any) -> None:
            return None

        monkeypatch.setattr(
            "app.api.routes.venue_map.crud_venue_map.get_marker_for_location",
            _no_clash,
        )
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/markers",
            json={
                "kind": "location",
                "location_id": str(test_location_marker.location_id),
                "x": 0.1,
                "y": 0.1,
            },
        )
        assert r.status_code == 409
        assert r.json()["code"] == "venue_marker.duplicate_location"
        assert await db_session.get(VenueMarker, test_location_marker.id) is not None

    async def test_same_location_on_another_plan_ok(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
        test_location_marker: VenueMarker,
    ) -> None:
        other = await _add_plan(db_session, test_event, "Upstairs", 1)
        r = await async_client.post(
            f"{API}/venue-plans/{other.id}/markers",
            json={
                "kind": "location",
                "location_id": str(test_location_marker.location_id),
                "x": 0.9,
                "y": 0.9,
            },
        )
        assert r.status_code == 201, r.text

    async def test_member_403_unknown_plan_404(
        self,
        async_client: AsyncClient,
        test_venue_plan: VenuePlan,
    ) -> None:
        payload = {"kind": "entrance", "x": 0.5, "y": 0.5}
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/markers", json=payload
        )
        assert r.status_code == 403
        r = await async_client.post(
            f"{API}/venue-plans/{uuid.uuid4()}/markers", json=payload
        )
        assert r.status_code == 404
        assert r.json()["code"] == "venue_plan.not_found"

    async def test_outsider_404(
        self, async_client: AsyncClient, as_outsider: None, test_venue_plan: VenuePlan
    ) -> None:
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/markers",
            json={"kind": "entrance", "x": 0.5, "y": 0.5},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
class TestMarkerUpdateDelete:
    async def test_move(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_location_marker: VenueMarker,
    ) -> None:
        r = await async_client.patch(
            f"{API}/venue-markers/{test_location_marker.id}",
            json={"x": 0.6, "y": 0.4},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert (body["x"], body["y"]) == (0.6, 0.4)
        assert body["kind"] == "location"
        assert body["location_id"] == str(test_location_marker.location_id)

    @pytest.mark.parametrize("payload", [{"x": 1.01}, {"y": -0.1}])
    async def test_out_of_range_422(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_location_marker: VenueMarker,
        payload: dict[str, float],
    ) -> None:
        r = await async_client.patch(
            f"{API}/venue-markers/{test_location_marker.id}", json=payload
        )
        assert r.status_code == 422

    async def test_switch_to_generic_requires_clearing_location(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_location_marker: VenueMarker,
    ) -> None:
        url = f"{API}/venue-markers/{test_location_marker.id}"
        r = await async_client.patch(url, json={"kind": "info_desk"})
        assert r.status_code == 422
        assert r.json()["code"] == "venue_marker.location_required"

        r = await async_client.patch(
            url, json={"kind": "info_desk", "location_id": None, "label": "Info"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["location_id"] is None
        assert r.json()["label"] == "Info"

    async def test_clearing_location_alone_422(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_location_marker: VenueMarker,
    ) -> None:
        r = await async_client.patch(
            f"{API}/venue-markers/{test_location_marker.id}",
            json={"location_id": None},
        )
        assert r.status_code == 422
        assert r.json()["code"] == "venue_marker.location_required"

    async def test_null_kind_and_coordinates_are_ignored(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_location_marker: VenueMarker,
    ) -> None:
        r = await async_client.patch(
            f"{API}/venue-markers/{test_location_marker.id}",
            json={"kind": None, "x": None, "y": None},
        )
        assert r.status_code == 200
        body = r.json()
        assert (body["kind"], body["x"], body["y"]) == ("location", 0.25, 0.75)

    async def test_repoint_to_other_location(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
        test_location_marker: VenueMarker,
    ) -> None:
        other = await _add_location(db_session, test_event, "Kitchen")
        r = await async_client.patch(
            f"{API}/venue-markers/{test_location_marker.id}",
            json={"location_id": str(other.id)},
        )
        assert r.status_code == 200, r.text
        assert r.json()["location_id"] == str(other.id)

    async def test_repoint_to_foreign_location_422(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_draft_event: Event,
        test_location_marker: VenueMarker,
    ) -> None:
        foreign = await _add_location(db_session, test_draft_event, "Elsewhere")
        r = await async_client.patch(
            f"{API}/venue-markers/{test_location_marker.id}",
            json={"location_id": str(foreign.id)},
        )
        assert r.status_code == 422
        assert r.json()["code"] == "location.wrong_event"

    async def test_generic_to_location_already_on_plan_409(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_venue_plan: VenuePlan,
        test_location_marker: VenueMarker,
    ) -> None:
        generic = VenueMarker(plan_id=test_venue_plan.id, kind="entrance", x=0, y=0)
        db_session.add(generic)
        await db_session.flush()
        r = await async_client.patch(
            f"{API}/venue-markers/{generic.id}",
            json={
                "kind": "location",
                "location_id": str(test_location_marker.location_id),
            },
        )
        assert r.status_code == 409
        assert r.json()["code"] == "venue_marker.duplicate_location"

    async def test_unique_constraint_race_on_patch_is_409(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_venue_plan: VenuePlan,
        test_location_marker: VenueMarker,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        generic = VenueMarker(plan_id=test_venue_plan.id, kind="entrance", x=0, y=0)
        db_session.add(generic)
        await db_session.flush()

        async def _no_clash(*_args: Any, **_kwargs: Any) -> None:
            return None

        monkeypatch.setattr(
            "app.api.routes.venue_map.crud_venue_map.get_marker_for_location",
            _no_clash,
        )
        r = await async_client.patch(
            f"{API}/venue-markers/{generic.id}",
            json={
                "kind": "location",
                "location_id": str(test_location_marker.location_id),
            },
        )
        assert r.status_code == 409
        assert r.json()["code"] == "venue_marker.duplicate_location"

    async def test_member_403_unknown_404(
        self,
        async_client: AsyncClient,
        test_location_marker: VenueMarker,
    ) -> None:
        url = f"{API}/venue-markers/{test_location_marker.id}"
        assert (await async_client.patch(url, json={"x": 0.1})).status_code == 403
        assert (await async_client.delete(url)).status_code == 403

        unknown = f"{API}/venue-markers/{uuid.uuid4()}"
        r = await async_client.patch(unknown, json={"x": 0.1})
        assert r.status_code == 404
        assert r.json()["code"] == "venue_marker.not_found"
        assert (await async_client.delete(unknown)).status_code == 404

    async def test_outsider_404(
        self,
        async_client: AsyncClient,
        as_outsider: None,
        test_location_marker: VenueMarker,
    ) -> None:
        url = f"{API}/venue-markers/{test_location_marker.id}"
        assert (await async_client.patch(url, json={"x": 0.1})).status_code == 404
        assert (await async_client.delete(url)).status_code == 404

    async def test_delete(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_location_marker: VenueMarker,
        test_location: Location,
    ) -> None:
        marker_id = test_location_marker.id
        r = await async_client.delete(f"{API}/venue-markers/{marker_id}")
        assert r.status_code == 204
        db_session.expunge_all()
        assert await db_session.get(VenueMarker, marker_id) is None
        # The location itself is untouched.
        assert await db_session.get(Location, test_location.id) is not None


# ── Member map view ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestVenueMapView:
    async def test_plans_ordered_with_markers_and_locations(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_venue_plan: VenuePlan,
        test_location_marker: VenueMarker,
        test_location: Location,
    ) -> None:
        # Inserted first but sorted before the fixture plan.
        first = await _add_plan(db_session, test_event, "Parking", -1)
        later = await _add_plan(db_session, test_event, "Upstairs", 5)
        generic = VenueMarker(plan_id=later.id, kind="toilets", x=0.3, y=0.3)
        db_session.add(generic)
        await db_session.flush()
        other_loc = await _add_location(db_session, test_event, "Altar")

        r = await async_client.get(
            f"{API}/events/{test_event.id}/venue-map", params={"on": "2026-06-11"}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["event_id"] == str(test_event.id)
        assert body["on"] == "2026-06-11"
        assert [p["id"] for p in body["plans"]] == [
            str(first.id),
            str(test_venue_plan.id),
            str(later.id),
        ]
        assert body["plans"][0]["markers"] == []
        assert [m["id"] for m in body["plans"][1]["markers"]] == [
            str(test_location_marker.id)
        ]
        assert [m["kind"] for m in body["plans"][2]["markers"]] == ["toilets"]
        # Locations alphabetical, case-insensitive.
        assert [loc["id"] for loc in body["locations"]] == [
            str(other_loc.id),
            str(test_location.id),
        ]
        assert body["locations"][1]["description"] == test_location.description
        assert body["my_location_ids"] == []

    async def test_defaults_to_today(
        self, async_client: AsyncClient, test_event: Event
    ) -> None:
        r = await async_client.get(f"{API}/events/{test_event.id}/venue-map")
        assert r.status_code == 200
        assert r.json()["on"] == dt.date.today().isoformat()
        assert r.json()["plans"] == []

    async def test_my_location_ids_only_my_active_bookings_on_day(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_draft_event: Event,
        test_task: Task,
        test_user: User,
        test_event_admin_user: User,
    ) -> None:
        day = dt.date(2026, 6, 11)
        mine = await _add_location(db_session, test_event, "Mine")
        mine_twice = await _add_location(db_session, test_event, "Mine twice")
        other_day = await _add_location(db_session, test_event, "Other day")
        someone_else = await _add_location(db_session, test_event, "Someone else")
        cancelled = await _add_location(db_session, test_event, "Cancelled")

        other_task = Task(
            name="Elsewhere",
            start_date=day,
            end_date=day,
            status="published",
            event_id=test_draft_event.id,
        )
        db_session.add(other_task)
        await db_session.flush()
        other_event_loc = await _add_location(db_session, test_draft_event, "Theirs")

        async def book(
            loc: Location | None,
            *,
            on: dt.date = day,
            user: User = test_user,
            status: str = "confirmed",
            task: Task = test_task,
        ) -> None:
            shift = Shift(
                task_id=task.id,
                title="Dienst",
                date=on,
                start_time=dt.time(9),
                end_time=dt.time(11),
                max_bookings=5,
                location=loc.name if loc else "Free text",
                location_id=loc.id if loc else None,
            )
            db_session.add(shift)
            await db_session.flush()
            db_session.add(Booking(shift_id=shift.id, user_id=user.id, status=status))
            await db_session.flush()

        await book(mine)
        await book(mine_twice)
        await book(mine_twice)
        await book(None)  # free text only
        await book(other_day, on=day + dt.timedelta(days=1))
        await book(someone_else, user=test_event_admin_user)
        await book(cancelled, status="cancelled")
        await book(other_event_loc, task=other_task)

        r = await async_client.get(
            f"{API}/events/{test_event.id}/venue-map", params={"on": day.isoformat()}
        )
        assert r.status_code == 200, r.text
        assert sorted(r.json()["my_location_ids"]) == sorted(
            [str(mine.id), str(mine_twice.id)]
        )

    async def test_non_member_of_public_event_404(
        self, async_client: AsyncClient, as_outsider: None, test_event: Event
    ) -> None:
        r = await async_client.get(f"{API}/events/{test_event.id}/venue-map")
        assert r.status_code == 404
        assert r.json()["code"] == "event.not_found"

    async def test_non_member_of_private_event_404(
        self, async_client: AsyncClient, test_private_event: Event
    ) -> None:
        r = await async_client.get(f"{API}/events/{test_private_event.id}/venue-map")
        assert r.status_code == 404

    async def test_admin_sees_map(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_event: Event,
        test_venue_plan: VenuePlan,
    ) -> None:
        r = await async_client.get(f"{API}/events/{test_event.id}/venue-map")
        assert r.status_code == 200
        assert [p["id"] for p in r.json()["plans"]] == [str(test_venue_plan.id)]
