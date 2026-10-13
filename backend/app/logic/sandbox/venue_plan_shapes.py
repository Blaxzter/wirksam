"""The demo event's venue plans, drawn as shapes.

A sandbox cannot upload an image (``sandbox.upload_disabled``), so the map
screens would otherwise open empty for every visitor. The demo plans are
therefore made the way an organiser would make one in the editor: blank
canvases with rooms, areas, paths and captions on them. Being vectors, they
follow the light and dark theme like the rest of the app.

Two plans, because a real event usually has more than one: the building (foyer,
main hall, the small rooms) and the outdoor area around it (festival meadow,
food stalls, car park).

Every spot a marker sits on is written down once in ``SPOTS``, and the shapes
below are built from the same numbers, so a pin always lands on the feature
drawn for it. Coordinates are fractions of the 1600 x 1000 canvas.
"""

import functools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

WIDTH: Final = 1600
HEIGHT: Final = 1000

PlanKey = Literal["indoor", "outdoor"]
PLAN_KEYS: Final[tuple[PlanKey, ...]] = ("indoor", "outdoor")

Box = tuple[float, float, float, float]
Point = tuple[float, float]
ShapeKind = Literal["rect", "polygon", "path", "label"]
LabelSize = Literal["sm", "md", "lg"]

# ── Shared geometry: fractions of the canvas, (left, top, right, bottom) ──

# Indoor plan.
BUILDING: Final[Box] = (0.04, 0.07, 0.90, 0.86)
TOILETS: Final[Box] = (0.065, 0.105, 0.185, 0.37)
FIRST_AID: Final[Box] = (0.20, 0.105, 0.305, 0.37)
KITCHEN: Final[Box] = (0.32, 0.105, 0.425, 0.37)
FOYER: Final[Box] = (0.065, 0.405, 0.425, 0.825)
MAIN_HALL: Final[Box] = (0.45, 0.105, 0.875, 0.825)
STAGE: Final[Box] = (0.53, 0.14, 0.795, 0.30)
WELCOME_DESK: Final[Box] = (0.165, 0.70, 0.265, 0.735)
CAFE_COUNTER: Final[Box] = (0.255, 0.435, 0.405, 0.47)
INFO_DESK_AT: Final[Point] = (0.385, 0.655)
MAIN_DOOR_X: Final[tuple[float, float]] = (0.18, 0.25)
SIDE_DOOR_Y: Final[tuple[float, float]] = (0.56, 0.64)

# Outdoor plan.
OUT_BUILDING: Final[Box] = (0.04, 0.07, 0.29, 0.40)
MEADOW: Final[Box] = (0.35, 0.07, 0.84, 0.70)
STALLS_ROW: Final[Box] = (0.41, 0.12, 0.68, 0.20)
KIDS_CORNER_AT: Final[Point] = (0.73, 0.50)
FIRST_AID_TENT_AT: Final[Point] = (0.775, 0.17)
OUT_TOILETS: Final[Box] = (0.385, 0.56, 0.465, 0.63)
CAR_PARK: Final[Box] = (0.04, 0.50, 0.29, 0.86)
BIKE_PARKING: Final[Box] = (0.36, 0.77, 0.47, 0.85)
MEADOW_GATE_AT: Final[Point] = (0.575, 0.70)
SIDE_GATE_AT: Final[Point] = (0.35, 0.26)


def _center(box: Box) -> Point:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


# Where markers sit, per plan. ``seed.py`` places every pin from this table and
# links the demo rooms through it, so a pin always lands on its feature.
SPOTS: Final[dict[PlanKey, dict[str, Point]]] = {
    "indoor": {
        "welcome_desk": _center(WELCOME_DESK),
        "cafe_counter": _center(CAFE_COUNTER),
        "stage": _center(STAGE),
        "info_desk": INFO_DESK_AT,
        "toilets": (_center(TOILETS)[0], 0.22),
        "first_aid": (_center(FIRST_AID)[0], 0.22),
        "kitchen": (_center(KITCHEN)[0], 0.22),
        "side_entrance": (BUILDING[2], sum(SIDE_DOOR_Y) / 2),
    },
    "outdoor": {
        "food_stalls": _center(STALLS_ROW),
        "kids_corner": KIDS_CORNER_AT,
        "first_aid_tent": FIRST_AID_TENT_AT,
        "toilets": _center(OUT_TOILETS),
        "car_park": (_center(CAR_PARK)[0], 0.64),
        "bike_parking": _center(BIKE_PARKING),
        "meadow_gate": MEADOW_GATE_AT,
        "side_gate": SIDE_GATE_AT,
    },
}

# Captions on the drawing, per language.
_LABELS: Final[dict[str, dict[str, str]]] = {
    "en": {
        "foyer": "Foyer",
        "hall": "Main hall",
        "stage": "Stage",
        "toilets": "Toilets",
        "first_aid": "First aid",
        "kitchen": "Kitchen",
        "cafe": "Café",
        "street": "Riverside Road",
        "to_meadow": "Meadow",
        "building": "Building",
        "meadow": "Festival meadow",
        "stalls": "Food stalls",
        "kids": "Kids' corner",
        "car_park": "Car park",
        "bikes": "Bikes",
        "river": "River",
        "gate": "Gate",
    },
    "de": {
        "foyer": "Foyer",
        "hall": "Große Halle",
        "stage": "Bühne",
        "toilets": "WC",
        "first_aid": "Erste Hilfe",
        "kitchen": "Küche",
        "cafe": "Café",
        "street": "Uferweg",
        "to_meadow": "Festwiese",
        "building": "Gebäude",
        "meadow": "Festwiese",
        "stalls": "Essensstände",
        "kids": "Kinderecke",
        "car_park": "Parkplatz",
        "bikes": "Fahrräder",
        "river": "Fluss",
        "gate": "Tor",
    },
}


@dataclass(frozen=True)
class ShapeSpec:
    """One shape of a demo plan, language-free (labels resolve in the seeder)."""

    kind: ShapeKind
    style: str
    points: tuple[Point, ...]
    #: Key into the captions; ``None`` draws no label.
    label_key: str | None = None
    #: Explicit caption anchor, keeping captions clear of the pins.
    label_at: Point | None = None
    label_size: LabelSize = "md"
    #: Paths only: a fraction of the shorter side (``HEIGHT``), i.e. px / 1000.
    stroke_width: float | None = None
    #: A ``SPOTS`` key: the seeder links the shape to the location whose
    #: marker uses that spot.
    link_spot: str | None = None


def label_text(key: str, lang: str) -> str:
    return _LABELS["de" if lang == "de" else "en"][key]


def rect(
    box: Box,
    style: str,
    *,
    label_key: str | None = None,
    label_at: Point | None = None,
    label_size: LabelSize = "md",
    link_spot: str | None = None,
) -> ShapeSpec:
    return ShapeSpec(
        kind="rect",
        style=style,
        points=((box[0], box[1]), (box[2], box[3])),
        label_key=label_key,
        label_at=label_at,
        label_size=label_size,
        link_spot=link_spot,
    )


def ngon(
    at: Point,
    radius_px: float,
    n: int,
    style: str,
    *,
    label_key: str | None = None,
    label_at: Point | None = None,
    label_size: LabelSize = "md",
    link_spot: str | None = None,
) -> ShapeSpec:
    """A regular ``n``-gon standing in for a circle of ``radius_px`` canvas px."""
    rx, ry = radius_px / WIDTH, radius_px / HEIGHT
    points = tuple(
        (
            min(1.0, max(0.0, at[0] + rx * math.cos(2 * math.pi * i / n))),
            min(1.0, max(0.0, at[1] + ry * math.sin(2 * math.pi * i / n))),
        )
        for i in range(n)
    )
    return ShapeSpec(
        kind="polygon",
        style=style,
        points=points,
        label_key=label_key,
        label_at=label_at,
        label_size=label_size,
        link_spot=link_spot,
    )


def _path(points: Sequence[Point], width_px: float) -> ShapeSpec:
    return ShapeSpec(
        kind="path",
        style="path",
        points=tuple(_smooth(points)),
        stroke_width=width_px / HEIGHT,
    )


def _label(at: Point, key: str, style: str = "path") -> ShapeSpec:
    return ShapeSpec(
        kind="label", style=style, points=(at,), label_key=key, label_size="sm"
    )


def _smooth(points: Sequence[Point], rounds: int = 3) -> list[Point]:
    """Chaikin corner cutting: the same ends, with the corners rounded off."""
    pts = list(points)
    for _ in range(rounds):
        if len(pts) < 3:
            break
        cut = [pts[0]]
        for (ax, ay), (bx, by) in zip(pts, pts[1:], strict=False):
            cut.append((0.75 * ax + 0.25 * bx, 0.75 * ay + 0.25 * by))
            cut.append((0.25 * ax + 0.75 * bx, 0.25 * ay + 0.75 * by))
        cut.append(pts[-1])
        pts = cut
    return pts


def _room(box: Box, key: str) -> ShapeSpec:
    """A small room, captioned low so the pin above it stays clear."""
    return rect(box, "room", label_key=key, label_at=(_center(box)[0], box[3] - 0.035))


def _indoor() -> list[ShapeSpec]:
    shapes: list[ShapeSpec] = []
    door_l, door_r = MAIN_DOOR_X
    side_t, side_b = SIDE_DOOR_Y
    # Outside: the street along the bottom, the walkway to the main door and
    # the one from the side door towards the meadow, each as wide as its door.
    shapes += [
        rect(
            (0.0, 0.925, 1.0, 1.0),
            "path",
            label_key="street",
            label_at=(0.62, 0.9625),
            label_size="sm",
        ),
        rect((door_l, BUILDING[3] - 0.01, door_r, 0.94), "path"),
        rect((BUILDING[2] - 0.01, side_t, 1.0, side_b), "path"),
        _label((0.952, side_b + 0.03), "to_meadow"),
        rect(BUILDING, "building"),
        _room(TOILETS, "toilets"),
        _room(FIRST_AID, "first_aid"),
        _room(KITCHEN, "kitchen"),
        rect(FOYER, "room", label_key="foyer", label_at=(0.33, FOYER[3] - 0.035)),
        rect(
            MAIN_HALL,
            "room",
            label_key="hall",
            label_at=(_center(MAIN_HALL)[0], MAIN_HALL[3] - 0.04),
            link_spot="stage",
        ),
    ]

    # Kitchen worktops along two walls.
    k_l, k_t, k_r, k_b = KITCHEN
    shapes += [
        rect((k_l + 0.012, k_t + 0.022, k_r - 0.012, k_t + 0.055), "furniture"),
        rect((k_r - 0.03, k_t + 0.022, k_r - 0.012, k_b - 0.09), "furniture"),
    ]
    # Toilets: a row of cubicles.
    t_l, t_t, t_r, _ = TOILETS
    cell = (t_r - t_l - 0.024) / 3
    for i in range(3):
        left = t_l + 0.012 + i * cell
        shapes.append(
            rect(
                (left + 0.003, t_t + 0.022, left + cell - 0.003, t_t + 0.075),
                "furniture",
            )
        )
    # First aid: a couch.
    f_l, f_t, _, _ = FIRST_AID
    shapes.append(rect((f_l + 0.014, f_t + 0.022, f_l + 0.04, f_t + 0.12), "furniture"))

    # Main hall: the stage with its front step, then rows of seats either side
    # of the aisle.
    s_l, _, s_r, s_b = STAGE
    shapes += [
        rect((s_l - 0.012, s_b - 0.02, s_r + 0.012, s_b + 0.018), "furniture"),
        rect(
            STAGE,
            "stage",
            label_key="stage",
            label_at=(_center(STAGE)[0], STAGE[3] - 0.035),
            label_size="sm",
        ),
    ]
    aisle = (s_l + s_r) / 2
    for i in range(6):
        row_y = 0.42 + i * 0.045
        shapes += [
            rect((s_l + 0.005, row_y, aisle - 0.025, row_y + 0.016), "furniture"),
            rect((aisle + 0.025, row_y, s_r - 0.005, row_y + 0.016), "furniture"),
        ]

    # Foyer: café counter with tables, the welcome desk by the door, the
    # round information desk by the way into the hall.
    shapes += [
        rect(CAFE_COUNTER, "furniture", link_spot="cafe_counter"),
        _label((_center(CAFE_COUNTER)[0], CAFE_COUNTER[3] + 0.03), "cafe", "furniture"),
    ]
    for at in (
        (0.115, 0.50),
        (0.175, 0.53),
        (0.115, 0.60),
        (0.235, 0.58),
        (0.175, 0.635),
    ):
        shapes.append(ngon(at, 15, 10, "furniture"))
    shapes += [
        rect(WELCOME_DESK, "furniture", link_spot="welcome_desk"),
        ngon(INFO_DESK_AT, 24, 16, "furniture"),
    ]
    return shapes


def _outdoor() -> list[ShapeSpec]:
    shapes: list[ShapeSpec] = []
    # The river along the right edge, with a gently wavy bank.
    bank = [
        (0.905 + 0.018 * math.sin(i / 20 * math.pi * 2.2), i / 20) for i in range(21)
    ]
    shapes.append(
        ShapeSpec(
            kind="polygon",
            style="water",
            points=(*bank, (1.0, 1.0), (1.0, 0.0)),
            label_key="river",
            label_at=(0.955, 0.50),
            label_size="sm",
        )
    )

    # The street along the bottom and the walkways off it.
    gate_x, gate_y = MEADOW_GATE_AT
    park_x = _center(CAR_PARK)[0]
    house_x = _center(OUT_BUILDING)[0]
    shapes += [
        rect(
            (0.0, 0.925, 0.89, 1.0),
            "path",
            label_key="street",
            label_at=(0.70, 0.9625),
            label_size="sm",
        ),
        _path([(gate_x, 0.95), (gate_x, gate_y)], 64),
        _path([(park_x, 0.86), (park_x, 0.95)], 54),
        _path([(OUT_BUILDING[2] - 0.02, 0.24), SIDE_GATE_AT], 48),
        _path([(house_x, OUT_BUILDING[3]), (house_x, CAR_PARK[1])], 40),
    ]

    # The meadow, with walkways looping through it from the gate.
    stalls_x = _center(STALLS_ROW)[0]
    shapes += [
        rect(MEADOW, "green", label_key="meadow", label_at=(0.47, 0.665)),
        _path(
            [(gate_x, gate_y), (gate_x, 0.50), (stalls_x, 0.38), (stalls_x, 0.21)], 34
        ),
        _path([(gate_x, 0.52), (0.64, 0.52), KIDS_CORNER_AT], 28),
        _path([(stalls_x, 0.36), (0.45, 0.31), SIDE_GATE_AT], 28),
        _path([(stalls_x, 0.33), (0.70, 0.33), (0.74, 0.24), FIRST_AID_TENT_AT], 24),
    ]

    # Food stalls: the row as an area, a booth for each stall on top.
    s_l, s_t, s_r, s_b = STALLS_ROW
    shapes.append(
        rect(
            STALLS_ROW,
            "area",
            label_key="stalls",
            label_at=(_center(STALLS_ROW)[0], s_t - 0.025),
            label_size="sm",
            link_spot="food_stalls",
        )
    )
    booths = 5
    booth_w = (s_r - s_l - 0.01 * (booths - 1)) / booths
    for i in range(booths):
        left = s_l + i * (booth_w + 0.01)
        shapes.append(rect((left, s_t, left + booth_w, s_b), "furniture"))
    # Beer tables between the stalls and the kids' corner.
    for row in range(3):
        by = 0.37 + row * 0.035
        for bx in (0.6, 0.652):
            shapes.append(rect((bx, by, bx + 0.045, by + 0.013), "furniture"))

    shapes += [
        ngon(
            KIDS_CORNER_AT,
            64,
            20,
            "area",
            label_key="kids",
            label_at=(KIDS_CORNER_AT[0], KIDS_CORNER_AT[1] + 0.095),
            label_size="sm",
            link_spot="kids_corner",
        ),
        ngon(FIRST_AID_TENT_AT, 36, 14, "furniture"),
        rect(OUT_TOILETS, "room"),
        rect(OUT_BUILDING, "building", label_key="building"),
        rect(
            CAR_PARK,
            "parking",
            label_key="car_park",
            label_at=(_center(CAR_PARK)[0], CAR_PARK[3] - 0.035),
            link_spot="car_park",
        ),
        rect(
            BIKE_PARKING,
            "parking",
            label_key="bikes",
            label_at=(_center(BIKE_PARKING)[0], BIKE_PARKING[3] + 0.03),
            label_size="sm",
        ),
    ]

    # Trees along the meadow edge and the street.
    for at, r in (
        ((0.33, 0.07), 26),
        ((0.86, 0.10), 30),
        ((0.865, 0.40), 26),
        ((0.85, 0.62), 34),
        ((0.33, 0.47), 22),
        ((0.505, 0.80), 26),
        ((0.62, 0.82), 30),
        ((0.74, 0.79), 26),
        ((0.82, 0.83), 22),
        ((0.31, 0.88), 20),
    ):
        shapes.append(ngon(at, r, 12, "green"))

    shapes.append(_label((gate_x + 0.07, gate_y + 0.035), "gate"))
    return shapes


@functools.cache
def demo_shapes(plan: PlanKey) -> tuple[ShapeSpec, ...]:
    """A demo plan's shapes in drawing order (later ones on top)."""
    return tuple(_indoor() if plan == "indoor" else _outdoor())
