"""Venue plan templates: drawings an organiser saved to reuse across events.

A template belongs to the *user* who saved it, not to an event, so neither
permission gate in ``logic/permissions.py`` applies: the only rule is "it is
yours". Anyone else, the superadmin included, gets a 404 on its id, so a
template cannot be probed.

Saving one (``POST /venue-plans/{id}/save-as-template``) and starting a plan
from one (``POST /events/{id}/venue-plans`` with ``template_id``) live in
``venue_map.py``, next to the plan routes whose event gate they share.
"""

import uuid

from fastapi import APIRouter, Request, Response, status

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.venue_template import venue_template as crud_venue_template
from app.models.user import User
from app.models.venue_template import VenueTemplate
from app.schemas.venue_template import (
    TEMPLATE_NOT_FOUND,
    VenueTemplateRead,
    VenueTemplateSummary,
    VenueTemplateUpdate,
)

router = APIRouter(tags=["venue-templates"])

# The image URL carries ``?v=<etag>`` and a template's picture never changes.
_IMAGE_CACHE_CONTROL = "private, max-age=604800"


async def load_own_template(
    session: DBDep, user: User, template_id: uuid.UUID
) -> VenueTemplate:
    """The caller's template, or 404 ``venue_template.not_found``.

    Someone else's template is a 404 too, never a 403.
    """
    template = await crud_venue_template.get(session, template_id=template_id)
    if template is None or template.user_id != user.id:
        raise_problem(404, code=TEMPLATE_NOT_FOUND, detail="Venue template not found")
    return template


@router.get("/venue-templates", response_model=list[VenueTemplateSummary])
async def list_venue_templates(
    session: DBDep, current_user: CurrentUser
) -> list[VenueTemplateSummary]:
    """The caller's templates, newest first, without their drawings."""
    return await crud_venue_template.list_for_user(session, user_id=current_user.id)


@router.get("/venue-templates/{template_id}", response_model=VenueTemplateRead)
async def get_venue_template(
    template_id: uuid.UUID, session: DBDep, current_user: CurrentUser
) -> VenueTemplateRead:
    """One of the caller's templates with its drawing, for a preview."""
    template = await load_own_template(session, current_user, template_id)
    return crud_venue_template.read(template)


@router.patch("/venue-templates/{template_id}", response_model=VenueTemplateRead)
async def update_venue_template(
    template_id: uuid.UUID,
    body: VenueTemplateUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> VenueTemplateRead:
    """Rename a template. Its drawing cannot be edited; save a new one instead."""
    template = await load_own_template(session, current_user, template_id)
    if body.name is not None:
        template = await crud_venue_template.rename(
            session, template=template, name=body.name
        )
    return crud_venue_template.read(template)


@router.delete("/venue-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_venue_template(
    template_id: uuid.UUID, session: DBDep, current_user: CurrentUser
) -> None:
    """Delete a template. Plans made from it keep their copy of the drawing."""
    template = await load_own_template(session, current_user, template_id)
    await crud_venue_template.delete(session, template=template)


@router.get(
    "/venue-templates/{template_id}/image",
    response_class=Response,
    responses={
        200: {"content": {"image/webp": {}}, "description": "The template image"},
        304: {"description": "Not modified"},
    },
)
async def get_venue_template_image(
    template_id: uuid.UUID,
    request: Request,
    session: DBDep,
    current_user: CurrentUser,
) -> Response:
    """Serve a template's picture to its owner."""
    template = await load_own_template(session, current_user, template_id)
    image = await crud_venue_template.get_image(session, template_id=template.id)
    if image is None:
        raise_problem(
            404,
            code="venue_template.image_not_found",
            detail="This template has no image",
        )

    etag_header = f'"{image.etag}"'
    headers = {"ETag": etag_header, "Cache-Control": _IMAGE_CACHE_CONTROL}
    if request.headers.get("if-none-match") == etag_header:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=image.data, media_type=image.content_type, headers=headers)
