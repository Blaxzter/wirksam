"""Geometry of drawn venue-map shapes (#185 phase 2).

Pure functions only, shared by the request schemas (which validate a shape on
the way in) and the batch logic (which re-validates a shape after merging a
partial update onto it). Nothing here touches the database, and nothing here
imports a schema, so ``app.schemas.venue_map`` can import it without a cycle.

Coordinates are normalised to the plan's effective size, exactly like marker
coordinates: ``x`` is a fraction of the width, ``y`` of the height.
"""

import math
import uuid
from collections.abc import Sequence
from typing import Final, NamedTuple

from pydantic_core import PydanticCustomError

MAX_SHAPES_PER_PLAN: Final = 500
MAX_POINTS_PER_SHAPE: Final = 500
# All shapes of one plan together: the map page loads every plan's drawing in
# one response, so a plan must stay small even when each shape is within limits.
MAX_POINTS_PER_PLAN: Final = 20_000
MAX_OPS_PER_BATCH: Final = 200
MAX_LABEL_LENGTH: Final = 120
# Normalised, per axis: anything smaller is a stray click, not a room.
MIN_RECT_SIZE: Final = 0.002
# Path widths as a fraction of the plan's shorter side.
STROKE_WIDTH_RANGE: Final = (0.002, 0.2)
DEFAULT_STROKE_WIDTH: Final = 0.02
# Five decimals is ~0.016 px on a 1600 px plan: exact enough, and keeps the
# JSON short.
_DECIMALS: Final = 5

# Only areas can stand for a place; a line or a caption cannot be tapped open.
LINKABLE_KINDS: Final = frozenset({"rect", "polygon"})

POINTS_COUNT: Final = "venue_shape.points_count"
LABEL_REQUIRED: Final = "venue_shape.label_required"
STROKE_WIDTH: Final = "venue_shape.stroke_width"
LINK_NOT_ALLOWED: Final = "venue_shape.link_not_allowed"
TOO_SMALL: Final = "venue_shape.too_small"
LABEL_ANCHOR: Final = "venue_shape.label_anchor"

# (minimum, maximum) number of points per kind.
_POINT_COUNTS: Final[dict[str, tuple[int, int]]] = {
    "rect": (2, 2),
    "polygon": (3, MAX_POINTS_PER_SHAPE),
    "path": (2, MAX_POINTS_PER_SHAPE),
    "label": (1, 1),
}


class NormalisedGeometry(NamedTuple):
    """What a valid shape is stored as."""

    points: list[list[float]]
    stroke_width: float | None


def round_point(p: Sequence[float]) -> list[float]:
    return [round(float(p[0]), _DECIMALS), round(float(p[1]), _DECIMALS)]


def validate_geometry(
    *,
    kind: str,
    points: Sequence[Sequence[float]],
    label: str | None,
    stroke_width: float | None,
    location_id: uuid.UUID | None,
    label_x: float | None,
    label_y: float | None,
) -> NormalisedGeometry:
    """Check a whole shape and return its normalised geometry.

    A rect's two corners come back sorted into (min, max) and every point is
    rounded. A path without a width gets :data:`DEFAULT_STROKE_WIDTH`; every
    other kind has none, whatever was sent. Raises ``PydanticCustomError``
    with a ``venue_shape.*`` code, so the same rule reports the same code
    whether it fires in the request schema or after a merge in the batch.
    """
    low, high = _POINT_COUNTS[kind]
    if not low <= len(points) <= high:
        raise PydanticCustomError(
            POINTS_COUNT,
            "A {kind} needs between {low} and {high} points",
            {"kind": kind, "low": low, "high": high},
        )
    if kind == "label" and not (label and label.strip()):
        raise PydanticCustomError(LABEL_REQUIRED, "A text label needs some text")
    if location_id is not None and kind not in LINKABLE_KINDS:
        raise PydanticCustomError(
            LINK_NOT_ALLOWED, "Only rectangles and shapes can be linked to a place"
        )
    if (label_x is None) != (label_y is None):
        raise PydanticCustomError(
            LABEL_ANCHOR, "label_x and label_y must be set together"
        )

    normalised = [round_point(p) for p in points]
    if kind == "rect":
        (ax, ay), (bx, by) = normalised
        normalised = [[min(ax, bx), min(ay, by)], [max(ax, bx), max(ay, by)]]
        width = normalised[1][0] - normalised[0][0]
        height = normalised[1][1] - normalised[0][1]
        if width < MIN_RECT_SIZE or height < MIN_RECT_SIZE:
            raise PydanticCustomError(TOO_SMALL, "The rectangle is too small")

    width_out: float | None = None
    if kind == "path":
        width_out = DEFAULT_STROKE_WIDTH if stroke_width is None else stroke_width
        low_w, high_w = STROKE_WIDTH_RANGE
        if not (low_w <= width_out <= high_w):
            raise PydanticCustomError(
                STROKE_WIDTH,
                "The line width must be between {low} and {high}",
                {"low": low_w, "high": high_w},
            )
        width_out = round(width_out, _DECIMALS)
    return NormalisedGeometry(points=normalised, stroke_width=width_out)


def _bbox_centre(points: Sequence[Sequence[float]]) -> tuple[float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


def _polygon_centroid(points: Sequence[Sequence[float]]) -> tuple[float, float]:
    """Area centroid (shoelace); the bbox centre for a degenerate polygon."""
    twice_area = 0.0
    cx = 0.0
    cy = 0.0
    n = len(points)
    for i in range(n):
        x0, y0 = points[i][0], points[i][1]
        x1, y1 = points[(i + 1) % n][0], points[(i + 1) % n][1]
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(twice_area / 2) < 1e-9:
        return _bbox_centre(points)
    return (cx / (3 * twice_area), cy / (3 * twice_area))


def _path_midpoint(points: Sequence[Sequence[float]]) -> tuple[float, float]:
    """The point halfway along the polyline, measured by length."""
    lengths = [math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)]
    total = sum(lengths)
    if total <= 0:
        return (points[0][0], points[0][1])
    remaining = total / 2
    for i, seg in enumerate(lengths):
        if remaining <= seg and seg > 0:
            t = remaining / seg
            (x0, y0), (x1, y1) = points[i], points[i + 1]
            return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
        remaining -= seg
    return (points[-1][0], points[-1][1])  # pragma: no cover - float rounding


def shape_anchor(kind: str, points: Sequence[Sequence[float]]) -> tuple[float, float]:
    """Where a shape's pill or caption sits, in normalised plan coordinates.

    rect: centre. polygon: area centroid (bbox centre when degenerate). path:
    halfway along its length. label: its point. Must match the frontend's
    ``shapeAnchor`` in ``src/lib/venue-shapes.ts``; both are tested against
    ``tests/fixtures/shape_anchor_cases.json``.
    """
    if kind == "polygon":
        return _polygon_centroid(points)
    if kind == "path":
        return _path_midpoint(points)
    if kind == "label":
        return (points[0][0], points[0][1])
    return _bbox_centre(points)
