"""An event's logos: upload, remove, serve.

Stored like avatars (``app.core.storage``, WebP), with ``events.logo_etag`` as
the version marker that clients append to the URL. ``/logo/dark`` is the same
for an optional second logo that dark mode shows instead, with
``events.logo_dark_etag``.

The GET is unauthenticated, like the avatar one: the logo appears in ``<img>``
tags, which carry no bearer token, and on the invitation page, whose visitor
is not a member yet. An event id is a random UUID that only members, invitees
and (for a public event) Discover ever see, and a logo is meant to be shown.
"""

import logging
import uuid

from fastapi import APIRouter, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import CurrentUser, DBDep
from app.api.files import serve_file
from app.api.routes.events import decorate_event
from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.crud.event_logo import event_logo as crud_event_logo
from app.logic.event_logo import normalize_event_logo
from app.logic.images import MAX_INPUT_BYTES, ImageProcessingError
from app.logic.permissions import require_event_role
from app.models.event_logo import LogoVariant
from app.schemas.event import EventRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


async def _upload(
    event_id: uuid.UUID,
    file: UploadFile,
    session: DBDep,
    current_user: CurrentUser,
    variant: LogoVariant,
) -> EventRead:
    event = await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event.id, minimum="admin")
    if event.is_sandbox or current_user.is_sandbox:
        raise_problem(
            403,
            code="sandbox.upload_disabled",
            detail="Images cannot be uploaded in a demo event",
        )
    if variant == "dark" and event.logo_etag is None:
        raise_problem(
            409,
            code="event.logo_required",
            detail="Upload the logo before a version of it for dark mode",
        )
    if file.size is not None and file.size > MAX_INPUT_BYTES:
        raise_problem(
            400, code="event.invalid_logo", detail="Image exceeds 20 MB upload limit"
        )
    raw = await file.read()
    try:
        # Decoding is CPU-bound; keep it off the event loop.
        image = await run_in_threadpool(normalize_event_logo, raw)
    except ImageProcessingError as exc:
        raise_problem(400, code="event.invalid_logo", detail=str(exc))
    await crud_event_logo.upsert(session, event=event, image=image, variant=variant)
    return await decorate_event(session, current_user, event)


async def _delete(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    variant: LogoVariant,
) -> EventRead:
    event = await crud_event.get(session, event_id, raise_404_error=True)
    await require_event_role(current_user, session, event.id, minimum="admin")
    await crud_event_logo.delete_for_event(session, event=event, variant=variant)
    if variant == "light":
        # The dark one is a version of the logo, never shown without it.
        await crud_event_logo.delete_for_event(session, event=event, variant="dark")
    return await decorate_event(session, current_user, event)


async def _serve(
    event_id: uuid.UUID,
    request: Request,
    session: DBDep,
    variant: LogoVariant,
) -> Response:
    logo = await crud_event_logo.get_by_event(
        session, event_id=event_id, variant=variant
    )
    if logo is None:
        raise_problem(404, code="event.logo_not_found", detail="Logo not found")

    etag_header = f'"{logo.etag}"'
    if request.headers.get("if-none-match") == etag_header:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag_header}
        )

    served = await serve_file(
        session,
        logo.storage_key,
        media_type=logo.content_type,
        headers={
            "ETag": etag_header,
            # The client appends ?v=<etag>, so a new logo is a new URL.
            "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
        },
    )
    if served is None:
        logger.error("event logo file missing", extra={"key": logo.storage_key})
        raise_problem(404, code="event.logo_not_found", detail="Logo not found")
    return served


@router.put("/{event_id}/logo", response_model=EventRead)
async def upload_event_logo(
    event_id: uuid.UUID,
    file: UploadFile,
    session: DBDep,
    current_user: CurrentUser,
) -> EventRead:
    """Set the event's logo (event admins).

    PNG, JPEG, WebP or GIF; it is re-encoded as WebP to fit 512x512, keeping
    its proportions and any transparency. Refused in a demo event and for a
    demo guest, like every other image upload: an anonymous visitor storing
    arbitrary images is not something a demo needs. The colours stay open.
    """
    return await _upload(event_id, file, session, current_user, "light")


@router.delete("/{event_id}/logo", response_model=EventRead)
async def delete_event_logo(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> EventRead:
    """Remove the event's logo (event admins), and with it the version for
    dark mode, which is never shown on its own. Removing none is not an error.
    """
    return await _delete(event_id, session, current_user, "light")


@router.get("/{event_id}/logo")
async def get_event_logo(
    event_id: uuid.UUID,
    request: Request,
    session: DBDep,
) -> Response:
    """The logo's bytes. Public; relies on the event id being unguessable."""
    return await _serve(event_id, request, session, "light")


@router.put("/{event_id}/logo/dark", response_model=EventRead)
async def upload_event_logo_dark(
    event_id: uuid.UUID,
    file: UploadFile,
    session: DBDep,
    current_user: CurrentUser,
) -> EventRead:
    """Set the logo dark mode shows instead (event admins), such as the same
    mark with white lettering. Same formats and rules as the logo, which has
    to be there first (409 ``event.logo_required``)."""
    return await _upload(event_id, file, session, current_user, "dark")


@router.delete("/{event_id}/logo/dark", response_model=EventRead)
async def delete_event_logo_dark(
    event_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> EventRead:
    """Remove the logo for dark mode (event admins); dark mode then shows the
    logo. Removing none is not an error."""
    return await _delete(event_id, session, current_user, "dark")


@router.get("/{event_id}/logo/dark")
async def get_event_logo_dark(
    event_id: uuid.UUID,
    request: Request,
    session: DBDep,
) -> Response:
    """The dark-mode logo's bytes. Public, like the logo."""
    return await _serve(event_id, request, session, "dark")
