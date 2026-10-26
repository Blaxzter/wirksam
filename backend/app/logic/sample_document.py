"""A made-up first-aid certificate for demo team requests.

The team review dialog shows the file a requester attached next to the tick
box, and a demo with no file there cannot show that half of the flow. Real
uploads are refused in demo events (``sandbox.upload_disabled``), so the
seeders attach this instead: a PNG drawn at seed time that cannot be mistaken
for the real thing. It says MUSTER / SAMPLE in the title, carries a large
diagonal watermark, names a course provider that does not exist and states in
the footer that it is not a valid certificate. No real organisation's name,
logo or emblem appears on it — the provider's mark is a pair of initials.
"""

import datetime as dt
import functools
import io
import math
from typing import Final

from PIL import Image, ImageDraw, ImageFont

#: Fictitious on purpose, like its ``.example`` address (reserved, never resolves).
PROVIDER_NAME: Final = "Beispiel-Hilfsdienst e.V."
TITLE: Final = "MUSTER / SAMPLE - Bescheinigung Erste-Hilfe-Kurs"
FILENAME: Final = "muster-erste-hilfe-bescheinigung.png"
CONTENT_TYPE: Final = "image/png"

_SIZE: Final = (1240, 877)  # A5 landscape at 150 dpi
_INK: Final = (33, 37, 41)
_MUTED: Final = (108, 117, 125)
_ACCENT: Final = (21, 101, 92)
_PAPER: Final = (255, 255, 252)
_WATERMARK: Final = (200, 40, 40, 60)


# Pillow's bundled font covers ASCII and the middle dot, nothing more, so
# German text is written the way a typewriter would.
_ASCII: Final = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
        "ß": "ss",
        "–": "-",
        "—": "-",
    }
)


def _plain(text: str) -> str:
    return text.translate(_ASCII)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Pillow's bundled font; no system font is assumed to exist in the image.
    return ImageFont.load_default(size=size)


def _german_date(day: dt.date) -> str:
    return f"{day.day:02d}.{day.month:02d}.{day.year}"


@functools.lru_cache(maxsize=16)
def render_first_aid_sample(*, holder: str, course_date: dt.date) -> bytes:
    """The sample certificate for ``holder`` as PNG bytes.

    Cached: the sandbox draws the same one (same name, same relative date)
    for every visitor on a given day.
    """
    width, height = _SIZE
    page = Image.new("RGB", _SIZE, _PAPER)
    draw = ImageDraw.Draw(page)

    # Frame and header band.
    draw.rectangle((24, 24, width - 25, height - 25), outline=_ACCENT, width=4)
    draw.rectangle((24, 24, width - 25, 150), fill=_ACCENT)
    draw.rounded_rectangle((56, 50, 156, 124), radius=14, outline=_PAPER, width=4)
    draw.text((106, 87), "BH", font=_font(44), fill=_PAPER, anchor="mm")
    draw.text((186, 58), PROVIDER_NAME, font=_font(40), fill=_PAPER)
    draw.text(
        (186, 106),
        "Musterweg 1 · 12345 Beispielstadt · kurse@beispiel-hilfsdienst.example",
        font=_font(22),
        fill=_PAPER,
    )

    draw.text((width // 2, 210), TITLE, font=_font(42), fill=_INK, anchor="mm")

    body = _font(28)
    y = 290
    draw.text((80, y), "Hiermit wird bescheinigt, dass", font=body, fill=_INK)
    draw.text(
        (width // 2, y + 80), _plain(holder), font=_font(54), fill=_INK, anchor="mm"
    )
    draw.line((260, y + 120, width - 260, y + 120), fill=_MUTED, width=2)
    draw.text(
        (80, y + 150),
        f"am {_german_date(course_date)} an einem Erste-Hilfe-Kurs "
        "(9 Unterrichtseinheiten) teilgenommen hat.",
        font=body,
        fill=_INK,
    )
    draw.text(
        (80, y + 200),
        f"This certifies that the person above attended a first-aid course "
        f"(9 units) on {course_date.isoformat()}.",
        font=_font(22),
        fill=_MUTED,
    )

    # Signature block, with a squiggle instead of anyone's signature.
    sig_y = y + 330
    points = [
        (110 + i * 6, sig_y - 18 + int(14 * math.sin(i / 2.2))) for i in range(40)
    ]
    draw.line(points, fill=_INK, width=3)
    draw.line((90, sig_y, 440, sig_y), fill=_MUTED, width=2)
    draw.text((90, sig_y + 10), "Kursleitung: M. Muster", font=_font(22), fill=_MUTED)
    draw.text(
        (width - 90, sig_y + 10),
        f"Beispielstadt, {_german_date(course_date)}",
        font=_font(22),
        fill=_MUTED,
        anchor="ra",
    )

    draw.text(
        (width // 2, height - 58),
        "Demo-Dokument aus WirkSam · kein gueltiger Nachweis · "
        "Demo document, not a valid certificate",
        font=_font(20),
        fill=_MUTED,
        anchor="mm",
    )

    # The watermark, drawn on its own layer, turned and laid over everything.
    mark = Image.new("RGBA", _SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(mark).text(
        (width // 2, height // 2),
        "MUSTER",
        font=_font(260),
        fill=_WATERMARK,
        anchor="mm",
        stroke_width=4,
        stroke_fill=_WATERMARK,
    )
    mark = mark.rotate(
        math.degrees(math.atan2(height, width)), resample=Image.Resampling.BICUBIC
    )
    page = Image.alpha_composite(page.convert("RGBA"), mark).convert("RGB")

    out = io.BytesIO()
    page.save(out, format="PNG", optimize=True)
    return out.getvalue()
