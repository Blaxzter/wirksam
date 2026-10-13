"""The demo event's venue plans, drawn in code.

A sandbox cannot upload an image (``sandbox.upload_disabled``), so the map
screens would otherwise open empty for every visitor. Drawing the plans here
rather than committing binaries keeps the labels in the visitor's language and
the layout in step with the marker coordinates in ``seed.py``: every spot a
marker sits on is a fraction of the image, written down once in ``SPOTS`` and
drawn from the same numbers below.

Two plans, because a real event usually has more than one: the building (foyer,
main hall, the small rooms) and the outdoor area around it (festival meadow,
food stalls, car park). The style is deliberately quiet — warm ground with a
dot grid, soft rounded blocks, wide paths, small spaced-out captions — because
the interesting layer is the markers the app draws on top, not the picture.

Everything is drawn at twice the size and scaled down, which is the cheap way
to anti-alias Pillow's shapes. The result goes through the same
``normalize_image`` pipeline as an upload, so the demo serves exactly what a
real plan would (WebP, same size limits), and it is cached per plan and
language: the drawing never changes within a process.
"""

import functools
import io
import math
from collections.abc import Sequence
from typing import Final, Literal

from PIL import Image, ImageDraw, ImageFont

from app.logic.images import NormalizedImage, normalize_image
from app.logic.venue_map import PLAN_MAX_BYTES, PLAN_MAX_DIM, PLAN_QUALITIES

WIDTH: Final = 1600
HEIGHT: Final = 1000
# Supersampling factor: drawn at this multiple, then scaled down.
_SS: Final = 2

PlanKey = Literal["indoor", "outdoor"]
PLAN_KEYS: Final[tuple[PlanKey, ...]] = ("indoor", "outdoor")

Box = tuple[float, float, float, float]
Point = tuple[float, float]
Rgb = tuple[int, int, int]

_GROUND: Final[Rgb] = (241, 234, 220)
_DOT: Final[Rgb] = (224, 213, 192)
_FLOOR: Final[Rgb] = (248, 243, 233)
_FLOOR_EDGE: Final[Rgb] = (222, 208, 181)
_ROOM: Final[Rgb] = (233, 221, 197)
_FURNITURE: Final[Rgb] = (218, 201, 168)
_FURNITURE_SOFT: Final[Rgb] = (226, 212, 184)
_PATH: Final[Rgb] = (227, 214, 189)
_MEADOW: Final[Rgb] = (230, 228, 202)
_MEADOW_EDGE: Final[Rgb] = (216, 216, 184)
_TREE: Final[Rgb] = (212, 215, 182)
_WATER: Final[Rgb] = (212, 223, 218)
_BAY_LINE: Final[Rgb] = (246, 240, 228)
_TEXT: Final[Rgb] = (146, 126, 98)
_TEXT_SOFT: Final[Rgb] = (172, 153, 124)

# ── Shared geometry: fractions of the image, (left, top, right, bottom) ──

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


# Where markers sit, per plan. ``seed.py`` places every pin from this table, so
# a pin always lands on the feature drawn for it.
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

# Captions drawn into the picture. Uppercase on purpose: it reads as a map
# caption rather than a heading, and German capitals need no ``ß``.
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

# Pillow's bundled font (Aileron) has no umlauts or accents. Rather than rely
# on a system font that the container may not have, the base letter is drawn
# and the mark added by hand: two dots, or an acute stroke.
_DIAERESIS: Final[dict[str, str]] = {"Ä": "A", "Ö": "O", "Ü": "U"}
_ACUTE: Final[dict[str, str]] = {"É": "E"}

Font = ImageFont.ImageFont | ImageFont.FreeTypeFont


def _font(size: int) -> Font:
    # Pillow's bundled scalable font needs FreeType; the bitmap fallback is
    # small but still legible, and a demo must never fail over a typeface.
    try:
        return ImageFont.load_default(size=size * _SS)
    except (ImportError, OSError):  # pragma: no cover - depends on the build
        return ImageFont.load_default()


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


class _Canvas:
    """A supersampled drawing surface addressed in image fractions."""

    def __init__(self) -> None:
        self.img = Image.new("RGB", (WIDTH * _SS, HEIGHT * _SS), _GROUND)
        self.draw = ImageDraw.Draw(self.img)

    @staticmethod
    def x(fx: float) -> float:
        return fx * WIDTH * _SS

    @staticmethod
    def y(fy: float) -> float:
        return fy * HEIGHT * _SS

    @staticmethod
    def s(px: float) -> int:
        """A length given in output pixels, at drawing scale."""
        return round(px * _SS)

    def box(self, box: Box) -> tuple[float, float, float, float]:
        return (self.x(box[0]), self.y(box[1]), self.x(box[2]), self.y(box[3]))

    def dot_grid(self, step: int = 28, radius: float = 1.6) -> None:
        r = radius * _SS
        for gy in range(step // 2, HEIGHT, step):
            for gx in range(step // 2, WIDTH, step):
                cx, cy = gx * _SS, gy * _SS
                self.draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_DOT)

    def block(
        self,
        box: Box,
        fill: Rgb,
        *,
        radius: float = 18,
        outline: Rgb | None = None,
        width: float = 0,
    ) -> None:
        self.draw.rounded_rectangle(
            self.box(box),
            radius=self.s(radius),
            fill=fill,
            outline=outline,
            width=self.s(width) if outline else 0,
        )

    def circle(self, at: Point, radius: float, fill: Rgb) -> None:
        cx, cy, r = self.x(at[0]), self.y(at[1]), self.s(radius)
        self.draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)

    def path(self, points: Sequence[Point], width: float, fill: Rgb = _PATH) -> None:
        """A wide path with softly rounded bends and round ends."""
        pts = [(self.x(px), self.y(py)) for px, py in _smooth(points)]
        w = self.s(width)
        self.draw.line(pts, fill=fill, width=w, joint="curve")
        for px, py in (pts[0], pts[-1]):
            self.draw.ellipse(
                (px - w / 2, py - w / 2, px + w / 2, py + w / 2), fill=fill
            )

    def caption(
        self,
        at: Point,
        text: str,
        *,
        size: int = 15,
        fill: Rgb = _TEXT,
        tracking: float = 0.14,
    ) -> None:
        """Small spaced-out uppercase caption, centred on ``at``."""
        font = _font(size)
        text = text.upper()
        gap = size * _SS * tracking
        bases = [_DIAERESIS.get(c, _ACUTE.get(c, c)) for c in text]
        widths = [font.getlength(b) for b in bases]
        total = sum(widths) + gap * (len(text) - 1)
        cap = font.getbbox("H", anchor="ls")
        cap_height = -cap[1]
        x = self.x(at[0]) - total / 2
        baseline = self.y(at[1]) + cap_height / 2
        for char, base, w in zip(text, bases, widths, strict=True):
            self.draw.text((x, baseline), base, fill=fill, font=font, anchor="ls")
            top = baseline - cap_height
            if char in _DIAERESIS:
                r = max(1.0, size * _SS * 0.065)
                dot_y = top - r * 2.6
                for fx in (0.32, 0.68):
                    dx = x + w * fx
                    self.draw.ellipse((dx - r, dot_y - r, dx + r, dot_y + r), fill=fill)
            elif char in _ACUTE:
                t = max(1.0, size * _SS * 0.08)
                self.draw.line(
                    (x + w * 0.42, top - t * 1.2, x + w * 0.66, top - t * 3.4),
                    fill=fill,
                    width=round(t),
                )
            x += w + gap

    def png(self) -> bytes:
        out = io.BytesIO()
        # In place: the canvas is drawn once and thrown away.
        self.img.thumbnail((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        self.img.save(out, format="PNG")
        return out.getvalue()


def _draw_indoor(c: _Canvas, labels: dict[str, str]) -> None:
    # Outside: the street along the bottom, the path to the main door and the
    # path from the side door towards the meadow.
    c.block((-0.02, 0.925, 1.02, 1.02), _PATH, radius=0)
    c.caption((0.62, 0.9625), labels["street"], size=14, fill=_TEXT_SOFT)
    # Each path is exactly as wide as the doorway it leads to.
    door_l, door_r = MAIN_DOOR_X
    door_x = (door_l + door_r) / 2
    c.block((door_l, BUILDING[3] - 0.01, door_r, 0.94), _PATH, radius=0)
    side_t, side_b = SIDE_DOOR_Y
    c.block((BUILDING[2] - 0.01, side_t, 1.02, side_b), _PATH, radius=0)
    c.caption((0.952, side_b + 0.03), labels["to_meadow"], size=12, fill=_TEXT_SOFT)

    # The building: a pale floor with a soft edge, the rooms as blocks on it.
    c.block(BUILDING, _FLOOR, radius=28, outline=_FLOOR_EDGE, width=3)
    # Doorways: a gap in the edge, with a doormat just inside.
    c.block(
        (door_l, BUILDING[3] - 0.008, door_r, BUILDING[3] + 0.002), _FLOOR, radius=0
    )
    c.block(
        (door_x - 0.025, BUILDING[3] - 0.03, door_x + 0.025, BUILDING[3] - 0.012),
        _FURNITURE_SOFT,
        radius=4,
    )
    c.block(
        (BUILDING[2] - 0.004, side_t, BUILDING[2] + 0.002, side_b), _FLOOR, radius=0
    )

    for room in (TOILETS, FIRST_AID, KITCHEN, FOYER, MAIN_HALL):
        c.block(room, _ROOM, radius=20)

    # Kitchen: worktops along two walls.
    k_l, k_t, k_r, k_b = KITCHEN
    c.block(
        (k_l + 0.012, k_t + 0.022, k_r - 0.012, k_t + 0.055), _FURNITURE_SOFT, radius=6
    )
    c.block(
        (k_r - 0.03, k_t + 0.022, k_r - 0.012, k_b - 0.09), _FURNITURE_SOFT, radius=6
    )
    # Toilets: a row of cubicles.
    t_l, t_t, t_r, _ = TOILETS
    cell = (t_r - t_l - 0.024) / 3
    for i in range(3):
        left = t_l + 0.012 + i * cell
        c.block(
            (left + 0.003, t_t + 0.022, left + cell - 0.003, t_t + 0.075),
            _FURNITURE_SOFT,
            radius=5,
        )
    # First aid: a couch.
    f_l, f_t, _, _ = FIRST_AID
    c.block(
        (f_l + 0.014, f_t + 0.022, f_l + 0.04, f_t + 0.12), _FURNITURE_SOFT, radius=8
    )

    # Main hall: the stage with its front step, then rows of seats.
    s_l, _, s_r, s_b = STAGE
    c.block(
        (s_l - 0.012, s_b - 0.02, s_r + 0.012, s_b + 0.018), _FURNITURE_SOFT, radius=10
    )
    c.block(STAGE, _FURNITURE, radius=14)
    seat_w, seat_h = 0.011, 0.016
    aisle = (s_l + s_r) / 2
    row_y = 0.42
    while row_y < 0.69:
        fx = s_l + 0.005
        while fx < s_r - 0.005:
            if abs(fx + seat_w / 2 - aisle) > 0.025:
                c.block(
                    (fx, row_y, fx + seat_w, row_y + seat_h), _FURNITURE_SOFT, radius=3
                )
            fx += seat_w + 0.006
        row_y += 0.045

    # Foyer: café counter with tables, the welcome desk by the door, the
    # round information desk by the way into the hall.
    c.block(CAFE_COUNTER, _FURNITURE, radius=10)
    for tx, ty in (
        (0.115, 0.50),
        (0.175, 0.53),
        (0.115, 0.60),
        (0.235, 0.58),
        (0.175, 0.635),
    ):
        c.circle((tx, ty), 15, _FURNITURE_SOFT)
    c.block(WELCOME_DESK, _FURNITURE, radius=10)
    c.circle(INFO_DESK_AT, 24, _FURNITURE)

    # Captions sit low in each room, out of the way of the pins above them.
    c.caption((_center(TOILETS)[0], TOILETS[3] - 0.035), labels["toilets"])
    c.caption((_center(FIRST_AID)[0], FIRST_AID[3] - 0.035), labels["first_aid"])
    c.caption((_center(KITCHEN)[0], KITCHEN[3] - 0.035), labels["kitchen"])
    c.caption((0.33, FOYER[3] - 0.035), labels["foyer"])
    c.caption(
        (_center(CAFE_COUNTER)[0], CAFE_COUNTER[3] + 0.03),
        labels["cafe"],
        size=12,
        fill=_TEXT_SOFT,
    )
    c.caption((_center(MAIN_HALL)[0], MAIN_HALL[3] - 0.04), labels["hall"])
    c.caption(
        (_center(STAGE)[0], STAGE[3] - 0.035), labels["stage"], size=12, fill=_FLOOR
    )


def _tree(c: _Canvas, at: Point, radius: float) -> None:
    """A soft clump of three overlapping crowns."""
    dx, dy = radius * 0.45 / WIDTH, radius * 0.4 / HEIGHT
    c.circle((at[0] - dx, at[1] + dy * 0.4), radius * 0.75, _TREE)
    c.circle((at[0] + dx, at[1] + dy * 0.6), radius * 0.7, _TREE)
    c.circle((at[0], at[1] - dy * 0.6), radius * 0.78, _TREE)


def _draw_outdoor(c: _Canvas, labels: dict[str, str]) -> None:
    # The river along the right edge, with a gently wavy bank.
    bank = [
        (0.905 + 0.018 * math.sin(i / 20 * math.pi * 2.2), i / 20) for i in range(21)
    ]
    c.draw.polygon(
        [(c.x(bx), c.y(by)) for bx, by in bank] + [(c.x(1.0), c.y(1.0)), (c.x(1.0), 0)],
        fill=_WATER,
    )
    c.caption((0.955, 0.50), labels["river"], size=13, fill=_TEXT_SOFT)

    # The street along the bottom and the paths off it.
    c.block((-0.02, 0.925, 0.89, 1.02), _PATH, radius=0)
    c.caption((0.70, 0.9625), labels["street"], size=14, fill=_TEXT_SOFT)
    gate_x, gate_y = MEADOW_GATE_AT
    c.path([(gate_x, 0.95), (gate_x, gate_y)], 64)
    c.path([(_center(CAR_PARK)[0], 0.86), (_center(CAR_PARK)[0], 0.95)], 54)
    c.path([(OUT_BUILDING[2] - 0.02, 0.24), SIDE_GATE_AT], 48)
    c.path(
        [
            (_center(OUT_BUILDING)[0], OUT_BUILDING[3]),
            (_center(OUT_BUILDING)[0], CAR_PARK[1]),
        ],
        40,
    )

    # The meadow, with a looping path through it from the gate.
    c.block(MEADOW, _MEADOW, radius=60, outline=_MEADOW_EDGE, width=3)
    stalls_x = _center(STALLS_ROW)[0]
    c.path([(gate_x, gate_y), (gate_x, 0.50), (stalls_x, 0.38), (stalls_x, 0.21)], 34)
    c.path([(gate_x, 0.52), (0.64, 0.52), KIDS_CORNER_AT], 28)
    c.path([(stalls_x, 0.36), (0.45, 0.31), SIDE_GATE_AT], 28)
    c.path([(stalls_x, 0.33), (0.70, 0.33), (0.74, 0.24), FIRST_AID_TENT_AT], 24)

    # Food stalls: a row of booths with benches in front of them.
    s_l, s_t, s_r, s_b = STALLS_ROW
    booths = 5
    booth_w = (s_r - s_l - 0.01 * (booths - 1)) / booths
    for i in range(booths):
        left = s_l + i * (booth_w + 0.01)
        c.block((left, s_t, left + booth_w, s_b), _FURNITURE_SOFT, radius=10)
        c.block((left, s_t, left + booth_w, s_t + 0.022), _FURNITURE, radius=8)
    # Beer tables between the stalls and the kids' corner.
    for row in range(3):
        by = 0.37 + row * 0.035
        for bx in (0.6, 0.652):
            c.block((bx, by, bx + 0.045, by + 0.013), _FURNITURE_SOFT, radius=4)

    # Kids' corner: a sandpit ring; the first-aid tent; portable toilets.
    c.circle(KIDS_CORNER_AT, 64, _FURNITURE_SOFT)
    c.circle(KIDS_CORNER_AT, 46, _MEADOW)
    c.circle(FIRST_AID_TENT_AT, 36, _FURNITURE)
    c.circle(FIRST_AID_TENT_AT, 22, _FURNITURE_SOFT)
    c.block(OUT_TOILETS, _ROOM, radius=10)
    t_l, t_t, t_r, t_b = OUT_TOILETS
    cell = (t_r - t_l - 0.016) / 3
    for i in range(3):
        left = t_l + 0.008 + i * cell
        c.block(
            (left + 0.003, t_t + 0.012, left + cell - 0.003, t_b - 0.012),
            _FURNITURE_SOFT,
            radius=4,
        )

    # Gate posts either side of the path.
    for dx in (-0.032, 0.032):
        c.circle((gate_x + dx, gate_y), 9, _FURNITURE)

    # The building (its own plan has the inside), the car park, the bikes.
    c.block(OUT_BUILDING, _ROOM, radius=22, outline=_FLOOR_EDGE, width=3)
    c.block(CAR_PARK, _ROOM, radius=22)
    p_l, p_t, p_r, p_b = CAR_PARK
    bay = 0.032
    lane_t, lane_b = p_t + 0.12, p_b - 0.12
    fx = p_l + 0.02 + bay
    while fx < p_r - 0.02:
        c.draw.line(
            (c.x(fx), c.y(p_t + 0.02), c.x(fx), c.y(lane_t)),
            fill=_BAY_LINE,
            width=c.s(3),
        )
        c.draw.line(
            (c.x(fx), c.y(lane_b), c.x(fx), c.y(p_b - 0.02)),
            fill=_BAY_LINE,
            width=c.s(3),
        )
        fx += bay
    c.block(BIKE_PARKING, _ROOM, radius=12)
    b_l, b_t, b_r, b_b = BIKE_PARKING
    fx = b_l + 0.015
    while fx < b_r - 0.01:
        c.draw.line(
            (c.x(fx), c.y(b_t + 0.015), c.x(fx), c.y(b_b - 0.015)),
            fill=_FURNITURE,
            width=c.s(4),
        )
        fx += 0.014

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
        _tree(c, at, r)

    # Captions.
    c.caption((_center(OUT_BUILDING)[0], _center(OUT_BUILDING)[1]), labels["building"])
    c.caption((0.47, 0.665), labels["meadow"])
    c.caption(
        (_center(STALLS_ROW)[0], s_t - 0.025),
        labels["stalls"],
        size=12,
        fill=_TEXT_SOFT,
    )
    c.caption(
        (KIDS_CORNER_AT[0], KIDS_CORNER_AT[1] + 0.095),
        labels["kids"],
        size=12,
        fill=_TEXT_SOFT,
    )
    c.caption((_center(CAR_PARK)[0], CAR_PARK[3] - 0.035), labels["car_park"])
    c.caption(
        (_center(BIKE_PARKING)[0], BIKE_PARKING[3] + 0.03),
        labels["bikes"],
        size=12,
        fill=_TEXT_SOFT,
    )
    c.caption((gate_x + 0.07, gate_y + 0.035), labels["gate"], size=12, fill=_TEXT_SOFT)


def draw_demo_plan(plan: PlanKey, lang: str) -> bytes:
    """One of the plans as a PNG, before normalisation."""
    labels = _LABELS["de" if lang == "de" else "en"]
    canvas = _Canvas()
    canvas.dot_grid()
    if plan == "indoor":
        _draw_indoor(canvas, labels)
    else:
        _draw_outdoor(canvas, labels)
    return canvas.png()


@functools.cache
def render_demo_plan(plan: PlanKey, lang: str) -> NormalizedImage:
    """A demo plan, normalised exactly like an upload. Cached per plan and language."""
    return normalize_image(
        draw_demo_plan(plan, lang),
        max_dim=PLAN_MAX_DIM,
        max_output_bytes=PLAN_MAX_BYTES,
        qualities=PLAN_QUALITIES,
    )
