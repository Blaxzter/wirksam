import uuid
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import QueryableAttribute, defer
from sqlmodel import col

from app.core.storage import drain_after_commit
from app.crud.venue_map import copy_image, drawing_fields
from app.crud.venue_map import venue_map as crud_venue_map
from app.models.user import User
from app.models.venue_plan import VenuePlan, VenuePlanImage, VenueShape
from app.models.venue_template import VenueTemplate, VenueTemplateImage
from app.schemas.venue_template import (
    VenueTemplateRead,
    VenueTemplateShape,
    VenueTemplateSummary,
    template_shapes_adapter,
)


def _now() -> datetime:
    """Naive UTC, matching how every other timestamp in the app is stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CRUDVenueTemplate:
    """A user's venue templates and their image bytes.

    Saving a plan as a template and starting a plan from one both *copy*: the
    picture inside the database, the drawing as fresh rows (or a fresh
    snapshot). Markers and location links never travel; they belong to one
    event. Never commits; the request owns the transaction.
    """

    async def get(
        self, session: AsyncSession, *, template_id: uuid.UUID
    ) -> VenueTemplate | None:
        return await session.get(VenueTemplate, template_id)

    async def count_for_user(self, session: AsyncSession, *, user_id: uuid.UUID) -> int:
        count = await session.scalar(
            select(func.count())
            .select_from(VenueTemplate)
            .where(col(VenueTemplate.user_id) == user_id)
        )
        return int(count or 0)

    async def lock_owner(self, session: AsyncSession, *, user_id: uuid.UUID) -> None:
        """Serialise template creation per user (``SELECT ... FOR UPDATE``).

        Two parallel saves would otherwise both pass the count check and push
        an account past the cap.
        """
        await session.execute(
            select(col(User.id)).where(col(User.id) == user_id).with_for_update()
        )

    async def list_for_user(
        self, session: AsyncSession, *, user_id: uuid.UUID
    ) -> list[VenueTemplateSummary]:
        """The user's templates, newest first, without loading their drawings."""
        result = await session.execute(
            select(VenueTemplate, func.jsonb_array_length(col(VenueTemplate.shapes)))
            .options(defer(cast(QueryableAttribute[Any], VenueTemplate.shapes)))
            .where(col(VenueTemplate.user_id) == user_id)
            .order_by(col(VenueTemplate.created_at).desc(), col(VenueTemplate.id))
        )
        return [
            VenueTemplateSummary.model_validate(template).model_copy(
                update={"shape_count": int(shape_count)}
            )
            for template, shape_count in result.all()
        ]

    def shapes_of(self, template: VenueTemplate) -> list[VenueTemplateShape]:
        """The template's drawing, validated, in drawing order."""
        shapes = template_shapes_adapter.validate_python(template.shapes)
        return sorted(shapes, key=lambda s: s.sort_order)

    def read(self, template: VenueTemplate) -> VenueTemplateRead:
        """The template with its drawing; validating it checks every shape."""
        read = VenueTemplateRead.model_validate(template)
        shapes = sorted(read.shapes, key=lambda s: s.sort_order)
        return read.model_copy(update={"shapes": shapes, "shape_count": len(shapes)})

    async def create_from_plan(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        plan: VenuePlan,
        name: str,
    ) -> VenueTemplate:
        """Save a copy of ``plan``'s drawing (canvas, picture, shapes) for ``user_id``.

        Markers are left behind and every shape loses its location link.
        """
        now = _now()
        shapes = await crud_venue_map.list_shapes_for_plans(session, plan_ids=[plan.id])
        snapshot = [
            VenueTemplateShape.model_validate(
                {"id": uuid.uuid4(), **drawing_fields(shape)}
            ).model_dump(mode="json")
            for shape in shapes
        ]
        template = VenueTemplate(
            created_at=now,
            updated_at=now,
            user_id=user_id,
            name=name,
            canvas_width=plan.canvas_width,
            canvas_height=plan.canvas_height,
            shapes=snapshot,
        )
        session.add(template)
        await session.flush()

        copied = await copy_image(
            session,
            source=VenuePlanImage,
            source_key="plan_id",
            source_id=plan.id,
            target=VenueTemplateImage,
            target_key="template_id",
            target_id=template.id,
            kind="venue-templates",
            now=now,
        )
        if copied:
            template.image_etag = plan.image_etag
            template.image_width = plan.image_width
            template.image_height = plan.image_height
            session.add(template)
            await session.flush()
        await session.refresh(template)
        return template

    async def create_plan(
        self,
        session: AsyncSession,
        *,
        template: VenueTemplate,
        event_id: uuid.UUID,
        name: str,
    ) -> VenuePlan:
        """Append a new plan to ``event_id`` with a copy of ``template``'s drawing.

        The plan has no markers; the organiser places them afterwards.
        """
        now = _now()
        shapes = self.shapes_of(template)
        plan = VenuePlan(
            created_at=now,
            updated_at=now,
            event_id=event_id,
            name=name,
            sort_order=await crud_venue_map.next_sort_order(session, event_id=event_id),
            canvas_width=template.canvas_width,
            canvas_height=template.canvas_height,
            # 0 tells clients there is nothing drawn to fetch.
            shapes_revision=1 if shapes else 0,
        )
        session.add(plan)
        await session.flush()

        copied = await copy_image(
            session,
            source=VenueTemplateImage,
            source_key="template_id",
            source_id=template.id,
            target=VenuePlanImage,
            target_key="plan_id",
            target_id=plan.id,
            kind="venue-plans",
            now=now,
        )
        if copied:
            plan.image_etag = template.image_etag
            plan.image_width = template.image_width
            plan.image_height = template.image_height
            session.add(plan)

        for shape in shapes:
            session.add(
                VenueShape(
                    created_at=now,
                    updated_at=now,
                    plan_id=plan.id,
                    **shape.model_dump(exclude={"id"}),
                )
            )
        await session.flush()
        await session.refresh(plan)
        return plan

    async def rename(
        self, session: AsyncSession, *, template: VenueTemplate, name: str
    ) -> VenueTemplate:
        template.name = name
        template.updated_at = _now()
        session.add(template)
        await session.flush()
        await session.refresh(template)
        return template

    async def delete(self, session: AsyncSession, *, template: VenueTemplate) -> None:
        """Delete a template; its image row goes with it (DB cascade), and the
        file with the row (the image table's trigger)."""
        await session.delete(template)
        await session.flush()
        drain_after_commit(session)

    async def get_image(
        self, session: AsyncSession, *, template_id: uuid.UUID
    ) -> VenueTemplateImage | None:
        result = await session.execute(
            select(VenueTemplateImage).where(
                col(VenueTemplateImage.template_id) == template_id
            )
        )
        return result.scalars().first()


venue_template = CRUDVenueTemplate()
