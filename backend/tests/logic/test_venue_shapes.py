"""Unit tests for the pure shape geometry in ``app/logic/venue_shapes.py``."""

import json
import uuid
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticCustomError

from app.logic.venue_shapes import (
    DEFAULT_STROKE_WIDTH,
    PROP_STYLE,
    PROP_TYPES,
    round_point,
    shape_anchor,
    validate_geometry,
)
from app.schemas.venue_map import PropType, ShapeStyle, VenueShapeCreate

CASES_FILE = Path(__file__).parent.parent / "fixtures" / "shape_anchor_cases.json"


def _geometry(**overrides: Any):
    args: dict[str, Any] = {
        "kind": "rect",
        "style": "room",
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
            ("prop", 0),
            ("prop", 2),
        ],
    )
    def test_points_count(self, kind: str, count: int) -> None:
        points = [[i / 1000, i / 1000] for i in range(count)]
        assert (
            _code(kind=kind, points=points, label="x", prop="tree")
            == "venue_shape.points_count"
        )

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
        [
            ("path", [[0, 0], [1, 1]]),
            ("label", [[0.5, 0.5]]),
            ("prop", [[0.5, 0.5]]),
        ],
    )
    def test_only_areas_link_to_a_place(
        self, kind: str, points: list[list[float]]
    ) -> None:
        assert (
            _code(
                kind=kind,
                points=points,
                label="x",
                location_id=uuid.uuid4(),
                prop="tree",
            )
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


def _prop(**overrides: Any):
    args: dict[str, Any] = {"kind": "prop", "points": [[0.3, 0.4]], "prop": "tree"}
    args.update(overrides)
    return _geometry(**args)


class TestProps:
    def test_defaults(self) -> None:
        geometry = _prop()
        assert geometry.points == [[0.3, 0.4]]
        assert geometry.prop == "tree"
        assert geometry.rotation == 0.0
        assert geometry.scale == 1.0
        assert geometry.stroke_width is None

    def test_needs_a_prop_type(self) -> None:
        assert _code(kind="prop", points=[[0.3, 0.4]]) == "venue_shape.prop_required"

    @pytest.mark.parametrize("scale", [0.2, 4.1, 0.0, -1.0])
    def test_scale_out_of_range(self, scale: float) -> None:
        with pytest.raises(PydanticCustomError) as exc:
            _prop(scale=scale)
        assert exc.value.type == "venue_shape.prop_scale"
        assert exc.value.context == {"low": 0.25, "high": 4.0}

    @pytest.mark.parametrize("scale", [0.25, 4.0, 1.23456])
    def test_scale_in_range_is_rounded(self, scale: float) -> None:
        assert _prop(scale=scale).scale == round(scale, 3)

    @pytest.mark.parametrize(
        ("rotation", "expected"),
        [
            (-90, 270.0),
            (360, 0.0),
            (725, 5.0),
            (12.34, 12.3),
            (359.96, 0.0),
            (-0.04, 0.0),
            (None, 0.0),
        ],
    )
    def test_rotation_is_normalised(
        self, rotation: float | None, expected: float
    ) -> None:
        assert _prop(rotation=rotation).rotation == expected

    def test_style_is_forced_to_the_family(self) -> None:
        assert _prop(style="wall").style == "green"
        assert _prop(style="wall", prop="bench").style == "furniture"
        assert _prop(style="wall", prop="tent").style == "area"

    def test_stroke_width_is_dropped(self) -> None:
        assert _prop(stroke_width=0.05).stroke_width is None

    def test_a_caption_is_allowed(self) -> None:
        assert _prop(label="Info").points

    @pytest.mark.parametrize(
        ("kind", "points"),
        [
            ("rect", [[0.1, 0.1], [0.5, 0.5]]),
            ("polygon", [[0, 0], [1, 0], [0, 1]]),
            ("path", [[0, 0], [1, 1]]),
            ("label", [[0.5, 0.5]]),
        ],
    )
    def test_other_kinds_drop_prop_fields(
        self, kind: str, points: list[list[float]]
    ) -> None:
        geometry = _geometry(
            kind=kind,
            points=points,
            label="x",
            style="wall",
            prop="tree",
            rotation=90,
            scale=2,
        )
        assert geometry.style == "wall"
        assert (geometry.prop, geometry.rotation, geometry.scale) == (None, None, None)

    def test_prop_type_literal_matches_the_logic(self) -> None:
        assert get_args(PropType) == PROP_TYPES
        assert set(PROP_STYLE) == set(PROP_TYPES)
        assert set(PROP_STYLE.values()) <= set(get_args(ShapeStyle))

    def test_anchor_is_the_point(self) -> None:
        assert shape_anchor("prop", [[0.3, 0.4]]) == (0.3, 0.4)


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

    def test_prop_through_the_schema(self) -> None:
        shape = VenueShapeCreate.model_validate(
            {
                "kind": "prop",
                "style": "wall",
                "points": [[0.5, 0.5]],
                "prop": "conifer",
                "rotation": -90,
                "scale": 1.5,
                "stroke_width": 0.05,
            }
        )
        assert shape.style == "green"
        assert (shape.prop, shape.rotation, shape.scale) == ("conifer", 270.0, 1.5)
        assert shape.stroke_width is None

    def test_prop_schema_rejects_unknown_types_and_wild_rotations(self) -> None:
        base = {"kind": "prop", "style": "green", "points": [[0.5, 0.5]]}
        with pytest.raises(ValidationError):
            VenueShapeCreate.model_validate({**base, "prop": "palm"})
        with pytest.raises(ValidationError):
            VenueShapeCreate.model_validate({**base, "prop": "tree", "rotation": 725})
        with pytest.raises(ValidationError) as exc:
            VenueShapeCreate.model_validate(base)
        assert exc.value.errors()[0]["type"] == "venue_shape.prop_required"

    def test_new_styles_are_accepted(self) -> None:
        for style in ("hedge", "fence", "sand"):
            shape = VenueShapeCreate.model_validate(
                {"kind": "path", "style": style, "points": [[0, 0], [0.5, 0.5]]}
            )
            assert shape.style == style

    def test_coordinates_stay_in_range(self) -> None:
        with pytest.raises(ValidationError):
            VenueShapeCreate.model_validate(
                {"kind": "rect", "style": "room", "points": [[0, 0], [1.01, 0.5]]}
            )
