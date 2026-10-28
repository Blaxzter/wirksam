"""Location and venue map fixtures for testing."""

import io

import pytest_asyncio
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.models.location import Location
from app.models.venue_plan import VenueMarker, VenuePlan, VenuePlanImage, VenueShape
from tests.fixtures.storage import put_file

PLAN_WIDTH = 800
PLAN_HEIGHT = 600


def make_png(
    width: int, height: int, color: tuple[int, int, int] = (40, 120, 200)
) -> bytes:
    """A solid-colour PNG generated in-process (no binary fixtures committed)."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest_asyncio.fixture
async def test_location(db_session: AsyncSession, test_event: Event) -> Location:
    """A location on ``test_event`` with a markdown description."""
    loc = Location(
        event_id=test_event.id,
        name="Foyer",
        description="Ground floor, **left** of the main entrance.",
        address="Kirchplatz 1, Musterstadt",
        map_url="https://maps.example.test/foyer",
        contact="Anna, 0170 1234567",
    )
    db_session.add(loc)
    await db_session.flush()
    await db_session.refresh(loc)
    return loc


@pytest_asyncio.fixture
async def test_venue_plan(db_session: AsyncSession, test_event: Event) -> VenuePlan:
    """A plan on ``test_event`` with an 800x600 image row already stored.

    The bytes are a real PNG rather than a normalised WebP; the image GET
    serves whatever is stored, and the etag only has to match the plan row.
    """
    data = make_png(PLAN_WIDTH, PLAN_HEIGHT)
    etag = "f" * 64
    plan = VenuePlan(
        event_id=test_event.id,
        name="Ground floor",
        sort_order=0,
        image_etag=etag,
        image_width=PLAN_WIDTH,
        image_height=PLAN_HEIGHT,
    )
    db_session.add(plan)
    await db_session.flush()
    db_session.add(
        VenuePlanImage(
            plan_id=plan.id,
            storage_key=await put_file(db_session, "venue-plans", data, "image/png"),
            content_type="image/png",
            etag=etag,
        )
    )
    await db_session.flush()
    await db_session.refresh(plan)
    return plan


@pytest_asyncio.fixture
async def test_location_marker(
    db_session: AsyncSession, test_venue_plan: VenuePlan, test_location: Location
) -> VenueMarker:
    """``test_location`` placed on ``test_venue_plan``."""
    marker = VenueMarker(
        plan_id=test_venue_plan.id,
        location_id=test_location.id,
        kind="location",
        x=0.25,
        y=0.75,
    )
    db_session.add(marker)
    await db_session.flush()
    await db_session.refresh(marker)
    return marker


@pytest_asyncio.fixture
async def blank_plan(db_session: AsyncSession, test_event: Event) -> VenuePlan:
    """A second plan on ``test_event`` with no image: a 1600x1000 blank canvas."""
    plan = VenuePlan(event_id=test_event.id, name="Garden", sort_order=1)
    db_session.add(plan)
    await db_session.flush()
    await db_session.refresh(plan)
    return plan


@pytest_asyncio.fixture
async def test_venue_shapes(
    db_session: AsyncSession, test_venue_plan: VenuePlan, test_location: Location
) -> list[VenueShape]:
    """One shape of each kind on ``test_venue_plan``, in drawing order: a rect
    linked to ``test_location``, a polygon, a path and a text label."""
    shapes = [
        VenueShape(
            plan_id=test_venue_plan.id,
            location_id=test_location.id,
            kind="rect",
            style="room",
            points=[[0.1, 0.1], [0.4, 0.5]],
            label="Foyer",
            sort_order=0,
        ),
        VenueShape(
            plan_id=test_venue_plan.id,
            kind="polygon",
            style="green",
            points=[[0.5, 0.1], [0.9, 0.1], [0.7, 0.4]],
            sort_order=1,
        ),
        VenueShape(
            plan_id=test_venue_plan.id,
            kind="path",
            style="path",
            points=[[0.1, 0.8], [0.9, 0.8]],
            stroke_width=0.02,
            sort_order=2,
        ),
        VenueShape(
            plan_id=test_venue_plan.id,
            kind="label",
            style="water",
            points=[[0.95, 0.5]],
            label="River",
            label_size="sm",
            sort_order=3,
        ),
    ]
    db_session.add_all(shapes)
    test_venue_plan.shapes_revision = 1
    db_session.add(test_venue_plan)
    await db_session.flush()
    return shapes
