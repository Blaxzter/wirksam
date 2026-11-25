"""Event logo limits.

A logo is shown small (a 32 px tile in the event switcher) and at most a few
times that on the invitation page and the printed schedule. 512 px covers
that at 3x with room to spare; the aspect ratio is kept, so a wide wordmark
stays wide and the page fits it into its box.
"""

from typing import Final

from app.logic.images import NormalizedImage, normalize_image

LOGO_MAX_DIM: Final = 512
LOGO_MAX_BYTES: Final = 160 * 1024  # 160 KB
LOGO_QUALITIES: Final = (85, 70, 55)


def normalize_event_logo(raw: bytes) -> NormalizedImage:
    """Normalise an uploaded logo. Blocking: run it in a worker thread."""
    return normalize_image(
        raw,
        max_dim=LOGO_MAX_DIM,
        max_output_bytes=LOGO_MAX_BYTES,
        qualities=LOGO_QUALITIES,
    )
