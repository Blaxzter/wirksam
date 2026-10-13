"""Unit tests for the pure shape geometry in ``app/logic/venue_shapes.py``."""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticCustomError

from app.logic.venue_shapes import (
    DEFAULT_STROKE_WIDTH,
    round_point,
    shape_anchor,
    validate_geometry,
)
from app.schemas.venue_map import VenueShapeCreate

CASES_FILE = Path(__file__).parent.parent / "fixtures" / "shape_anchor_cases.json"


def _geometry(**overrides: Any):
    args: dict[str, Any] = {
        "kind": "rect",
        "points": [[0.1, 0.1], [0.5, 0.5]],
        "label": None,
        "stroke_width": None,
        "location_id": None,
        "label_x": None,
        "label_y": None,
    }
    args.update(overrides)
    return validate_geometry(**args)


def _code(**overrides: Any) -> str:
    with pytest.raises(PydanticCustomError) as exc:
        _geometry(**overrides)
    return exc.value.type


class TestValidateGeometry:
    @pytest.mark.parametrize(
        ("kind", "count"),
        [
            ("rect", 1),
            ("rect", 3),
            ("polygon", 2),
            ("polygon", 501),
            ("path", 1),
            ("path", 501),
            ("label", 2),
        ],
    )
    def test_points_count(self, kind: str, count: int) -> None:
        points = [[i / 1000, i / 1000] for i in range(count)]
        assert _code(kind=kind, points=points, label="x") == "venue_shape.points_count"

    @pytest.mark.parametrize(
        ("kind", "count"),
        [("rect", 2), ("polygon", 3), ("polygon", 500), ("path", 2), ("label", 1)],
    )
    def test_points_count_bounds_accepted(self, kind: str, count: int) -> None:
        points = [[i / 1000, (i * 7 % 13) / 13] for i in range(count)]
        if kind == "rect":
            points = [[0.1, 0.1], [0.2, 0.2]]
        assert _geometry(kind=kind, points=points, label="x").points

    def test_rect_corners_are_sorted_and_rounded(self) -> None:
        geometry = _geometry(points=[[0.5000001, 0.9], [0.1234567, 0.2]])
        assert geometry.points == [[0.12346, 0.2], [0.5, 0.9]]
        assert geometry.stroke_width is None

    def test_rect_too_small(self) -> None:
        assert _code(points=[[0.1, 0.1], [0.1015, 0.5]]) == "venue_shape.too_small"
        assert _code(points=[[0.1, 0.1], [0.5, 0.1]]) == "venue_shape.too_small"

    def test_label_kind_needs_text(self) -> None:
        assert (
            _code(kind="label", points=[[0.5, 0.5]], label=None)
            == "venue_shape.label_required"
        )
        assert (
            _code(kind="label", points=[[0.5, 0.5]], label="   ")
            == "venue_shape.label_required"
        )

    def test_path_stroke_width_defaults_and_ranges(self) -> None:
        path = {"kind": "path", "points": [[0, 0], [1, 1]]}
        assert _geometry(**path).stroke_width == DEFAULT_STROKE_WIDTH
        assert _geometry(**path, stroke_width=0.05).stroke_width == 0.05
        assert _code(**path, stroke_width=0.001) == "venue_shape.stroke_width"
        assert _code(**path, stroke_width=0.5) == "venue_shape.stroke_width"

    def test_other_kinds_drop_a_stroke_width(self) -> None:
        assert _geometry(stroke_width=0.05).stroke_width is None

    @pytest.mark.parametrize(
        ("kind", "points"),
        [("path", [[0, 0], [1, 1]]), ("label", [[0.5, 0.5]])],
    )
    def test_only_areas_link_to_a_place(
        self, kind: str, points: list[list[float]]
    ) -> None:
        assert (
            _code(kind=kind, points=points, label="x", location_id=uuid.uuid4())
            == "venue_shape.link_not_allowed"
        )

    def test_areas_may_link(self) -> None:
        location_id = uuid.uuid4()
        assert _geometry(location_id=location_id).points
        assert _geometry(
            kind="polygon",
            points=[[0, 0], [1, 0], [0, 1]],
            location_id=location_id,
        ).points

    def test_label_anchor_needs_both_coordinates(self) -> None:
        assert _code(label_x=0.5) == "venue_shape.label_anchor"
        assert _code(label_y=0.5) == "venue_shape.label_anchor"
        assert _geometry(label_x=0.5, label_y=0.5).points

    def test_round_point(self) -> None:
        assert round_point((0.123456789, 1)) == [0.12346, 1.0]


class TestShapeAnchor:
    def test_shared_cases(self) -> None:
        """The same file is read by the frontend's ``shapeAnchor`` spec."""
        cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))["cases"]
        assert len(cases) >= 10
        for case in cases:
            x, y = shape_anchor(case["kind"], case["points"])
            ex, ey = case["expected"]
            assert x == pytest.approx(ex, abs=1e-9), case["name"]
            assert y == pytest.approx(ey, abs=1e-9), case["name"]


class TestCreateSchema:
    """The request schema runs the same rules and reports the same codes."""

    def test_normalises_on_the_way_in(self) -> None:
        shape = VenueShapeCreate.model_validate(
            {
                "kind": "path",
                "style": "water",
                "points": [[0, 0], [0.5, 0.5]],
                "label": "  ",
            }
        )
        assert shape.stroke_width == DEFAULT_STROKE_WIDTH
        assert shape.label is None
        assert shape.label_size == "md"

    def test_error_code_surfaces_as_error_type(self) -> None:
        with pytest.raises(ValidationError) as exc:
            VenueShapeCreate.model_validate(
                {"kind": "label", "style": "room", "points": [[0.5, 0.5]]}
            )
        assert exc.value.errors()[0]["type"] == "venue_shape.label_required"

    def test_coordinates_stay_in_range(self) -> None:
        with pytest.raises(ValidationError):
            VenueShapeCreate.model_validate(
                {"kind": "rect", "style": "room", "points": [[0, 0], [1.01, 0.5]]}
            )
