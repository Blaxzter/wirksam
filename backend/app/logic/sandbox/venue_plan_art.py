"""The demo event's venue plan, drawn in code.

A sandbox cannot upload an image (``sandbox.upload_disabled``), so the map
screens would otherwise open empty for every visitor. Drawing the plan here
rather than committing a binary keeps the labels in the visitor's language and
the room layout in step with the marker coordinates in ``seed.py``: both are
expressed as fractions of the image, so they are written down once, below.

The result goes through the same ``normalize_image`` pipeline as an upload, so
the demo serves exactly what a real plan would (WebP, same size limits), and
is cached per language: the drawing never changes within a process.
"""

import functools
import io
from typing import Final

from PIL import Image, ImageDraw, ImageFont

from app.logic.images import NormalizedImage, normalize_image
from app.logic.venue_map import PLAN_MAX_BYTES, PLAN_MAX_DIM, PLAN_QUALITIES

WIDTH: Final = 1600
HEIGHT: Final = 1000

_GROUND = (238, 243, 232)
_FLOOR = (252, 250, 245)
_WALL = (64, 72, 84)
_ROOM_LINE = (150, 158, 168)
_TEXT = (52, 60, 72)
_PATH = (214, 204, 186)
_PARKING = (205, 208, 212)
_PARKING_LINE = (250, 250, 250)
_STAGE = (226, 220, 240)

Box = tuple[float, float, float, float]

# Fractions of the image: (left, top, right, bottom).
BUILDING: Final[Box] = (0.06, 0.08, 0.94, 0.70)
TOILETS: Final[Box] = (0.06, 0.08, 0.22, 0.36)
FIRST_AID: Final[Box] = (0.22, 0.08, 0.38, 0.36)
FOYER: Final[Box] = (0.06, 0.36, 0.38, 0.70)
MAIN_HALL: Final[Box] = (0.38, 0.08, 0.94, 0.70)
STAGE: Final[Box] = (0.50, 0.10, 0.82, 0.24)
PARKING: Final[Box] = (0.04, 0.80, 0.60, 0.94)
# Gaps in the outer wall: the main entrance (bottom, into the foyer) and a
# side entrance (right, into the hall).
MAIN_DOOR: Final[Box] = (0.17, 0.70, 0.27, 0.70)
SIDE_DOOR: Final[Box] = (0.94, 0.48, 0.94, 0.58)

# ASCII only: Pillow's bundled font has no umlauts, and a system font cannot
# be relied on inside the container. The German words are picked to match.
_LABELS: Final[dict[str, dict[str, str]]] = {
    "en": {
        "foyer": "Foyer",
        "hall": "Main hall",
        "stage": "Stage",
        "toilets": "Toilets",
        "first_aid": "First aid",
        "parking": "Car park",
        "street": "Riverside Road",
    },
    "de": {
        "foyer": "Foyer",
        "hall": "Halle",
        "stage": "Podium",
        "toilets": "WC",
        "first_aid": "Erste Hilfe",
        "parking": "Parkplatz",
        "street": "Uferweg",
    },
}


def _px(box: Box) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    return (
        round(left * WIDTH),
        round(top * HEIGHT),
        round(right * WIDTH),
        round(bottom * HEIGHT),
    )


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    # Pillow's bundled scalable font needs FreeType; the bitmap fallback is
    # small but still legible, and a demo must never fail over a typeface.
    try:
        return ImageFont.load_default(size=size)
    except (ImportError, OSError):  # pragma: no cover - depends on the build
        return ImageFont.load_default()


def _label(
    draw: ImageDraw.ImageDraw,
    box: Box,
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    *,
    anchor_y: float = 0.5,
) -> None:
    left, top, right, bottom = _px(box)
    x = (left + right) / 2
    y = top + (bottom - top) * anchor_y
    draw.text((x, y), text, fill=_TEXT, font=font, anchor="mm")


def draw_demo_plan(lang: str) -> bytes:
    """The plan as a PNG, before normalisation."""
    labels = _LABELS["de" if lang == "de" else "en"]
    img = Image.new("RGB", (WIDTH, HEIGHT), _GROUND)
    draw = ImageDraw.Draw(img)
    big = _font(40)
    small = _font(28)

    # Street along the bottom edge and the footpath from it to the main door.
    draw.rectangle(_px((0.0, 0.96, 1.0, 1.0)), fill=_PATH)
    door_l, _, door_r, door_y = _px(MAIN_DOOR)
    draw.rectangle((door_l + 10, door_y, door_r - 10, HEIGHT), fill=_PATH)
    _label(draw, (0.62, 0.96, 1.0, 1.0), labels["street"], small)

    # Car park with bay lines.
    draw.rectangle(_px(PARKING), fill=_PARKING)
    p_left, p_top, p_right, p_bottom = _px(PARKING)
    for x in range(p_left + 60, p_right, 60):
        draw.line((x, p_top, x, p_top + (p_bottom - p_top) // 3), fill=_PARKING_LINE)
        draw.line(
            (x, p_bottom - (p_bottom - p_top) // 3, x, p_bottom), fill=_PARKING_LINE
        )
    _label(draw, PARKING, labels["parking"], big)

    # Building floor, inner walls, then the outer wall on top.
    draw.rectangle(_px(BUILDING), fill=_FLOOR)
    draw.rectangle(_px(STAGE), fill=_STAGE, outline=_ROOM_LINE, width=3)
    for room in (TOILETS, FIRST_AID, FOYER):
        draw.rectangle(_px(room), outline=_ROOM_LINE, width=4)
    draw.rectangle(_px(BUILDING), outline=_WALL, width=10)

    # Door gaps: paint the floor colour back over the outer wall.
    # (Pillow draws an outline inwards from the box edge.)
    draw.rectangle((door_l, door_y - 10, door_r, door_y), fill=_FLOOR)
    side_x, side_t, _, side_b = _px(SIDE_DOOR)
    draw.rectangle((side_x - 10, side_t, side_x, side_b), fill=_FLOOR)
    # A gap in the foyer/hall wall, so the plan reads as one walkable space.
    hall_x = _px(MAIN_HALL)[0]
    foyer_t, foyer_b = _px(FOYER)[1], _px(FOYER)[3]
    gap_t = foyer_t + (foyer_b - foyer_t) // 3
    draw.rectangle((hall_x - 4, gap_t, hall_x + 4, gap_t + 90), fill=_FLOOR)

    _label(draw, FOYER, labels["foyer"], big, anchor_y=0.3)
    _label(draw, MAIN_HALL, labels["hall"], big, anchor_y=0.62)
    _label(draw, STAGE, labels["stage"], small)
    _label(draw, TOILETS, labels["toilets"], small, anchor_y=0.75)
    _label(draw, FIRST_AID, labels["first_aid"], small, anchor_y=0.75)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


@functools.cache
def render_demo_plan(lang: str) -> NormalizedImage:
    """The demo plan, normalised exactly like an upload. Cached per language."""
    return normalize_image(
        draw_demo_plan(lang),
        max_dim=PLAN_MAX_DIM,
        max_output_bytes=PLAN_MAX_BYTES,
        qualities=PLAN_QUALITIES,
    )
