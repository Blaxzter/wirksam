"""Image normalization shared by avatars and venue plans.

Validate, orient, shrink to fit a box, re-encode as WebP. The output is bounded
by pixel dimensions *and* by final byte size, so a single request can never
blow up the database, and decompression bombs are refused rather than decoded.
"""

import hashlib
import io
import warnings
from collections.abc import Callable
from typing import Final, NamedTuple

from PIL import Image, ImageOps, UnidentifiedImageError

# Pre-decode upload size cap. Anything larger is rejected before Pillow sees it.
MAX_INPUT_BYTES: Final = 20 * 1024 * 1024  # 20 MB
# Decoded-size cap. A tiny PNG can declare enormous dimensions; this refuses it
# from the header alone, below Pillow's own (much higher) bomb threshold.
MAX_PIXELS: Final = 60_000_000

Encoder = Callable[[Image.Image, int], bytes]


class ImageProcessingError(ValueError):
    """Raised when an uploaded image is invalid or exceeds limits."""


class NormalizedImage(NamedTuple):
    data: bytes
    content_type: str
    etag: str
    width: int
    height: int


def encode_webp(img: Image.Image, quality: int) -> bytes:
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=quality, method=6)
    return out.getvalue()


def normalize_image(
    raw: bytes,
    *,
    max_dim: int,
    max_output_bytes: int,
    qualities: tuple[int, ...],
    encoder: Encoder | None = None,
    max_pixels: int = MAX_PIXELS,
) -> NormalizedImage:
    """Validate, orient, resize and encode ``raw`` as WebP.

    The image is shrunk (never enlarged) to fit a ``max_dim`` square, keeping
    its aspect ratio, then encoded at each of ``qualities`` in turn until the
    result fits ``max_output_bytes``. ``width``/``height`` are those of the
    stored image. ``encoder`` exists so callers (and their tests) can swap the
    encode step; it defaults to :func:`encode_webp`. ``max_pixels`` caps the
    decoded size (width x height), which is what bounds memory use: a small
    file can still decode to hundreds of megabytes.

    CPU-bound and blocking; call it from a worker thread in async code.
    """
    if not qualities:
        raise ValueError("qualities must not be empty")
    encode = encoder or encode_webp

    if len(raw) == 0:
        raise ImageProcessingError("Empty file")
    if len(raw) > MAX_INPUT_BYTES:
        raise ImageProcessingError("Image exceeds 20 MB upload limit")

    with warnings.catch_warnings():
        # Pillow only *warns* between its two bomb thresholds; make that fatal.
        warnings.simplefilter("error", Image.DecompressionBombWarning)

        try:
            with Image.open(io.BytesIO(raw)) as probe:
                if probe.width * probe.height > max_pixels:
                    raise ImageProcessingError("Image is too large")
                probe.verify()
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ImageProcessingError("Image is too large") from exc
        except (UnidentifiedImageError, OSError) as exc:
            raise ImageProcessingError("File is not a valid image") from exc

        # verify() consumes the file; reopen for actual processing.
        try:
            with Image.open(io.BytesIO(raw)) as src:
                if src.format == "JPEG":
                    # Let libjpeg decode at a reduced scale (no smaller than
                    # the target box) instead of decoding full size first.
                    src.draft(src.mode, (max_dim, max_dim))
                oriented = ImageOps.exif_transpose(src) or src
                if oriented.mode not in ("RGB", "RGBA"):
                    oriented = oriented.convert(
                        "RGBA" if "A" in oriented.mode else "RGB"
                    )
                oriented.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                width, height = oriented.size
                data = b""
                for quality in qualities:
                    data = encode(oriented, quality)
                    if len(data) <= max_output_bytes:
                        break
        except (UnidentifiedImageError, OSError) as exc:
            raise ImageProcessingError("Failed to decode image") from exc

    if len(data) > max_output_bytes:
        raise ImageProcessingError("Image too large after compression")

    etag = hashlib.sha256(data).hexdigest()
    return NormalizedImage(data, "image/webp", etag, width, height)
