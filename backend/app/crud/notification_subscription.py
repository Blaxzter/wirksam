import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.notification import NotificationSubscription, NotificationType
from app.schemas.notification import (
    NotificationSubscriptionCreate,
    NotificationSubscriptionUpdate,
)


class CRUDNotificationSubscription(
    CRUDBase[
        NotificationSubscription,
        NotificationSubscriptionCreate,
        NotificationSubscriptionUpdate,
    ]
):
    async def get_user_preferences(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> Sequence[NotificationSubscription]:
        query = (
            select(NotificationSubscription)
            .where(col(NotificationSubscription.user_id) == user_id)
            .options(selectinload(NotificationSubscription.notification_type))  # type: ignore[arg-type]
            .order_by(col(NotificationSubscription.created_at))
        )
        result = await db.execute(query)
        return result.scalars().all()

    async def resolve_channels(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        type_code: str,
        scope_chain: list[tuple[str, uuid.UUID]] | None = None,
    ) -> dict[str, bool] | None:
        """Resolve which channels are enabled for a user + notification type.

        Walks the scope chain from most specific to least specific.
        Returns dict like {"email": True, "push": False, "telegram": True}
        or None if the notification is muted at the resolved scope level.

        If no subscription is found, returns None (caller should use defaults).
        """
        # Get the notification type ID
        type_query = select(NotificationType).where(
            col(NotificationType.code) == type_code
        )
        type_result = await db.execute(type_query)
        notif_type = type_result.scalar_one_or_none()
        if not notif_type:
            return None

        # Build scope levels to check: specific → global
        scope_levels: list[tuple[str, uuid.UUID | None]] = []
        if scope_chain:
            for scope_type, scope_id in scope_chain:
                scope_levels.append((scope_type, scope_id))
        scope_levels.append(("global", None))

        # Check each scope level
        for scope_type, scope_id in scope_levels:
            query = select(NotificationSubscription).where(
                col(NotificationSubscription.user_id) == user_id,
                col(NotificationSubscription.notification_type_id) == notif_type.id,
                col(NotificationSubscription.scope_type) == scope_type,
            )
            if scope_id is not None:
                query = query.where(col(NotificationSubscription.scope_id) == scope_id)
            else:
                query = query.where(col(NotificationSubscription.scope_id).is_(None))

            result = await db.execute(query)
            sub = result.scalar_one_or_none()

            if sub is not None:
                if sub.is_muted:
                    return None  # Explicitly muted
                return {
                    "email": sub.email_enabled,
                    "push": sub.push_enabled,
                    "telegram": sub.telegram_enabled,
                }

        # No subscription found — return default channels from the type
        defaults = {
            "email": "email" in notif_type.default_channels,
            "push": "push" in notif_type.default_channels,
            "telegram": "telegram" in notif_type.default_channels,
        }
        return defaults

    async def bulk_upsert(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        preferences: list[NotificationSubscriptionCreate],
    ) -> list[NotificationSubscription]:
        """Upsert a list of subscription preferences for a user."""
        results: list[NotificationSubscription] = []
        for pref in preferences:
            # Find existing
            query = select(NotificationSubscription).where(
                col(NotificationSubscription.user_id) == user_id,
                col(NotificationSubscription.notification_type_id) == pref.notification_type_id,
                col(NotificationSubscription.scope_type) == pref.scope_type,
            )
            if pref.scope_id is not None:
                query = query.where(
                    col(NotificationSubscription.scope_id) == pref.scope_id
                )
            else:
                query = query.where(
                    col(NotificationSubscription.scope_id).is_(None)
                )

            result = await db.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                existing.email_enabled = pref.email_enabled
                existing.push_enabled = pref.push_enabled
                existing.telegram_enabled = pref.telegram_enabled
                existing.is_muted = pref.is_muted
                db.add(existing)
                results.append(existing)
            else:
                new_sub = NotificationSubscription(
                    user_id=user_id,
                    notification_type_id=pref.notification_type_id,
                    email_enabled=pref.email_enabled,
                    push_enabled=pref.push_enabled,
                    telegram_enabled=pref.telegram_enabled,
                    scope_type=pref.scope_type,
                    scope_id=pref.scope_id,
                    is_muted=pref.is_muted,
                )
                db.add(new_sub)
                results.append(new_sub)

        await db.flush()
        for r in results:
            await db.refresh(r)
        return results


notification_subscription = CRUDNotificationSubscription(NotificationSubscription)
