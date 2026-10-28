"""Answering a request for a stored file: a redirect to the bucket, or the bytes."""

from collections.abc import Mapping

from fastapi import Response
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import StoredFile, get_storage

# How long a signed link works. The redirect to it is cached half as long, so
# a browser that replays a cached redirect still lands on a live link, and
# within that window keeps landing on the same one, which it has cached too.
LINK_TTL_SECONDS = 2 * 60 * 60


def file_response(
    opened: StoredFile, *, media_type: str, headers: Mapping[str, str]
) -> StreamingResponse:
    """Stream ``opened`` to the client, with its length when the store knows it."""
    all_headers = dict(headers)
    if opened.size is not None:
        all_headers["Content-Length"] = str(opened.size)
    return StreamingResponse(opened.chunks, media_type=media_type, headers=all_headers)


async def serve_file(
    db: AsyncSession,
    key: str,
    *,
    media_type: str,
    headers: Mapping[str, str],
    link: bool = True,
) -> Response | None:
    """Send the browser to the file in the bucket, or stream it; None if missing.

    Call it after the access check. With ``link`` and a store that signs
    links (S3), the answer is a redirect to a link that works for
    ``LINK_TTL_SECONDS`` and makes the bucket answer with these headers'
    ``Cache-Control``; the bytes never pass through the API. The redirect
    carries no ETag: revalidating it would keep a link alive past its expiry.
    """
    storage = get_storage()
    cache_control = headers.get("Cache-Control", "private, no-store")
    if link:
        url = await storage.link(
            db, key, expires_in=LINK_TTL_SECONDS, cache_control=cache_control
        )
        if url is not None:
            scope = "public" if cache_control.startswith("public") else "private"
            return RedirectResponse(
                url,
                status_code=302,
                headers={"Cache-Control": f"{scope}, max-age={LINK_TTL_SECONDS // 2}"},
            )
    opened = await storage.open(db, key)
    if opened is None:
        return None
    return file_response(opened, media_type=media_type, headers=headers)
