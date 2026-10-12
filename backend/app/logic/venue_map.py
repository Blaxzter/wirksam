"""Venue map limits.

A plan is line art shown full-screen and zoomed, so it keeps far more
resolution than an avatar; WebP compresses that kind of image well, which is
what keeps the byte budget modest.
"""

import threading
from typing import Final

from app.logic.images import NormalizedImage, normalize_image

PLAN_MAX_DIM: Final = 2560
PLAN_MAX_BYTES: Final = 2 * 1024 * 1024  # 2 MB
PLAN_QUALITIES: Final = (85, 75, 60)
# Decoded-size cap for an uploaded plan. ~30 MP is far more than a 2560 px
# output needs, and keeps one decode to roughly 120 MB (RGBA) of memory.
PLAN_MAX_PIXELS: Final = 30_000_000
# How many plan images are decoded at once across the whole process. The rest
# wait their turn, so parallel uploads cannot multiply the peak memory.
PLAN_DECODE_CONCURRENCY: Final = 2

_decode_slots = threading.BoundedSemaphore(PLAN_DECODE_CONCURRENCY)


def normalize_plan_image(raw: bytes) -> NormalizedImage:
    """Normalise an uploaded plan image with the plan limits.

    Blocking: run it in a worker thread. At most
    :data:`PLAN_DECODE_CONCURRENCY` run at once; further callers wait here.
    """
    with _decode_slots:
        return normalize_image(
            raw,
            max_dim=PLAN_MAX_DIM,
            max_output_bytes=PLAN_MAX_BYTES,
            qualities=PLAN_QUALITIES,
            max_pixels=PLAN_MAX_PIXELS,
        )
