"""HTTP tests for drawn venue-map shapes (#185 phase 2).

Covers ``GET /venue-plans/{id}/shapes`` and ``POST /venue-plans/{id}/shapes/batch``
(``app/api/routes/venue_map.py`` and ``app/logic/venue_shape_batch.py``).

Cast as in ``test_venue_map.py``: the default identity ``test_user`` is a plain
*member* of ``test_event``, ``as_event_admin`` an *admin*, ``as_outsider``
belongs to nothing (and ``test_event`` is public, so they can see the event but
not its map).
"""

import datetime as dt
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.event import Event
from app.models.event_membership import EventMembership
from app.models.location import Location
from app.models.user import User
from app.models.venue_plan import VenuePlan, VenueShape
from tests.fixtures.locations import make_png

API = "/api/v1"

RECT: dict[str, Any] = {
    "kind": "rect",
    "style": "room",
    "points": [[0.6, 0.7], [0.2, 0.3]],
    "label": "Hall",
}


def _create(shape: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    return {"op": "create", "shape": {**(shape or RECT), **extra}}


async def _batch(
    client: AsyncClient,
    plan_id: uuid.UUID,
    ops: list[dict[str, Any]],
    expected_revision: int | None = None,
) -> Any:
    body: dict[str, Any] = {"ops": ops}
    if expected_revision is not None:
        body["expected_revision"] = expected_revision
    return await client.post(f"{API}/venue-plans/{plan_id}/shapes/batch", json=body)


async def _shape_ids(db: AsyncSession, plan_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(col(VenueShape.id)).where(col(VenueShape.plan_id) == plan_id)
    )
    return list(result.scalars().all())


# ── Reading ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGetShapes:
    async def test_member_reads_shapes_in_order(
        self,
        async_client: AsyncClient,
        test_venue_plan: VenuePlan,
        test_venue_shapes: list[VenueShape],
    ) -> None:
        r = await async_client.get(f"{API}/venue-plans/{test_venue_plan.id}/shapes")
        assert r.status_code == 200, r.text
        assert r.headers["cache-control"] == "private, no-cache"
        body = r.json()
        assert body["plan_id"] == str(test_venue_plan.id)
        assert body["revision"] == 1
        assert [s["id"] for s in body["shapes"]] == [
            str(s.id) for s in test_venue_shapes
        ]
        assert [s["kind"] for s in body["shapes"]] == [
            "rect",
            "polygon",
            "path",
            "label",
        ]

    async def test_outsider_gets_404(
        self,
        async_client: AsyncClient,
        as_outsider: None,
        test_venue_plan: VenuePlan,
    ) -> None:
        r = await async_client.get(f"{API}/venue-plans/{test_venue_plan.id}/shapes")
        assert r.status_code == 404

    async def test_unknown_plan_404(self, async_client: AsyncClient) -> None:
        r = await async_client.get(f"{API}/venue-plans/{uuid.uuid4()}/shapes")
        assert r.status_code == 404
        assert r.json()["code"] == "venue_plan.not_found"


# ── Gates ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestBatchGates:
    async def test_member_gets_403(
        self, async_client: AsyncClient, test_venue_plan: VenuePlan
    ) -> None:
        r = await _batch(async_client, test_venue_plan.id, [_create()])
        assert r.status_code == 403
        assert r.json()["code"] == "event.forbidden"

    async def test_outsider_gets_404(
        self,
        async_client: AsyncClient,
        as_outsider: None,
        test_venue_plan: VenuePlan,
    ) -> None:
        r = await _batch(async_client, test_venue_plan.id, [_create()])
        assert r.status_code == 404

    async def test_sandbox_admin_may_draw_but_not_upload(
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
        plan = VenuePlan(event_id=event.id, name="Venue")
        db_session.add(plan)
        await db_session.flush()

        r = await _batch(async_client, plan.id, [_create()])
        assert r.status_code == 200, r.text

        r = await async_client.put(
            f"{API}/venue-plans/{plan.id}/image",
            files={"file": ("p.png", make_png(40, 30), "image/png")},
        )
        assert r.status_code == 403
        assert r.json()["code"] == "sandbox.upload_disabled"


# ── Ops ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestBatchOps:
    async def test_create_each_kind(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        blank_plan: VenuePlan,
        test_location: Location,
    ) -> None:
        r = await _batch(
            async_client,
            blank_plan.id,
            [
                _create(location_id=str(test_location.id)),
                _create(
                    {
                        "kind": "polygon",
                        "style": "green",
                        "points": [[0, 0], [0.5, 0], [0.25, 0.4]],
                    }
                ),
                _create(
                    {
                        "kind": "path",
                        "style": "water",
                        "points": [[0, 0.9], [1, 0.9]],
                    }
                ),
                _create(
                    {
                        "kind": "label",
                        "style": "path",
                        "points": [[0.5, 0.95]],
                        "label": "  Main road ",
                        "label_size": "lg",
                    }
                ),
            ],
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["revision"] == 1
        rect, polygon, path, label = body["shapes"]
        assert rect["points"] == [[0.2, 0.3], [0.6, 0.7]]
        assert rect["location_id"] == str(test_location.id)
        assert rect["label_size"] == "md"
        assert rect["stroke_width"] is None
        assert polygon["style"] == "green"
        assert path["stroke_width"] == 0.02
        assert label["label"] == "Main road"
        assert label["label_size"] == "lg"
        assert [s["sort_order"] for s in body["shapes"]] == [0, 1, 2, 3]

    async def test_client_id_honoured_and_sort_order_appended(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
        test_venue_shapes: list[VenueShape],
    ) -> None:
        shape_id = uuid.uuid4()
        r = await _batch(async_client, test_venue_plan.id, [_create(id=str(shape_id))])
        assert r.status_code == 200, r.text
        created = r.json()["shapes"][-1]
        assert created["id"] == str(shape_id)
        assert created["sort_order"] == 4
        assert r.json()["revision"] == 2

        r = await _batch(async_client, test_venue_plan.id, [_create(id=str(shape_id))])
        assert r.status_code == 409
        assert r.json()["code"] == "venue_shape.id_taken"

    async def test_id_of_a_shape_on_another_plan_is_taken(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        blank_plan: VenuePlan,
        test_venue_shapes: list[VenueShape],
    ) -> None:
        r = await _batch(
            async_client, blank_plan.id, [_create(id=str(test_venue_shapes[0].id))]
        )
        assert r.status_code == 409
        assert r.json()["code"] == "venue_shape.id_taken"

    async def test_explicit_sort_order_kept(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        blank_plan: VenuePlan,
    ) -> None:
        r = await _batch(
            async_client,
            blank_plan.id,
            [_create(sort_order=5), _create(sort_order=-1)],
        )
        assert r.status_code == 200, r.text
        assert [s["sort_order"] for s in r.json()["shapes"]] == [-1, 5]

    async def test_update_merges_and_revalidates(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
        test_venue_shapes: list[VenueShape],
    ) -> None:
        rect = test_venue_shapes[0]
        r = await _batch(
            async_client,
            test_venue_plan.id,
            [
                {
                    "op": "update",
                    "id": str(rect.id),
                    "patch": {
                        "style": "stage",
                        "label": "Bühne",
                        "points": [[0.9, 0.9], [0.5, 0.5]],
                        "label_x": 0.7,
                        "label_y": 0.85,
                        # Cannot be cleared: ignored.
                        "label_size": None,
                        "sort_order": None,
                    },
                }
            ],
        )
        assert r.status_code == 200, r.text
        updated = r.json()["shapes"][0]
        assert updated["style"] == "stage"
        assert updated["label"] == "Bühne"
        assert updated["points"] == [[0.5, 0.5], [0.9, 0.9]]
        assert (updated["label_x"], updated["label_y"]) == (0.7, 0.85)
        assert updated["label_size"] == "md"
        assert updated["sort_order"] == 0

        # Clearing the label and unlinking work through explicit nulls.
        r = await _batch(
            async_client,
            test_venue_plan.id,
            [
                {
                    "op": "update",
                    "id": str(rect.id),
                    "patch": {"label": "", "location_id": None},
                }
            ],
        )
        assert r.status_code == 200, r.text
        assert r.json()["shapes"][0]["label"] is None
        assert r.json()["shapes"][0]["location_id"] is None

    @pytest.mark.parametrize(
        ("index", "patch", "code"),
        [
            (2, "link", "venue_shape.link_not_allowed"),
            (3, {"label": ""}, "venue_shape.label_required"),
            (0, {"points": [[0.1, 0.1], [0.1001, 0.5]]}, "venue_shape.too_small"),
            (0, {"points": [[0.1, 0.1]]}, "venue_shape.points_count"),
            (2, {"stroke_width": 0.9}, "venue_shape.stroke_width"),
            (0, {"label_x": 0.5}, "venue_shape.label_anchor"),
        ],
    )
    async def test_update_merged_validation_errors(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
        test_venue_shapes: list[VenueShape],
        test_location: Location,
        index: int,
        patch: Any,
        code: str,
    ) -> None:
        if patch == "link":
            patch = {"location_id": str(test_location.id)}
        r = await _batch(
            async_client,
            test_venue_plan.id,
            [{"op": "update", "id": str(test_venue_shapes[index].id), "patch": patch}],
        )
        assert r.status_code == 422, r.text
        assert r.json()["code"] == code
        assert r.json()["detail"].startswith("ops[0]: ")

    async def test_foreign_location_422(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_venue_plan: VenuePlan,
        test_venue_shapes: list[VenueShape],
        test_private_event: Event,
    ) -> None:
        foreign = Location(event_id=test_private_event.id, name="Elsewhere")
        db_session.add(foreign)
        await db_session.flush()

        r = await _batch(
            async_client, test_venue_plan.id, [_create(location_id=str(foreign.id))]
        )
        assert r.status_code == 422
        assert r.json()["code"] == "location.wrong_event"

        r = await _batch(
            async_client,
            test_venue_plan.id,
            [
                {
                    "op": "update",
                    "id": str(test_venue_shapes[0].id),
                    "patch": {"location_id": str(foreign.id)},
                }
            ],
        )
        assert r.status_code == 422
        assert r.json()["code"] == "location.wrong_event"

    async def test_delete_and_unknown_ids(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_venue_plan: VenuePlan,
        blank_plan: VenuePlan,
        test_venue_shapes: list[VenueShape],
    ) -> None:
        r = await _batch(
            async_client,
            test_venue_plan.id,
            [{"op": "delete", "id": str(test_venue_shapes[1].id)}],
        )
        assert r.status_code == 200, r.text
        assert len(r.json()["shapes"]) == 3
        assert test_venue_shapes[1].id not in await _shape_ids(
            db_session, test_venue_plan.id
        )

        for op in (
            {"op": "delete", "id": str(uuid.uuid4())},
            {"op": "update", "id": str(uuid.uuid4()), "patch": {"style": "wall"}},
            # A shape of another plan is not found through this one.
            {"op": "delete", "id": str(test_venue_shapes[0].id)},
        ):
            r = await _batch(async_client, blank_plan.id, [op])
            assert r.status_code == 404, op
            assert r.json()["code"] == "venue_shape.not_found"

    async def test_delete_then_recreate_same_id_in_one_batch(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
        test_venue_shapes: list[VenueShape],
    ) -> None:
        """What a redo of "undo a delete" sends."""
        shape = test_venue_shapes[0]
        r = await _batch(
            async_client,
            test_venue_plan.id,
            [
                {"op": "delete", "id": str(shape.id)},
                _create(id=str(shape.id), style="wall", sort_order=0),
            ],
        )
        assert r.status_code == 200, r.text
        recreated = next(s for s in r.json()["shapes"] if s["id"] == str(shape.id))
        assert recreated["style"] == "wall"

    async def test_create_then_delete_same_id_in_one_batch(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        blank_plan: VenuePlan,
    ) -> None:
        """A shape drawn and removed before the save went out: a no-op, then a
        re-create of the same id still works."""
        new_id = str(uuid.uuid4())
        r = await _batch(
            async_client,
            blank_plan.id,
            [
                _create(id=new_id),
                {"op": "delete", "id": new_id},
                _create(id=new_id, style="stage"),
                {"op": "delete", "id": new_id},
            ],
        )
        assert r.status_code == 200, r.text
        assert r.json()["shapes"] == []
        assert r.json()["revision"] == 1
        assert await _shape_ids(db_session, blank_plan.id) == []

        r = await _batch(
            async_client,
            blank_plan.id,
            [_create(id=new_id), {"op": "delete", "id": new_id}, _create(id=new_id)],
        )
        assert r.status_code == 200, r.text
        assert [s["id"] for s in r.json()["shapes"]] == [new_id]

    async def test_failing_op_rolls_back_the_whole_batch(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        db_session: AsyncSession,
        test_venue_plan: VenuePlan,
        test_venue_shapes: list[VenueShape],
    ) -> None:
        before = sorted(await _shape_ids(db_session, test_venue_plan.id))
        r = await _batch(
            async_client,
            test_venue_plan.id,
            [
                _create(),
                {"op": "delete", "id": str(test_venue_shapes[0].id)},
                {"op": "delete", "id": str(uuid.uuid4())},
            ],
        )
        assert r.status_code == 404
        assert r.json()["detail"].startswith("ops[2]: ")
        assert sorted(await _shape_ids(db_session, test_venue_plan.id)) == before
        await db_session.refresh(test_venue_plan)
        assert test_venue_plan.shapes_revision == 1

    async def test_expected_revision(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        test_venue_plan: VenuePlan,
        test_venue_shapes: list[VenueShape],
    ) -> None:
        r = await _batch(async_client, test_venue_plan.id, [_create()], 0)
        assert r.status_code == 409
        assert r.json()["code"] == "venue_shape.revision_conflict"

        r = await _batch(async_client, test_venue_plan.id, [_create()], 1)
        assert r.status_code == 200
        assert r.json()["revision"] == 2
        r = await _batch(async_client, test_venue_plan.id, [_create()], 2)
        assert r.json()["revision"] == 3


@pytest.mark.asyncio
class TestBatchLimits:
    async def test_too_many_points(
        self, async_client: AsyncClient, as_event_admin: None, blank_plan: VenuePlan
    ) -> None:
        points = [[i / 600, 0.5 + (i % 2) / 10] for i in range(501)]
        r = await _batch(
            async_client,
            blank_plan.id,
            [_create({"kind": "polygon", "style": "area", "points": points})],
        )
        assert r.status_code == 422

    async def test_too_many_ops(
        self, async_client: AsyncClient, as_event_admin: None, blank_plan: VenuePlan
    ) -> None:
        r = await _batch(async_client, blank_plan.id, [_create()] * 201)
        assert r.status_code == 422

    async def test_empty_batch(
        self, async_client: AsyncClient, as_event_admin: None, blank_plan: VenuePlan
    ) -> None:
        r = await _batch(async_client, blank_plan.id, [])
        assert r.status_code == 422

    async def test_too_many_shapes(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        blank_plan: VenuePlan,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("app.logic.venue_shapes.MAX_SHAPES_PER_PLAN", 3)
        r = await _batch(async_client, blank_plan.id, [_create()] * 3)
        assert r.status_code == 200
        r = await _batch(async_client, blank_plan.id, [_create()])
        assert r.status_code == 422
        assert r.json()["code"] == "venue_shape.too_many"

    async def test_too_many_points_in_all(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        blank_plan: VenuePlan,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Each shape within its own limit, but the plan as a whole is not."""
        monkeypatch.setattr("app.logic.venue_shapes.MAX_POINTS_PER_PLAN", 5)
        r = await _batch(async_client, blank_plan.id, [_create(), _create()])
        assert r.status_code == 200  # 2 + 2 points
        r = await _batch(async_client, blank_plan.id, [_create()])
        assert r.status_code == 422
        assert r.json()["code"] == "venue_shape.too_many_points"
        assert len(await _shape_ids(db_session, blank_plan.id)) == 2

    @pytest.mark.parametrize("sort_order", [2**31, -(2**40), 1_000_001])
    async def test_sort_order_out_of_range(
        self,
        async_client: AsyncClient,
        as_event_admin: None,
        blank_plan: VenuePlan,
        sort_order: int,
    ) -> None:
        r = await _batch(async_client, blank_plan.id, [_create(sort_order=sort_order)])
        assert r.status_code == 422
        r = await _batch(async_client, blank_plan.id, [_create()])
        shape_id = r.json()["shapes"][0]["id"]
        r = await _batch(
            async_client,
            blank_plan.id,
            [{"op": "update", "id": shape_id, "patch": {"sort_order": sort_order}}],
        )
        assert r.status_code == 422

    async def test_label_too_long(
        self, async_client: AsyncClient, as_event_admin: None, blank_plan: VenuePlan
    ) -> None:
        r = await _batch(async_client, blank_plan.id, [_create(label="x" * 121)])
        assert r.status_code == 422
        r = await _batch(async_client, blank_plan.id, [_create(label="x" * 120)])
        assert r.status_code == 200

    async def test_coordinate_out_of_range(
        self, async_client: AsyncClient, as_event_admin: None, blank_plan: VenuePlan
    ) -> None:
        r = await _batch(
            async_client, blank_plan.id, [_create(points=[[0, 0], [1.01, 0.5]])]
        )
        assert r.status_code == 422

    async def test_schema_error_code_reaches_the_problem(
        self, async_client: AsyncClient, as_event_admin: None, blank_plan: VenuePlan
    ) -> None:
        """Rules the request schema enforces come back as the error's ``type``,
        like ``venue_marker.location_required``."""
        r = await _batch(
            async_client,
            blank_plan.id,
            [_create({"kind": "label", "style": "room", "points": [[0.5, 0.5]]})],
        )
        assert r.status_code == 422
        assert [e["type"] for e in r.json()["errors"]] == ["venue_shape.label_required"]
