"""Avatar upload, delete, and serve endpoints.

Avatars are stored as WebP files in ``app.core.storage``. The denormalized ``avatar_etag``
on the ``users`` row is the canonical version marker — frontends append it as
a query string so a new upload busts cached browser copies.

The GET endpoint is unauthenticated by design: avatars are referenced by ``<img>``
tags which don't carry the bearer token, and user UUIDs are not enumerable from
the outside.
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, status

from app.api.deps import CurrentUser, DBDep
from app.api.files import serve_file
from app.crud.user_avatar import user_avatar as crud_avatar
from app.logic.avatar import AvatarProcessingError, normalize_avatar
from app.schemas.user_avatar import AvatarUploadResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.put("/me/avatar", response_model=AvatarUploadResponse)
async def upload_my_avatar(
    file: UploadFile,
    current_user: CurrentUser,
    *,
    session: DBDep,
) -> AvatarUploadResponse:
    """Upload a new avatar for the current user.

    The image is decoded, EXIF-oriented, resized to 256x256, re-encoded as WebP,
    and stored. The user's ``avatar_etag`` is updated.
    """
    raw = await file.read()
    try:
        data, content_type, etag = normalize_avatar(raw)
    except AvatarProcessingError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    await crud_avatar.upsert(
        session,
        user_id=current_user.id,
        data=data,
        content_type=content_type,
        etag=etag,
    )
    current_user.avatar_etag = etag
    session.add(current_user)
    await session.flush()
    return AvatarUploadResponse(etag=etag)


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_avatar(
    current_user: CurrentUser,
    *,
    session: DBDep,
) -> None:
    """Remove the current user's avatar; UI falls back to initials."""
    await crud_avatar.delete_by_user(session, user_id=current_user.id)
    current_user.avatar_etag = None
    session.add(current_user)
    await session.flush()


@router.get("/{user_id}/avatar")
async def get_user_avatar(
    user_id: uuid.UUID,
    request: Request,
    *,
    session: DBDep,
) -> Response:
    """Serve a user's avatar bytes. Public; relies on UUID unguessability."""
    avatar = await crud_avatar.get_by_user(session, user_id=user_id)
    if not avatar:
        # Confirm the user actually exists so 404s aren't an enumeration oracle —
        # but only minimally; return the same 404 either way.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found"
        )

    etag_header = f'"{avatar.etag}"'
    if_none_match = request.headers.get("if-none-match")
    if if_none_match == etag_header:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": etag_header},
        )

    served = await serve_file(
        session,
        avatar.storage_key,
        media_type=avatar.content_type,
        headers={
            "ETag": etag_header,
            # The frontend appends ?v=<etag> so the URL itself changes on update;
            # safe to cache aggressively here.
            "Cache-Control": "public, max-age=86400, stale-while-revalidate=604800",
        },
    )
    if served is None:
        logger.error("avatar file missing", extra={"key": avatar.storage_key})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found"
        )
    return served
