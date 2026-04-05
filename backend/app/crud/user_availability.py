import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col

from app.crud.base import CRUDBase
from app.models.user_availability import UserAvailability, UserAvailabilityDate
from app.schemas.user_availability import (
    UserAvailabilityCreate,
    UserAvailabilityDateInput,
    UserAvailabilityUpdate,
)


class CRUDUserAvailability(
    CRUDBase[UserAvailability, UserAvailabilityCreate, UserAvailabilityUpdate]
):
    async def get_by_user_and_group(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        event_group_id: uuid.UUID,
    ) -> UserAvailability | None:
        query = (
            select(UserAvailability)
            .where(
                col(UserAvailability.user_id) == user_id,
                col(UserAvailability.event_group_id) == event_group_id,
            )
            .options(selectinload(UserAvailability.available_dates))  # type: ignore[arg-type]
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_multi_by_group(
        self,
        db: AsyncSession,
        *,
        event_group_id: uuid.UUID,
        skip: int = 0,
        limit: int = 200,
    ) -> list[UserAvailability]:
        query = (
            select(UserAvailability)
            .where(col(UserAvailability.event_group_id) == event_group_id)
            .options(selectinload(UserAvailability.available_dates))  # type: ignore[arg-type]
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def _make_date_entry(
        availability_id: uuid.UUID,
        day: dt.date | UserAvailabilityDateInput,
    ) -> UserAvailabilityDate:
        if isinstance(day, UserAvailabilityDateInput):
            return UserAvailabilityDate(
                availability_id=availability_id,
                slot_date=day.date,
                start_time=day.start_time,
                end_time=day.end_time,
            )
        return UserAvailabilityDate(availability_id=availability_id, slot_date=day)

    async def upsert_for_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        event_group_id: uuid.UUID,
        obj_in: UserAvailabilityCreate,
    ) -> UserAvailability:
        existing = await self.get_by_user_and_group(
            db, user_id=user_id, event_group_id=event_group_id
        )
        if existing:
            # Update fields
            existing.availability_type = obj_in.availability_type
            existing.notes = obj_in.notes
            existing.default_start_time = obj_in.default_start_time
            existing.default_end_time = obj_in.default_end_time
            # Replace dates — use cascade-aware clear instead of manual delete
            existing.available_dates.clear()
            await db.flush()
            for day in obj_in.dates:
                existing.available_dates.append(self._make_date_entry(existing.id, day))
            await db.flush()
            await db.refresh(existing, ["available_dates"])
            return existing
        else:
            avail = UserAvailability(
                user_id=user_id,
                event_group_id=event_group_id,
                availability_type=obj_in.availability_type,
                notes=obj_in.notes,
                default_start_time=obj_in.default_start_time,
                default_end_time=obj_in.default_end_time,
            )
            db.add(avail)
            await db.flush()
            await db.refresh(avail)
            for day in obj_in.dates:
                db.add(self._make_date_entry(avail.id, day))
            await db.flush()
            # Load with dates
            result = await self.get_by_user_and_group(
                db, user_id=user_id, event_group_id=event_group_id
            )
            return result  # type: ignore[return-value]

    async def delete_for_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        event_group_id: uuid.UUID,
    ) -> bool:
        existing = await self.get_by_user_and_group(
            db, user_id=user_id, event_group_id=event_group_id
        )
        if not existing:
            return False
        await db.delete(existing)
        await db.flush()
        return True


user_availability = CRUDUserAvailability(UserAvailability)
