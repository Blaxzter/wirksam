"""Avatar image normalization: validate, resize, re-encode as WebP.

The pipeline itself lives in :mod:`app.logic.images`; this module pins the
avatar limits (256 px, 64 KB) and keeps the historic three-tuple return.
"""

import logging
from typing import Final

import httpx
from PIL import Image

from app.logic.images import MAX_INPUT_BYTES as MAX_INPUT_BYTES
from app.logic.images import ImageProcessingError, encode_webp, normalize_image

logger = logging.getLogger(__name__)

MAX_DIM: Final = 256
MAX_OUTPUT_BYTES: Final = 64 * 1024  # 64 KB
QUALITIES: Final = (80, 60)

# Kept under its old name so routes and tests that catch it stay unchanged.
AvatarProcessingError = ImageProcessingError


def _encode_webp(img: Image.Image, quality: int) -> bytes:
    return encode_webp(img, quality)


def normalize_avatar(raw: bytes) -> tuple[bytes, str, str]:
    """Validate, orient, resize, and encode an image as WebP.

    Returns ``(data, content_type, etag)``.
    """
    result = normalize_image(
        raw,
        max_dim=MAX_DIM,
        max_output_bytes=MAX_OUTPUT_BYTES,
        qualities=QUALITIES,
        # Looked up at call time so ``_encode_webp`` stays patchable here.
        encoder=lambda img, quality: _encode_webp(img, quality=quality),
    )
    return result.data, result.content_type, result.etag


async def fetch_remote_avatar(url: str) -> bytes | None:
    """Best-effort download of an external avatar URL.

    Returns ``None`` on any failure (network, non-200, oversize).
    """
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return None
            content = response.content
            if len(content) > MAX_INPUT_BYTES:
                return None
            return content
    except (httpx.HTTPError, OSError):
        logger.debug("Failed to fetch remote avatar from %s", url, exc_info=True)
        return None
