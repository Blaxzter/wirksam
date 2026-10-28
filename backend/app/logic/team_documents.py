"""Files a requester attaches to a team request (a first-aid card, say).

Stored like avatars (``app.core.storage``: Postgres, or a private S3 bucket)
and deliberately short-lived: the row is deleted once the request is decided,
and its file with it (see ``app.logic.storage_gc``).
Only PDF and the three common photo formats are accepted, recognised by their
first bytes rather than by what the browser claims. Photos are re-encoded
(which also drops their EXIF data, GPS position included); a PDF is kept as
sent. Either way the bytes are served with their checked type and
``nosniff``, so a browser never reads them as anything else.
"""

import re
import unicodedata
from pathlib import PurePath
from typing import Final, NamedTuple
from urllib.parse import quote

from app.logic.images import ImageProcessingError, normalize_image

#: The upload limit, for the raw file as sent.
MAX_DOCUMENT_BYTES: Final = 5 * 1024 * 1024
#: Photos of a document are shrunk to fit this box; still easily readable.
_MAX_DIM: Final = 2400
_QUALITIES: Final = (85, 75, 60)


class DocumentError(ValueError):
    """An upload the API refuses; ``code`` is the problem code to answer with."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class PreparedDocument(NamedTuple):
    data: bytes
    content_type: str
    filename: str


def sniff(raw: bytes) -> str | None:
    """``pdf``, ``png``, ``jpeg`` or ``webp`` from the file's magic bytes."""
    if raw.startswith(b"%PDF-"):
        return "pdf"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    return None


def safe_filename(name: str | None, *, suffix: str) -> str:
    """A display name without path parts or control characters, ending ``suffix``."""
    stem = PurePath((name or "").replace("\\", "/")).stem
    stem = unicodedata.normalize("NFC", stem)
    stem = re.sub(r"[\x00-\x1f\x7f\"]", "", stem).strip(" .")[:120]
    return f"{stem or 'document'}{suffix}"


def prepare_document(raw: bytes, filename: str | None) -> PreparedDocument:
    """Check an upload and turn it into what gets stored. CPU-bound for photos."""
    if not raw:
        raise DocumentError("team.document_unsupported", "The file is empty")
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise DocumentError("team.document_too_large", "The file is larger than 5 MB")
    kind = sniff(raw)
    if kind is None:
        raise DocumentError(
            "team.document_unsupported",
            "Only PDF, PNG, JPEG and WebP files can be attached",
        )
    if kind == "pdf":
        return PreparedDocument(
            raw, "application/pdf", safe_filename(filename, suffix=".pdf")
        )
    try:
        image = normalize_image(
            raw,
            max_dim=_MAX_DIM,
            max_output_bytes=MAX_DOCUMENT_BYTES,
            qualities=_QUALITIES,
        )
    except ImageProcessingError as exc:
        raise DocumentError("team.document_unsupported", str(exc)) from exc
    return PreparedDocument(
        image.data, image.content_type, safe_filename(filename, suffix=".webp")
    )


def content_disposition(filename: str) -> str:
    """``inline`` with an ASCII fallback and the UTF-8 name (RFC 6266)."""
    ascii_name = (
        unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode()
        or "document"
    )
    return f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
