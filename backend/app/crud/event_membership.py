import uuid
from typing import cast

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.event_membership import EventMembership
from app.models.user import User
from app.schemas.event_membership import EventRole


class CRUDEventMembership:
    async def get(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> EventMembership | None:
        result = await session.execute(
            select(EventMembership).where(
                col(EventMembership.user_id) == user_id,
                col(EventMembership.event_id) == event_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_role(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> EventRole | None:
        result = await session.execute(
            select(col(EventMembership.role)).where(
                col(EventMembership.user_id) == user_id,
                col(EventMembership.event_id) == event_id,
            )
        )
        role = result.scalar_one_or_none()
        return role  # type: ignore[return-value]

    async def get_roles_for_user(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
    ) -> dict[uuid.UUID, EventRole]:
        """Every event this user belongs to, mapped to their role.

        Loaded once per profile request so the frontend can decide what to
        render without a round trip per event.
        """
        result = await session.execute(
            select(col(EventMembership.event_id), col(EventMembership.role)).where(
                col(EventMembership.user_id) == user_id
            )
        )
        return {row[0]: cast(EventRole, row[1]) for row in result.all()}

    async def list_event_ids_for_user(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        minimum_role: EventRole | None = None,
    ) -> list[uuid.UUID]:
        query = select(col(EventMembership.event_id)).where(
            col(EventMembership.user_id) == user_id
        )
        if minimum_role == "admin":
            query = query.where(col(EventMembership.role).in_(["owner", "admin"]))
        elif minimum_role == "owner":
            query = query.where(col(EventMembership.role) == "owner")
        result = await session.execute(query)
        return list(result.scalars().all())

    async def list_members(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
    ) -> list[tuple[EventMembership, User]]:
        """Members of an event with their user rows, strongest role first."""
        result = await session.execute(
            select(EventMembership, User)
            .join(User, col(User.id) == col(EventMembership.user_id))
            .where(col(EventMembership.event_id) == event_id)
            .order_by(
                # owner → admin → member, then alphabetical within a role.
                col(EventMembership.role) == "member",
                col(EventMembership.role) == "admin",
                col(User.name).asc(),
            )
        )
        return [(m, u) for m, u in result.all()]

    async def list_user_ids(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        minimum_role: EventRole | None = None,
    ) -> list[uuid.UUID]:
        query = select(col(EventMembership.user_id)).where(
            col(EventMembership.event_id) == event_id
        )
        if minimum_role == "admin":
            query = query.where(col(EventMembership.role).in_(["owner", "admin"]))
        elif minimum_role == "owner":
            query = query.where(col(EventMembership.role) == "owner")
        result = await session.execute(query)
        return list(result.scalars().all())

    async def count_by_event(
        self,
        session: AsyncSession,
        *,
        event_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, int]:
        """Member counts for many events at once (avoids N+1 in list views)."""
        if not event_ids:
            return {}
        result = await session.execute(
            select(col(EventMembership.event_id), func.count())
            .where(col(EventMembership.event_id).in_(event_ids))
            .group_by(col(EventMembership.event_id))
        )
        return {row[0]: row[1] for row in result.all()}

    async def upsert(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        event_id: uuid.UUID,
        role: EventRole,
    ) -> EventMembership:
        obj = await self.get(session, user_id=user_id, event_id=event_id)
        if obj:
            if obj.role != role:
                obj.role = role
                session.add(obj)
                await session.flush()
            return obj
        obj = EventMembership(user_id=user_id, event_id=event_id, role=role)
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj

    async def remove(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        event_id: uuid.UUID,
    ) -> bool:
        result = await session.execute(
            delete(EventMembership).where(
                col(EventMembership.user_id) == user_id,
                col(EventMembership.event_id) == event_id,
            )
        )
        return result.rowcount > 0  # type: ignore[return-value]

    async def count_owners(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
    ) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(EventMembership)
            .where(
                col(EventMembership.event_id) == event_id,
                col(EventMembership.role) == "owner",
            )
        )
        return result.scalar_one()


event_membership = CRUDEventMembership()
