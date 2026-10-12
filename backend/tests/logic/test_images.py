"""Unit tests for the shared image pipeline in ``app.logic.images``.

``tests/logic/test_avatar.py`` covers the avatar wrapper and the rejection
branches it inherits. This module covers what venue plans add on top: the
returned dimensions, the configurable size box and quality ladder, and the
decompression-bomb guard. Every input is generated in-process; the "bombs" are
hand-built PNG headers a few dozen bytes long.
"""

import hashlib
import io
import struct
import warnings
import zlib
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.logic.images import (
    MAX_INPUT_BYTES,
    MAX_PIXELS,
    ImageProcessingError,
    NormalizedImage,
    normalize_image,
)
from app.logic.venue_map import PLAN_MAX_BYTES, PLAN_MAX_DIM, PLAN_QUALITIES


def _png(width: int, height: int, mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (width, height)).save(buffer, format="PNG")
    return buffer.getvalue()


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def _png_header_only(width: int, height: int) -> bytes:
    """A tiny PNG that *declares* ``width`` x ``height`` (1-bit greyscale).

    Pillow reads the size from IHDR on ``open()``, so this is enough to trip a
    pixel limit without ever allocating the pixels.
    """
    ihdr = struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(b""))
        + _chunk(b"IEND", b"")
    )


def _plan(raw: bytes) -> NormalizedImage:
    return normalize_image(
        raw,
        max_dim=PLAN_MAX_DIM,
        max_output_bytes=PLAN_MAX_BYTES,
        qualities=PLAN_QUALITIES,
    )


class TestDimensions:
    def test_returns_webp_with_sha256_etag_and_size(self) -> None:
        result = _plan(_png(320, 200))

        assert result.content_type == "image/webp"
        assert result.etag == hashlib.sha256(result.data).hexdigest()
        assert (result.width, result.height) == (320, 200)
        with Image.open(io.BytesIO(result.data)) as img:
            assert img.format == "WEBP"
            assert img.size == (320, 200)

    def test_wide_image_is_shrunk_to_the_box_keeping_aspect_ratio(self) -> None:
        result = normalize_image(
            _png(1000, 500), max_dim=400, max_output_bytes=10**6, qualities=(80,)
        )

        assert (result.width, result.height) == (400, 200)
        with Image.open(io.BytesIO(result.data)) as img:
            assert img.size == (400, 200)

    def test_tall_image_is_bounded_by_its_height(self) -> None:
        result = normalize_image(
            _png(300, 900), max_dim=300, max_output_bytes=10**6, qualities=(80,)
        )

        assert (result.width, result.height) == (100, 300)

    def test_small_images_are_not_upscaled(self) -> None:
        result = _plan(_png(40, 30))

        assert (result.width, result.height) == (40, 30)

    def test_palette_image_is_converted(self) -> None:
        result = _plan(_png(64, 48, mode="P"))

        assert (result.width, result.height) == (64, 48)


class TestQualityLadder:
    def test_stops_at_the_first_quality_that_fits(self) -> None:
        encoder = MagicMock(side_effect=[b"x" * 11, b"x" * 10, b"never"])

        result = normalize_image(
            _png(16, 16),
            max_dim=64,
            max_output_bytes=10,
            qualities=(90, 70, 50),
            encoder=encoder,
        )

        assert result.data == b"x" * 10
        assert [c.args[1] for c in encoder.call_args_list] == [90, 70]

    def test_walks_the_whole_ladder_before_giving_up(self) -> None:
        encoder = MagicMock(return_value=b"x" * 11)

        with pytest.raises(
            ImageProcessingError, match="Image too large after compression"
        ):
            normalize_image(
                _png(16, 16),
                max_dim=64,
                max_output_bytes=10,
                qualities=(85, 75, 60),
                encoder=encoder,
            )

        assert [c.args[1] for c in encoder.call_args_list] == [85, 75, 60]

    def test_real_encode_too_large_for_a_tiny_budget(self) -> None:
        with pytest.raises(ImageProcessingError, match="after compression"):
            normalize_image(
                _png(200, 200), max_dim=200, max_output_bytes=8, qualities=(60,)
            )

    def test_empty_ladder_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError, match="qualities"):
            normalize_image(_png(8, 8), max_dim=8, max_output_bytes=10**6, qualities=())


class TestRejections:
    def test_empty_input(self) -> None:
        with pytest.raises(ImageProcessingError, match="Empty file"):
            _plan(b"")

    def test_oversize_input(self) -> None:
        with pytest.raises(ImageProcessingError, match="20 MB"):
            _plan(b"\x00" * (MAX_INPUT_BYTES + 1))

    def test_not_an_image(self) -> None:
        with pytest.raises(ImageProcessingError, match="not a valid image"):
            _plan(b"%PDF-1.7 definitely a floor plan")


class TestDecompressionBombs:
    """Huge declared dimensions in a tiny file are a 400, never a 500."""

    def test_above_our_pixel_cap(self) -> None:
        # 64 MP: over MAX_PIXELS, under Pillow's own warning threshold.
        raw = _png_header_only(8000, 8000)
        assert 8000 * 8000 > MAX_PIXELS
        assert len(raw) < 200

        with pytest.raises(ImageProcessingError, match="Image is too large"):
            _plan(raw)

    def test_in_pillows_warning_band(self) -> None:
        # 100 MP: Pillow only warns here; the pipeline makes that fatal.
        with pytest.raises(ImageProcessingError, match="Image is too large"):
            _plan(_png_header_only(10_000, 10_000))

    def test_above_pillows_hard_limit(self) -> None:
        # 400 MP: Pillow raises DecompressionBombError, which is no OSError.
        with pytest.raises(ImageProcessingError, match="Image is too large"):
            _plan(_png_header_only(20_000, 20_000))

    def test_warning_filter_does_not_leak(self) -> None:
        before = list(warnings.filters)

        with pytest.raises(ImageProcessingError):
            _plan(_png_header_only(10_000, 10_000))

        assert warnings.filters == before
