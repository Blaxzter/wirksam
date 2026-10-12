"""Persistence tests for ``app.crud.location`` and ``app.crud.venue_map``.

The routes built on these are covered in ``tests/api/routes``; what is pinned
here is the behaviour of the rows themselves: ordering, the case-insensitive
name lookup, the image upsert mirroring onto the plan, the clone copy (bytes
copied inside the database, ids remapped) and the foreign-key actions the
denormalised ``location`` text depends on.
"""

import uuid
from datetime import date, time

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.location import location as crud_location
from app.crud.venue_map import venue_map as crud_venue_map
from app.logic.images import NormalizedImage
from app.models.event import Event
from app.models.location import Location
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User
from app.models.venue_plan import VenueMarker, VenuePlan, VenuePlanImage
from app.schemas.location import LocationCreate, LocationUpdate
from app.schemas.venue_map import VenueMarkerCreate


async def _new_event(session: AsyncSession, owner: User, name: str = "Copy") -> Event:
    event = Event(
        name=name,
        start_date=date(2027, 6, 10),
        end_date=date(2027, 6, 14),
        created_by_id=owner.id,
    )
    session.add(event)
    await session.flush()
    return event


@pytest.mark.asyncio
class TestCRUDLocation:
    async def test_create_list_and_order_ignore_case(
        self, db_session: AsyncSession, test_event: Event
    ) -> None:
        for name in ("garden", "Bar", "Atrium"):
            await crud_location.create(
                db_session, event_id=test_event.id, data=LocationCreate(name=name)
            )

        listed = await crud_location.list_for_event(db_session, event_id=test_event.id)

        assert [loc.name for loc in listed] == ["Atrium", "Bar", "garden"]

    async def test_get_by_name_ci(
        self, db_session: AsyncSession, test_location: Location
    ) -> None:
        found = await crud_location.get_by_name_ci(
            db_session, event_id=test_location.event_id, name="  fOYER "
        )
        assert found is not None and found.id == test_location.id

        assert (
            await crud_location.get_by_name_ci(
                db_session,
                event_id=test_location.event_id,
                name="foyer",
                exclude_id=test_location.id,
            )
            is None
        )
        assert (
            await crud_location.get_by_name_ci(
                db_session, event_id=uuid.uuid4(), name="Foyer"
            )
            is None
        )

    async def test_update_applies_only_sent_fields(
        self, db_session: AsyncSession, test_location: Location
    ) -> None:
        before = test_location.updated_at
        updated = await crud_location.update(
            db_session,
            location=test_location,
            data=LocationUpdate.model_validate({"address": "", "contact": "Ben"}),
        )

        assert updated.name == "Foyer"
        assert updated.address is None
        assert updated.contact == "Ben"
        assert updated.description is not None
        assert updated.updated_at >= before
        assert await crud_location.get(db_session, location_id=updated.id) is updated

    async def test_delete_nulls_references_keeps_text_and_drops_markers(
        self,
        db_session: AsyncSession,
        test_location: Location,
        test_location_marker: VenueMarker,
        test_task: Task,
        test_shift: Shift,
    ) -> None:
        batch = ShiftBatch(
            task_id=test_task.id,
            start_date=date(2026, 6, 11),
            end_date=date(2026, 6, 11),
            location="Foyer",
            location_id=test_location.id,
        )
        db_session.add(batch)
        for row in (test_task, test_shift):
            row.location = "Foyer"
            row.location_id = test_location.id
            db_session.add(row)
        await db_session.flush()
        marker_id = test_location_marker.id

        await crud_location.delete(db_session, location=test_location)

        for model, row_id in (
            (Task, test_task.id),
            (ShiftBatch, batch.id),
            (Shift, test_shift.id),
        ):
            row = await db_session.get(model, row_id, populate_existing=True)
            assert row is not None
            assert row.location_id is None
            assert row.location == "Foyer"
        assert (
            await db_session.scalar(
                select(col(VenueMarker.id)).where(col(VenueMarker.id) == marker_id)
            )
            is None
        )

    async def test_pins_in_plan_order(
        self,
        db_session: AsyncSession,
        test_location: Location,
        test_location_marker: VenueMarker,
        test_venue_plan: VenuePlan,
    ) -> None:
        upstairs = await crud_venue_map.create_plan(
            db_session, event_id=test_location.event_id, name="Upstairs"
        )
        # Move the new plan in front of the fixture one.
        await crud_venue_map.reorder(
            db_session,
            event_id=test_location.event_id,
            plan_ids=[upstairs.id, test_venue_plan.id],
        )
        db_session.add(
            VenueMarker(
                plan_id=upstairs.id,
                location_id=test_location.id,
                kind="location",
                x=0.5,
                y=0.5,
            )
        )
        await db_session.flush()

        pins = await crud_location.pins_for_location(
            db_session, location_id=test_location.id
        )

        assert [p.plan_id for p in pins] == [upstairs.id, test_venue_plan.id]
        fixture_pin = pins[1]
        assert fixture_pin.marker_id == test_location_marker.id
        assert fixture_pin.plan_name == "Ground floor"
        assert (fixture_pin.image_width, fixture_pin.image_height) == (800, 600)
        assert fixture_pin.image_etag == test_venue_plan.image_etag
        assert (fixture_pin.x, fixture_pin.y) == (0.25, 0.75)
        assert pins[0].image_etag is None


@pytest.mark.asyncio
class TestCRUDVenuePlans:
    async def test_create_appends_and_lists_with_markers(
        self,
        db_session: AsyncSession,
        test_venue_plan: VenuePlan,
        test_location_marker: VenueMarker,
    ) -> None:
        second = await crud_venue_map.create_plan(
            db_session, event_id=test_venue_plan.event_id, name="Garden"
        )
        assert second.sort_order == test_venue_plan.sort_order + 1
        generic = await crud_venue_map.create_marker(
            db_session,
            plan_id=second.id,
            data=VenueMarkerCreate(kind="first_aid", label="Tent", x=0, y=1),
        )

        plans = await crud_venue_map.list_plans_with_markers(
            db_session, event_id=test_venue_plan.event_id
        )

        assert [p.id for p in plans] == [test_venue_plan.id, second.id]
        assert [m.id for m in plans[0].markers] == [test_location_marker.id]
        assert [m.id for m in plans[1].markers] == [generic.id]
        assert plans[1].markers[0].kind == "first_aid"
        assert (
            await crud_venue_map.get_marker(db_session, marker_id=generic.id) is generic
        )

    async def test_first_plan_starts_at_zero(
        self, db_session: AsyncSession, test_event: Event
    ) -> None:
        plan = await crud_venue_map.create_plan(
            db_session, event_id=test_event.id, name="Only"
        )
        assert plan.sort_order == 0
        assert await crud_venue_map.get_plan(db_session, plan_id=plan.id) is plan

    async def test_empty_event_lists_nothing(
        self, db_session: AsyncSession, test_event: Event
    ) -> None:
        assert (
            await crud_venue_map.list_plans_with_markers(
                db_session, event_id=test_event.id
            )
            == []
        )

    async def test_rename_and_delete(
        self, db_session: AsyncSession, test_venue_plan: VenuePlan
    ) -> None:
        renamed = await crud_venue_map.rename_plan(
            db_session, plan=test_venue_plan, name="Hall"
        )
        assert renamed.name == "Hall"

        plan_id = test_venue_plan.id
        await crud_venue_map.delete_plan(db_session, plan=test_venue_plan)

        assert await crud_venue_map.get_image(db_session, plan_id=plan_id) is None

    async def test_reorder_rejects_anything_but_the_exact_set(
        self, db_session: AsyncSession, test_venue_plan: VenuePlan
    ) -> None:
        other = await crud_venue_map.create_plan(
            db_session, event_id=test_venue_plan.event_id, name="Two"
        )
        bad_orders = [
            [test_venue_plan.id],
            [test_venue_plan.id, other.id, other.id],
            [test_venue_plan.id, uuid.uuid4()],
        ]
        for plan_ids in bad_orders:
            with pytest.raises(ValueError):
                await crud_venue_map.reorder(
                    db_session, event_id=test_venue_plan.event_id, plan_ids=plan_ids
                )

        result = await crud_venue_map.reorder(
            db_session,
            event_id=test_venue_plan.event_id,
            plan_ids=[other.id, test_venue_plan.id],
        )
        assert [p.id for p in result] == [other.id, test_venue_plan.id]
        assert [p.sort_order for p in result] == [0, 1]

    async def test_count_plans_with_image_by_event(
        self,
        db_session: AsyncSession,
        test_venue_plan: VenuePlan,
        test_private_event: Event,
    ) -> None:
        # A plan without an image does not count.
        await crud_venue_map.create_plan(
            db_session, event_id=test_venue_plan.event_id, name="Draft"
        )

        counts = await crud_venue_map.count_plans_with_image_by_event(
            db_session, event_ids=[test_venue_plan.event_id, test_private_event.id]
        )

        assert counts == {test_venue_plan.event_id: 1}
        assert (
            await crud_venue_map.count_plans_with_image_by_event(
                db_session, event_ids=[]
            )
            == {}
        )

    async def test_upsert_image_inserts_then_replaces(
        self, db_session: AsyncSession, test_event: Event
    ) -> None:
        plan = await crud_venue_map.create_plan(
            db_session, event_id=test_event.id, name="New"
        )
        first = NormalizedImage(b"one", "image/webp", "a" * 64, 100, 50)
        second = NormalizedImage(b"two", "image/webp", "b" * 64, 200, 80)

        row = await crud_venue_map.upsert_image(db_session, plan=plan, image=first)
        assert (plan.image_etag, plan.image_width, plan.image_height) == (
            "a" * 64,
            100,
            50,
        )
        again = await crud_venue_map.upsert_image(db_session, plan=plan, image=second)

        assert again.id == row.id
        stored = await crud_venue_map.get_image(db_session, plan_id=plan.id)
        assert stored is not None and stored.data == b"two"
        assert (plan.image_etag, plan.image_width, plan.image_height) == (
            "b" * 64,
            200,
            80,
        )

    async def test_marker_lookup_by_location(
        self,
        db_session: AsyncSession,
        test_location_marker: VenueMarker,
    ) -> None:
        assert test_location_marker.location_id is not None
        found = await crud_venue_map.get_marker_for_location(
            db_session,
            plan_id=test_location_marker.plan_id,
            location_id=test_location_marker.location_id,
        )
        assert found is not None and found.id == test_location_marker.id
        assert (
            await crud_venue_map.get_marker_for_location(
                db_session,
                plan_id=test_location_marker.plan_id,
                location_id=test_location_marker.location_id,
                exclude_id=test_location_marker.id,
            )
            is None
        )


@pytest.mark.asyncio
class TestCopyForClone:
    async def test_copies_locations_plans_bytes_and_markers(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        test_location: Location,
        test_venue_plan: VenuePlan,
        test_location_marker: VenueMarker,
    ) -> None:
        empty_plan = await crud_venue_map.create_plan(
            db_session, event_id=test_venue_plan.event_id, name="No image yet"
        )
        generic = await crud_venue_map.create_marker(
            db_session,
            plan_id=test_venue_plan.id,
            data=VenueMarkerCreate(kind="entrance", label="Gate", x=0.1, y=0.2),
        )
        target = await _new_event(db_session, test_admin_user)

        location_map, plans_created = await crud_venue_map.copy_for_clone(
            db_session,
            source_event_id=test_venue_plan.event_id,
            new_event_id=target.id,
        )

        assert plans_created == 2
        assert set(location_map) == {test_location.id}
        new_loc = await db_session.get(Location, location_map[test_location.id])
        assert new_loc is not None
        assert new_loc.event_id == target.id
        assert (new_loc.name, new_loc.description, new_loc.map_url) == (
            test_location.name,
            test_location.description,
            test_location.map_url,
        )

        new_plans = await crud_venue_map.list_plans(db_session, event_id=target.id)
        assert [p.name for p in new_plans] == ["Ground floor", "No image yet"]
        copied, copied_empty = new_plans
        assert copied.id != test_venue_plan.id
        assert (copied.image_etag, copied.image_width, copied.image_height) == (
            test_venue_plan.image_etag,
            800,
            600,
        )
        assert copied_empty.image_etag is None
        assert copied_empty.sort_order == empty_plan.sort_order

        src_image = await crud_venue_map.get_image(
            db_session, plan_id=test_venue_plan.id
        )
        new_image = await crud_venue_map.get_image(db_session, plan_id=copied.id)
        assert src_image is not None and new_image is not None
        assert new_image.id != src_image.id
        assert new_image.data == src_image.data
        assert new_image.etag == src_image.etag
        assert new_image.content_type == src_image.content_type
        assert (
            await crud_venue_map.get_image(db_session, plan_id=copied_empty.id) is None
        )

        markers = await crud_venue_map.list_markers_for_plans(
            db_session, plan_ids=[copied.id]
        )
        by_kind = {m.kind: m for m in markers}
        assert set(by_kind) == {"location", "entrance"}
        assert by_kind["location"].location_id == location_map[test_location.id]
        assert (by_kind["location"].x, by_kind["location"].y) == (
            test_location_marker.x,
            test_location_marker.y,
        )
        assert by_kind["entrance"].location_id is None
        assert by_kind["entrance"].label == generic.label
        assert {m.id for m in markers}.isdisjoint({test_location_marker.id, generic.id})

        # The source is untouched.
        source_images = await db_session.scalars(
            select(col(VenuePlanImage.id)).where(
                col(VenuePlanImage.plan_id) == test_venue_plan.id
            )
        )
        assert list(source_images) == [src_image.id]

    async def test_event_without_map_copies_nothing(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        test_event: Event,
    ) -> None:
        target = await _new_event(db_session, test_admin_user)

        assert await crud_venue_map.copy_for_clone(
            db_session, source_event_id=test_event.id, new_event_id=target.id
        ) == ({}, 0)

    async def test_marker_pointing_outside_the_event_is_skipped(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        test_venue_plan: VenuePlan,
        test_private_event: Event,
    ) -> None:
        foreign = Location(event_id=test_private_event.id, name="Elsewhere")
        db_session.add(foreign)
        await db_session.flush()
        db_session.add(
            VenueMarker(
                plan_id=test_venue_plan.id,
                location_id=foreign.id,
                kind="location",
                x=0.5,
                y=0.5,
            )
        )
        await db_session.flush()
        target = await _new_event(db_session, test_admin_user)

        _, plans_created = await crud_venue_map.copy_for_clone(
            db_session,
            source_event_id=test_venue_plan.event_id,
            new_event_id=target.id,
        )

        assert plans_created == 1
        (copied,) = await crud_venue_map.list_plans(db_session, event_id=target.id)
        assert (
            await crud_venue_map.list_markers_for_plans(
                db_session, plan_ids=[copied.id]
            )
            == []
        )


@pytest.mark.asyncio
class TestEventDeleteWithLocations:
    """``tasks.location_id`` is SET NULL although tasks also point at events.

    ``app/models/CLAUDE.md`` warns that a SET NULL next to an event FK can
    re-check a row against an event the same statement already removed. These
    pin that deleting the event with a full location graph still works.
    """

    async def _graph(
        self, session: AsyncSession, owner: User, task_creator: User
    ) -> tuple[Event, Location, Task, Shift, VenuePlan]:
        """An event of ``owner`` whose task, batch, shift and marker all
        reference one of its locations. The task is someone else's, so it
        outlives the event (``tasks.event_id`` is SET NULL)."""
        event = await _new_event(session, owner, name="Doomed")
        loc = Location(event_id=event.id, name="Hall")
        session.add(loc)
        await session.flush()
        task = Task(
            name="T",
            start_date=date(2027, 6, 10),
            end_date=date(2027, 6, 10),
            created_by_id=task_creator.id,
            event_id=event.id,
            location="Hall",
            location_id=loc.id,
        )
        session.add(task)
        await session.flush()
        batch = ShiftBatch(
            task_id=task.id,
            start_date=date(2027, 6, 10),
            end_date=date(2027, 6, 10),
            location="Hall",
            location_id=loc.id,
        )
        session.add(batch)
        await session.flush()
        shift = Shift(
            task_id=task.id,
            batch_id=batch.id,
            title="S",
            date=date(2027, 6, 10),
            start_time=time(9, 0),
            end_time=time(10, 0),
            location="Hall",
            location_id=loc.id,
        )
        plan = VenuePlan(event_id=event.id, name="P")
        session.add_all([shift, plan])
        await session.flush()
        session.add(
            VenueMarker(plan_id=plan.id, location_id=loc.id, kind="location", x=0, y=0)
        )
        await session.flush()
        return event, loc, task, shift, plan

    async def _assert_survivors(
        self,
        session: AsyncSession,
        loc: Location,
        task: Task,
        shift: Shift,
        plan: VenuePlan,
    ) -> None:
        reloaded = await session.get(Task, task.id, populate_existing=True)
        assert reloaded is not None
        assert reloaded.event_id is None
        assert reloaded.location_id is None
        assert reloaded.location == "Hall"
        reloaded_shift = await session.get(Shift, shift.id, populate_existing=True)
        assert reloaded_shift is not None and reloaded_shift.location_id is None
        assert reloaded_shift.location == "Hall"
        assert await session.get(Location, loc.id, populate_existing=True) is None
        assert await session.get(VenuePlan, plan.id, populate_existing=True) is None

    async def test_orm_event_delete(
        self,
        db_session: AsyncSession,
        test_admin_user: User,
        test_user: User,
    ) -> None:
        event, loc, task, shift, plan = await self._graph(
            db_session, test_admin_user, test_user
        )

        await db_session.delete(event)
        await db_session.flush()
        await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        await self._assert_survivors(db_session, loc, task, shift, plan)

    async def test_deleting_the_owning_user(
        self,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """User delete cascades to the event in the database, in one statement."""
        owner = User(
            subject="local|location-owner",
            email="owner-of-locations@example.com",
            name="Owner",
            roles=[],
        )
        db_session.add(owner)
        await db_session.flush()
        _, loc, task, shift, plan = await self._graph(db_session, owner, test_user)

        await db_session.delete(owner)
        await db_session.flush()
        # The tasks.location_id check is deferred to commit, which a test
        # transaction never reaches; run deferred checks now instead.
        await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        await self._assert_survivors(db_session, loc, task, shift, plan)
