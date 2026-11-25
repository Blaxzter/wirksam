import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.storage import drain_after_commit, get_storage, new_key
from app.logic.images import NormalizedImage
from app.models.event import Event
from app.models.event_logo import LOGO_VARIANTS, EventLogo, LogoVariant


def _mirror(
    event: Event,
    variant: LogoVariant,
    etag: str | None,
    width: int | None,
    height: int | None,
) -> None:
    """Set the ``events`` columns that mirror one variant's row."""
    if variant == "light":
        event.logo_etag = etag
        event.logo_width, event.logo_height = width, height
    else:
        event.logo_dark_etag = etag
        event.logo_dark_width, event.logo_dark_height = width, height


def _size(event: Event, variant: LogoVariant) -> tuple[int | None, int | None]:
    if variant == "light":
        return event.logo_width, event.logo_height
    return event.logo_dark_width, event.logo_dark_height


class CRUDEventLogo:
    """An event's logo rows and the ``events.logo_*`` / ``events.logo_dark_*``
    columns that mirror them, which must move together."""

    async def get_by_event(
        self,
        db: AsyncSession,
        *,
        event_id: uuid.UUID,
        variant: LogoVariant = "light",
    ) -> EventLogo | None:
        result = await db.execute(
            select(EventLogo).where(
                col(EventLogo.event_id) == event_id,
                col(EventLogo.variant) == variant,
            )
        )
        return result.scalars().first()

    async def upsert(
        self,
        db: AsyncSession,
        *,
        event: Event,
        image: NormalizedImage,
        variant: LogoVariant = "light",
    ) -> EventLogo:
        """Store ``image`` as the event's logo of this variant.

        Always under a new key: replacing a logo queues the old file for
        deletion (a trigger on the table, see ``app.logic.storage_gc``).
        """
        content_type, etag = image.content_type, image.etag
        storage_key = new_key("event-logos")
        await get_storage().put(db, storage_key, image.data, content_type)
        existing = await self.get_by_event(db, event_id=event.id, variant=variant)
        if existing:
            existing.storage_key = storage_key
            drain_after_commit(db)
            existing.content_type = content_type
            existing.etag = etag
            db.add(existing)
            logo = existing
        else:
            logo = EventLogo(
                event_id=event.id,
                variant=variant,
                storage_key=storage_key,
                content_type=content_type,
                etag=etag,
            )
            db.add(logo)
        _mirror(event, variant, etag, image.width, image.height)
        db.add(event)
        await db.flush()
        return logo

    async def delete_for_event(
        self, db: AsyncSession, *, event: Event, variant: LogoVariant = "light"
    ) -> bool:
        existing = await self.get_by_event(db, event_id=event.id, variant=variant)
        _mirror(event, variant, None, None, None)
        db.add(event)
        if existing:
            await db.delete(existing)
        await db.flush()
        if not existing:
            return False
        drain_after_commit(db)
        return True

    async def copy_for_clone(
        self, db: AsyncSession, *, source: Event, target: Event
    ) -> int:
        """Give ``target`` its own copy of each of ``source``'s logos.

        A copy, not a shared key: each row owns its file, and deleting one
        event's logo must not take the other's with it. Answers how many
        came across.
        """
        copied = 0
        for variant in LOGO_VARIANTS:
            logo = await self.get_by_event(db, event_id=source.id, variant=variant)
            if logo is None:
                continue
            storage_key = new_key("event-logos")
            if not await get_storage().copy(db, logo.storage_key, storage_key):
                continue
            db.add(
                EventLogo(
                    event_id=target.id,
                    variant=variant,
                    storage_key=storage_key,
                    content_type=logo.content_type,
                    etag=logo.etag,
                )
            )
            _mirror(target, variant, logo.etag, *_size(source, variant))
            copied += 1
        if copied:
            db.add(target)
            await db.flush()
        return copied


event_logo = CRUDEventLogo()
