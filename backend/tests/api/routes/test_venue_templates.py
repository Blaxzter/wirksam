"""HTTP tests for venue plan templates.

Covers ``app/api/routes/venue_templates.py`` and the two template routes in
``venue_map.py``: saving a plan as a template, and starting a plan from one.

Cast (see ``tests/fixtures/events.py``): on ``test_event`` the default
``async_client`` identity ``test_user`` is a plain *member*,
``test_event_admin_user`` (``as_event_admin``) is an *admin*, and
``test_outsider_user`` (``as_outsider``) belongs to nothing.
"""

import datetime as dt
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.logic.sandbox.cleanup import purge_sandbox
from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.location import Location
from app.models.user import User
from app.models.venue_plan import VenueMarker, VenuePlan, VenuePlanImage, VenueShape
from app.models.venue_template import VenueTemplate, VenueTemplateImage
from app.schemas.venue_template import MAX_TEMPLATES_PER_USER
from tests.fixtures.locations import PLAN_HEIGHT, PLAN_WIDTH
from tests.fixtures.sandbox import SandboxSetup
from tests.fixtures.storage import drop_file, fetch_file, put_file, stored_bytes

API = "/api/v1"

_RECT: dict[str, Any] = {
    "id": "00000000-0000-4000-8000-000000000001",
    "kind": "rect",
    "style": "room",
    "points": [[0.1, 0.1], [0.4, 0.5]],
    "label": "Hall",
    "label_size": "md",
    "label_x": None,
    "label_y": None,
    "stroke_width": None,
    "prop": None,
    "rotation": None,
    "scale": None,
    "sort_order": 0,
}
_TREE: dict[str, Any] = {
    **_RECT,
    "id": "00000000-0000-4000-8000-000000000002",
    "kind": "prop",
    "style": "green",
    "points": [[0.7, 0.7]],
    "label": None,
    "prop": "tree",
    "rotation": 45.0,
    "scale": 1.5,
    "sort_order": 1,
}


async def _add_template(
    db: AsyncSession,
    *,
    user: User,
    name: str = "Parish hall",
    shapes: list[dict[str, Any]] | None = None,
    image: bytes | None = None,
) -> VenueTemplate:
    template = VenueTemplate(
        user_id=user.id,
        name=name,
        canvas_width=1200,
        canvas_height=1200,
        shapes=[_RECT, _TREE] if shapes is None else shapes,
    )
    if image is not None:
        template.image_etag = "a" * 64
        template.image_width = 640
        template.image_height = 480
    db.add(template)
    await db.flush()
    if image is not None:
        db.add(
            VenueTemplateImage(
                template_id=template.id,
                storage_key=await put_file(db, "venue-templates", image),
                content_type="image/webp",
                etag="a" * 64,
            )
        )
        await db.flush()
    await db.refresh(template)
    return template


async def _count(db: AsyncSession, model: Any, *where: Any) -> int:
    result = await db.execute(select(func.count()).select_from(model).where(*where))
    return int(result.scalar_one())


# ── Save as template ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSaveAsTemplate:
    async def test_copies_drawing_and_picture_without_pins_or_links(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event_admin_user: User,
        test_venue_plan: VenuePlan,
        test_venue_shapes: list[VenueShape],
        test_location_marker: VenueMarker,
    ) -> None:
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/save-as-template",
            json={"name": "  Gemeindehaus "},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "Gemeindehaus"
        assert body["canvas_width"] == test_venue_plan.canvas_width
        assert body["image_etag"] == test_venue_plan.image_etag
        assert (body["width"], body["height"]) == (PLAN_WIDTH, PLAN_HEIGHT)
        assert body["shape_count"] == len(test_venue_shapes) == len(body["shapes"])
        assert [s["kind"] for s in body["shapes"]] == [
            "rect",
            "polygon",
            "path",
            "label",
        ]
        # No location link and no markers anywhere in the template.
        assert all("location_id" not in s for s in body["shapes"])
        assert "markers" not in body

        template = await db_session.get(VenueTemplate, uuid.UUID(body["id"]))
        assert template is not None
        assert template.user_id == test_event_admin_user.id
        assert all("location_id" not in s for s in template.shapes)
        image = (
            await db_session.execute(
                select(VenueTemplateImage).where(
                    col(VenueTemplateImage.template_id) == template.id
                )
            )
        ).scalar_one()
        plan_image = (
            await db_session.execute(
                select(VenuePlanImage).where(
                    col(VenuePlanImage.plan_id) == test_venue_plan.id
                )
            )
        ).scalar_one()
        assert image.storage_key != plan_image.storage_key
        assert await stored_bytes(db_session, image.storage_key) == await stored_bytes(
            db_session, plan_image.storage_key
        )
        assert image.etag == plan_image.etag

    async def test_blank_plan_without_picture(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        blank_plan: VenuePlan,
    ) -> None:
        r = await async_client.post(
            f"{API}/venue-plans/{blank_plan.id}/save-as-template",
            json={"name": "Garden"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["image_etag"] is None
        assert body["shapes"] == []
        assert (body["width"], body["height"]) == (1600, 1000)

    async def test_dangling_etag_is_not_copied(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        blank_plan: VenuePlan,
    ) -> None:
        """A plan row that claims a picture with no bytes behind it."""
        blank_plan.image_etag = "d" * 64
        db_session.add(blank_plan)
        await db_session.flush()
        r = await async_client.post(
            f"{API}/venue-plans/{blank_plan.id}/save-as-template",
            json={"name": "Garden"},
        )
        assert r.status_code == 201
        assert r.json()["image_etag"] is None

    async def test_member_gets_403(
        self, async_client: AsyncClient, test_venue_plan: VenuePlan
    ) -> None:
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/save-as-template",
            json={"name": "X"},
        )
        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"

    async def test_outsider_gets_404(
        self,
        async_client: AsyncClient,
        as_outsider: None,
        test_venue_plan: VenuePlan,
    ) -> None:
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/save-as-template",
            json={"name": "X"},
        )
        assert r.status_code == 404
        assert r.json()["code"] == "event.not_found"

    async def test_unknown_plan_404_and_blank_name_422(
        self, async_client: AsyncClient, as_event_admin: None, blank_plan: VenuePlan
    ) -> None:
        r = await async_client.post(
            f"{API}/venue-plans/{uuid.uuid4()}/save-as-template", json={"name": "X"}
        )
        assert r.status_code == 404
        assert r.json()["code"] == "venue_plan.not_found"
        r = await async_client.post(
            f"{API}/venue-plans/{blank_plan.id}/save-as-template", json={"name": " "}
        )
        assert r.status_code == 422

    async def test_cap_of_twenty_per_user(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event_admin_user: User,
        test_user: User,
        blank_plan: VenuePlan,
    ) -> None:
        for i in range(MAX_TEMPLATES_PER_USER - 1):
            await _add_template(db_session, user=test_event_admin_user, name=f"T{i}")
        # Someone else's templates do not count towards the cap.
        await _add_template(db_session, user=test_user)

        url = f"{API}/venue-plans/{blank_plan.id}/save-as-template"
        r = await async_client.post(url, json={"name": "Twentieth"})
        assert r.status_code == 201, r.text

        r = await async_client.post(url, json={"name": "One too many"})
        assert r.status_code == 409
        assert r.json()["code"] == "venue_template.limit_reached"
        assert (
            await _count(
                db_session,
                VenueTemplate,
                col(VenueTemplate.user_id) == test_event_admin_user.id,
            )
            == MAX_TEMPLATES_PER_USER
        )

    async def test_sandbox_guest_may_save(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Templates are open to a demo guest; the purge takes them along."""
        test_user.is_sandbox = True
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
        plan = VenuePlan(event_id=event.id, name="Venue")
        db_session.add(plan)
        await db_session.flush()

        r = await async_client.post(
            f"{API}/venue-plans/{plan.id}/save-as-template", json={"name": "Mine"}
        )
        assert r.status_code == 201, r.text


# ── Reading, renaming, deleting ────────────────────────────────────────────


@pytest.mark.asyncio
class TestOwnTemplates:
    async def test_list_shows_only_mine_newest_first(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        test_event_admin_user: User,
    ) -> None:
        older = await _add_template(db_session, user=test_user, name="Older")
        older.created_at = older.created_at - dt.timedelta(minutes=5)
        db_session.add(older)
        newer = await _add_template(db_session, user=test_user, name="Newer", shapes=[])
        await _add_template(db_session, user=test_event_admin_user, name="Not mine")

        r = await async_client.get(f"{API}/venue-templates")
        assert r.status_code == 200, r.text
        body = r.json()
        assert [t["id"] for t in body] == [str(newer.id), str(older.id)]
        assert [t["shape_count"] for t in body] == [0, 2]
        assert "shapes" not in body[0]

    async def test_get_with_shapes(
        self, async_client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        template = await _add_template(db_session, user=test_user)
        r = await async_client.get(f"{API}/venue-templates/{template.id}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["shape_count"] == 2
        assert [s["id"] for s in body["shapes"]] == [_RECT["id"], _TREE["id"]]
        assert body["shapes"][1]["prop"] == "tree"
        assert (body["width"], body["height"]) == (1200, 1200)

    async def test_someone_elses_template_is_404_everywhere(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event_admin_user: User,
        test_event: Event,
    ) -> None:
        template = await _add_template(
            db_session, user=test_event_admin_user, image=b"img"
        )
        url = f"{API}/venue-templates/{template.id}"
        for r in (
            await async_client.get(url),
            await async_client.get(f"{url}/image"),
            await async_client.patch(url, json={"name": "Mine now"}),
            await async_client.delete(url),
        ):
            assert r.status_code == 404
            assert r.json()["code"] == "venue_template.not_found"
        await db_session.refresh(template)
        assert template.name == "Parish hall"

    async def test_superadmin_cannot_see_it_either(
        self,
        async_client: AsyncClient,
        as_admin: None,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        template = await _add_template(db_session, user=test_user)
        r = await async_client.get(f"{API}/venue-templates/{template.id}")
        assert r.status_code == 404

    async def test_unknown_id_404(self, async_client: AsyncClient) -> None:
        r = await async_client.get(f"{API}/venue-templates/{uuid.uuid4()}")
        assert r.status_code == 404
        assert r.json()["code"] == "venue_template.not_found"

    async def test_rename(
        self, async_client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        template = await _add_template(db_session, user=test_user)
        url = f"{API}/venue-templates/{template.id}"
        r = await async_client.patch(url, json={"name": "  Kirche "})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Kirche"
        assert len(r.json()["shapes"]) == 2

        r = await async_client.patch(url, json={})
        assert r.status_code == 200
        assert r.json()["name"] == "Kirche"

        r = await async_client.patch(url, json={"name": ""})
        assert r.status_code == 422

    async def test_delete_takes_the_image_along(
        self, async_client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        template = await _add_template(db_session, user=test_user, image=b"img")
        template_id = template.id
        r = await async_client.delete(f"{API}/venue-templates/{template_id}")
        assert r.status_code == 204

        db_session.expunge_all()
        assert await db_session.get(VenueTemplate, template_id) is None
        assert (
            await _count(
                db_session,
                VenueTemplateImage,
                col(VenueTemplateImage.template_id) == template_id,
            )
            == 0
        )

    @pytest.mark.usefixtures("streamed")
    async def test_image_served_to_owner_with_etag(
        self, async_client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        template = await _add_template(db_session, user=test_user, image=b"img")
        url = f"{API}/venue-templates/{template.id}/image"
        r = await async_client.get(url)
        assert r.status_code == 200
        assert r.content == b"img"
        assert r.headers["cache-control"].startswith("private")
        etag = r.headers["etag"]

        r = await async_client.get(url, headers={"If-None-Match": etag})
        assert r.status_code == 304

    async def test_template_without_image_404(
        self, async_client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        template = await _add_template(db_session, user=test_user)
        r = await async_client.get(f"{API}/venue-templates/{template.id}/image")
        assert r.status_code == 404
        assert r.json()["code"] == "venue_template.image_not_found"

    @pytest.mark.usefixtures("streamed")
    async def test_template_whose_file_is_gone_404(
        self, async_client: AsyncClient, db_session: AsyncSession, test_user: User
    ) -> None:
        template = await _add_template(db_session, user=test_user, image=b"img")
        image = (
            await db_session.execute(
                select(VenueTemplateImage).where(
                    col(VenueTemplateImage.template_id) == template.id
                )
            )
        ).scalar_one()
        await drop_file(db_session, image.storage_key)
        r = await async_client.get(f"{API}/venue-templates/{template.id}/image")
        assert r.status_code == 404
        assert r.json()["code"] == "venue_template.image_not_found"

    async def test_corrupt_snapshot_is_rejected_on_read(
        self, db_session: AsyncSession, test_user: User
    ) -> None:
        """The JSONB snapshot is validated with the shape rules on the way out."""
        from pydantic import ValidationError

        from app.crud.venue_template import venue_template as crud

        template = await _add_template(
            db_session, user=test_user, shapes=[{**_RECT, "points": [[0.1, 0.1]]}]
        )
        with pytest.raises(ValidationError):
            crud.read(template)


# ── Starting a plan from a template ────────────────────────────────────────


@pytest.mark.asyncio
class TestCreatePlanFromTemplate:
    async def test_copies_canvas_picture_and_drawing(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
        test_event_admin_user: User,
        test_venue_plan: VenuePlan,
    ) -> None:
        template = await _add_template(
            db_session, user=test_event_admin_user, image=b"webp-bytes"
        )
        r = await async_client.post(
            f"{API}/events/{test_event.id}/venue-plans",
            json={
                "name": "Upstairs",
                "canvas": "portrait",
                "template_id": str(template.id),
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "Upstairs"
        assert body["sort_order"] == test_venue_plan.sort_order + 1
        # The template's canvas wins over ``canvas``.
        assert (body["canvas_width"], body["canvas_height"]) == (1200, 1200)
        assert body["image_etag"] == "a" * 64
        assert (body["width"], body["height"]) == (640, 480)
        assert body["markers"] == []
        assert body["shapes_revision"] == 1
        assert [s["kind"] for s in body["shapes"]] == ["rect", "prop"]
        assert all(s["location_id"] is None for s in body["shapes"])
        # Fresh shape rows, not the template's ids.
        assert {s["id"] for s in body["shapes"]}.isdisjoint({_RECT["id"], _TREE["id"]})
        assert body["shapes"][1]["rotation"] == 45.0
        assert body["shapes"][1]["scale"] == 1.5

        plan_id = uuid.UUID(body["id"])
        image = (
            await db_session.execute(
                select(VenuePlanImage).where(col(VenuePlanImage.plan_id) == plan_id)
            )
        ).scalar_one()
        assert await stored_bytes(db_session, image.storage_key) == b"webp-bytes"

        r = await fetch_file(async_client, f"{API}/venue-plans/{plan_id}/image")
        assert r.status_code == 200
        assert r.content == b"webp-bytes"

    async def test_empty_template_gives_revision_zero(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
        test_event_admin_user: User,
    ) -> None:
        template = await _add_template(
            db_session, user=test_event_admin_user, shapes=[]
        )
        r = await async_client.post(
            f"{API}/events/{test_event.id}/venue-plans",
            json={"name": "Empty", "template_id": str(template.id)},
        )
        assert r.status_code == 201, r.text
        assert r.json()["shapes_revision"] == 0
        assert r.json()["image_etag"] is None

    async def test_someone_elses_template_is_404(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        template = await _add_template(db_session, user=test_user)
        r = await async_client.post(
            f"{API}/events/{test_event.id}/venue-plans",
            json={"name": "X", "template_id": str(template.id)},
        )
        assert r.status_code == 404
        assert r.json()["code"] == "venue_template.not_found"
        assert (
            await _count(
                db_session, VenuePlan, col(VenuePlan.event_id) == test_event.id
            )
            == 0
        )

    async def test_member_gets_403_before_the_template_is_looked_at(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_event: Event,
        test_user: User,
    ) -> None:
        template = await _add_template(db_session, user=test_user)
        r = await async_client.post(
            f"{API}/events/{test_event.id}/venue-plans",
            json={"name": "X", "template_id": str(template.id)},
        )
        assert r.status_code == 403

    async def test_copies_not_links_round_trip(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_event: Event,
        test_venue_plan: VenuePlan,
        test_venue_shapes: list[VenueShape],
        test_location: Location,
    ) -> None:
        """Save, start a new plan from it, then change each side on its own."""
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/save-as-template",
            json={"name": "Snapshot"},
        )
        assert r.status_code == 201
        template_id = r.json()["id"]

        # Changing the source plan does not reach the template.
        r = await async_client.post(
            f"{API}/venue-plans/{test_venue_plan.id}/shapes/batch",
            json={"ops": [{"op": "delete", "id": str(test_venue_shapes[0].id)}]},
        )
        assert r.status_code == 200, r.text
        r = await async_client.get(f"{API}/venue-templates/{template_id}")
        assert r.json()["shape_count"] == len(test_venue_shapes)

        r = await async_client.post(
            f"{API}/events/{test_event.id}/venue-plans",
            json={"name": "Copy", "template_id": template_id},
        )
        assert r.status_code == 201
        new_plan = r.json()
        assert len(new_plan["shapes"]) == len(test_venue_shapes)
        # The rect was linked to a place on the source plan; the copy is not.
        assert new_plan["shapes"][0]["kind"] == "rect"
        assert new_plan["shapes"][0]["location_id"] is None

        # Deleting the template leaves the plan made from it alone.
        r = await async_client.delete(f"{API}/venue-templates/{template_id}")
        assert r.status_code == 204
        r = await async_client.get(f"{API}/venue-plans/{new_plan['id']}/shapes")
        assert r.status_code == 200
        assert len(r.json()["shapes"]) == len(test_venue_shapes)


# ── Going away with the account ────────────────────────────────────────────


@pytest.mark.asyncio
class TestTemplatesGoWithTheAccount:
    async def test_user_delete_cascades(
        self, db_session: AsyncSession, test_outsider_user: User
    ) -> None:
        template = await _add_template(db_session, user=test_outsider_user, image=b"x")
        template_id = template.id
        await db_session.delete(test_outsider_user)
        await db_session.flush()
        db_session.expunge_all()
        assert await db_session.get(VenueTemplate, template_id) is None
        assert (
            await _count(
                db_session,
                VenueTemplateImage,
                col(VenueTemplateImage.template_id) == template_id,
            )
            == 0
        )

    async def test_delete_me_endpoint_removes_them(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        test_outsider_user: User,
        as_outsider: None,
    ) -> None:
        template = await _add_template(db_session, user=test_outsider_user)
        template_id = template.id
        r = await async_client.delete(f"{API}/users/me")
        assert r.status_code == 204
        db_session.expunge_all()
        assert await db_session.get(VenueTemplate, template_id) is None

    async def test_sandbox_purge_removes_the_guests_templates(
        self,
        db_session: AsyncSession,
        test_sandbox: SandboxSetup,
        test_user: User,
    ) -> None:
        await _add_template(db_session, user=test_sandbox.guest, image=b"img")
        await _add_template(db_session, user=test_sandbox.guest, name="Second")
        keep = await _add_template(db_session, user=test_user, image=b"keep")
        guest_id = test_sandbox.guest.id
        assert (
            await _count(
                db_session, VenueTemplate, col(VenueTemplate.user_id) == guest_id
            )
            == 2
        )

        await purge_sandbox(db_session, event_id=test_sandbox.event.id)

        assert (
            await _count(
                db_session, VenueTemplate, col(VenueTemplate.user_id) == guest_id
            )
            == 0
        )
        # Only the real account's template (and its picture) is left.
        assert await _count(db_session, VenueTemplate) == 1
        assert await _count(db_session, VenueTemplateImage) == 1
        assert (
            await _count(db_session, VenueTemplate, col(VenueTemplate.id) == keep.id)
            == 1
        )
