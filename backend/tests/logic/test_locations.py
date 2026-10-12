"""Unit tests for ``app.logic.locations`` and the location schemas."""

import uuid
from datetime import date
from typing import Any, cast

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.logic.locations import apply_location, propagate_rename, resolve_location
from app.models.event import Event
from app.models.location import Location
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.schemas.location import LocationCreate, LocationRead, LocationUpdate
from app.schemas.venue_map import (
    VenueMarkerCreate,
    VenueMarkerUpdate,
    marker_kind_mismatch,
)


def _code(exc: HTTPException) -> str:
    detail = cast(dict[str, Any], exc.detail)
    return str(detail["code"])


@pytest.mark.asyncio
class TestResolveLocation:
    async def test_none_is_none(self, db_session: AsyncSession) -> None:
        assert (
            await resolve_location(db_session, event_id=uuid.uuid4(), location_id=None)
            is None
        )

    async def test_same_event(
        self, db_session: AsyncSession, test_location: Location
    ) -> None:
        loc = await resolve_location(
            db_session,
            event_id=test_location.event_id,
            location_id=test_location.id,
        )
        assert loc is test_location

    @pytest.mark.parametrize("case", ["other_event", "no_event", "unknown"])
    async def test_refused_with_wrong_event(
        self,
        db_session: AsyncSession,
        test_location: Location,
        test_private_event: Event,
        case: str,
    ) -> None:
        event_id: uuid.UUID | None = {
            "other_event": test_private_event.id,
            "no_event": None,
            "unknown": test_location.event_id,
        }[case]
        location_id = uuid.uuid4() if case == "unknown" else test_location.id

        with pytest.raises(HTTPException) as exc_info:
            await resolve_location(
                db_session, event_id=event_id, location_id=location_id
            )

        assert exc_info.value.status_code == 422
        assert _code(exc_info.value) == "location.wrong_event"


class TestApplyLocation:
    def test_location_wins_over_text(self) -> None:
        loc = Location(id=uuid.uuid4(), event_id=uuid.uuid4(), name="Foyer")
        shift = Shift(
            task_id=uuid.uuid4(), date=date(2026, 6, 1), title="S", location="typed"
        )

        apply_location(shift, loc, "typed")

        assert (shift.location_id, shift.location) == (loc.id, "Foyer")

    def test_no_location_keeps_free_text(self) -> None:
        shift = Shift(
            task_id=uuid.uuid4(),
            date=date(2026, 6, 1),
            title="S",
            location_id=uuid.uuid4(),
            location="Foyer",
        )

        apply_location(shift, None, "Somewhere else")

        assert (shift.location_id, shift.location) == (None, "Somewhere else")


@pytest.mark.asyncio
class TestPropagateRename:
    async def test_rewrites_text_on_all_referencing_rows_only(
        self,
        db_session: AsyncSession,
        test_location: Location,
        test_task: Task,
        test_shift: Shift,
    ) -> None:
        test_task.location_id = test_location.id
        test_task.location = "Foyer"
        unrelated = Shift(
            task_id=test_task.id,
            title="Other",
            date=test_shift.date,
            location="Foyer",
        )
        batch = ShiftBatch(
            task_id=test_task.id,
            start_date=test_shift.date,
            end_date=test_shift.date,
            location="Foyer",
            location_id=test_location.id,
        )
        test_shift.location_id = test_location.id
        db_session.add_all([test_task, test_shift, unrelated, batch])
        await db_session.flush()

        await propagate_rename(db_session, test_location.id, "Lobby")

        assert test_task.location == "Lobby"
        assert test_shift.location == "Lobby"
        assert batch.location == "Lobby"
        assert unrelated.location == "Foyer"


class TestLocationSchemas:
    def test_name_is_stripped_and_blanks_become_none(self) -> None:
        data = LocationCreate.model_validate(
            {
                "name": "  Foyer ",
                "description": "",
                "address": "   ",
                "map_url": "",
                "contact": None,
            }
        )
        assert data.name == "Foyer"
        assert (data.description, data.address, data.map_url, data.contact) == (
            None,
            None,
            None,
            None,
        )

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "data:text/html,hi",
            "ftp://example.test",
            "https://",
            "maps.example.test",
            "https://x.test/" + "a" * 2048,
        ],
    )
    def test_map_url_must_be_http(self, url: str) -> None:
        with pytest.raises(ValidationError):
            LocationCreate(name="Foyer", map_url=url)

    @pytest.mark.parametrize("url", ["https://maps.test/x", "HTTP://maps.test"])
    def test_map_url_accepts_http_and_https(self, url: str) -> None:
        assert LocationCreate(name="Foyer", map_url=f" {url} ").map_url == url

    @pytest.mark.parametrize("name", ["", "   ", "x" * 121])
    def test_bad_names(self, name: str) -> None:
        with pytest.raises(ValidationError):
            LocationCreate(name=name)

    def test_update_is_partial_but_name_cannot_be_nulled(self) -> None:
        assert LocationUpdate.model_validate({}).model_dump(exclude_unset=True) == {}
        assert LocationUpdate.model_validate({"description": ""}).model_dump(
            exclude_unset=True
        ) == {"description": None}
        with pytest.raises(ValidationError):
            LocationUpdate.model_validate({"name": None})

    def test_read_does_not_revalidate_stored_url(self) -> None:
        loc = Location(
            id=uuid.uuid4(), event_id=uuid.uuid4(), name="Old", map_url="legacy"
        )
        assert LocationRead.model_validate(loc).map_url == "legacy"


class TestMarkerSchemas:
    def test_location_marker_needs_an_id(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            VenueMarkerCreate(kind="location", x=0.5, y=0.5)
        assert exc_info.value.errors()[0]["type"] == "venue_marker.location_required"

    def test_generic_marker_must_not_have_an_id(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            VenueMarkerCreate(kind="toilets", location_id=uuid.uuid4(), x=0, y=0)
        assert exc_info.value.errors()[0]["type"] == "venue_marker.location_required"

    def test_valid_markers(self) -> None:
        assert VenueMarkerCreate(kind="parking", x=0, y=1).location_id is None
        loc_id = uuid.uuid4()
        assert (
            VenueMarkerCreate(kind="location", location_id=loc_id, x=1, y=0).location_id
            == loc_id
        )

    @pytest.mark.parametrize("field", ["x", "y"])
    @pytest.mark.parametrize("value", [-0.01, 1.01])
    def test_coordinates_are_normalised(self, field: str, value: float) -> None:
        with pytest.raises(ValidationError):
            VenueMarkerCreate.model_validate(
                {"kind": "kitchen", "x": 0.5, "y": 0.5, field: value}
            )
        with pytest.raises(ValidationError):
            VenueMarkerUpdate.model_validate({field: value})

    def test_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            VenueMarkerCreate.model_validate({"kind": "stage", "x": 0, "y": 0})

    def test_mismatch_helper(self) -> None:
        assert marker_kind_mismatch("location", None)
        assert marker_kind_mismatch("entrance", uuid.uuid4())
        assert not marker_kind_mismatch("location", uuid.uuid4())
        assert not marker_kind_mismatch("entrance", None)
