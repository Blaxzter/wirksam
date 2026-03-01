# Duty Booking System — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a duty booking system where admins create events (e.g., Pfingsten, Kirchentag) with duty slots, and users can self-book slots that become locked (unmodifiable by others).

**Architecture:** Three new models — `Event`, `DutySlot`, `Booking` — following the existing Model → Schema → CRUD → Route → Register pattern. Events contain duty slots; users book themselves into slots. Bookings are locked: only the booking user or an admin can cancel. The frontend adds event browsing, slot booking, and a "My Bookings" view.

**Tech Stack:** FastAPI + SQLModel (backend), Vue 3 + TypeScript + shadcn-vue (frontend), Alembic migrations, Auth0 auth (existing), i18n (en + de).

---

## Phase 0: Template Cleanup

### Task 1: Study and run template cleanup scripts

**Files:**
- Run: `scripts/remove_examples.py`
- Run: `scripts/remove_project_task_domain.py`
- Regenerate: `just generate-client`

**Step 1: Run the clean-template command**

```bash
cd backend && uv sync && cd ..
just clean-template
```

This runs both `remove-examples` (deletes example views, nav items, demo schemas) and `remove-domain` (deletes Projects/Tasks models, CRUD, routes, schemas, tests, migrations, views) and then regenerates the frontend client.

> **Note:** If `just clean-template` prompts for confirmation, pass `--yes`:
> ```bash
> cd scripts && python remove_examples.py --yes && python remove_project_task_domain.py --yes && cd ..
> just generate-client
> ```

**Step 2: Verify the cleanup**

```bash
just lint-backend
cd frontend && pnpm type-check && cd ..
```

Fix any remaining import errors or dangling references the cleanup scripts may have missed.

**Step 3: Run the migration to reset schema**

After removing the Projects/Tasks migration, create a fresh baseline:

```bash
cd backend && uv run alembic upgrade head
```

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove template examples and project/task domain"
```

---

## Phase 1: Backend — Models

### Task 2: Create Event model

**Files:**
- Create: `backend/app/models/event.py`
- Modify: `backend/app/models/__init__.py`

**Step 1: Write the Event model**

```python
# backend/app/models/event.py
from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if __name__ != "__main__":
    from app.models.duty_slot import DutySlot  # noqa: F401


class Event(Base, table=True):
    __tablename__ = "events"

    name: str = Field(sa_column=sa.Column(sa.String, nullable=False, index=True))
    description: str | None = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )
    start_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    end_date: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    status: str = Field(
        default="draft",
        sa_column=sa.Column(sa.String, nullable=False, index=True),
    )
    created_by_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid, sa.ForeignKey("users.id"), nullable=True, index=True
        ),
    )

    duty_slots: list["DutySlot"] = Relationship(
        back_populates="event",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
```

**Step 2: Register the model in `__init__.py`**

Add to `backend/app/models/__init__.py`:

```python
from app.models.event import Event
from app.models.duty_slot import DutySlot
from app.models.booking import Booking
```

And add `"Event"`, `"DutySlot"`, `"Booking"` to the `__all__` list.

> **Important:** Do this AFTER creating all three model files (Tasks 2–4). Until then, the import will fail.

**Step 3: Commit**

Wait until Task 4 is done — commit all three models together.

---

### Task 3: Create DutySlot model

**Files:**
- Create: `backend/app/models/duty_slot.py`

**Step 1: Write the DutySlot model**

```python
# backend/app/models/duty_slot.py
from __future__ import annotations

import uuid
from datetime import date, time

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base

if __name__ != "__main__":
    from app.models.booking import Booking  # noqa: F401


class DutySlot(Base, table=True):
    __tablename__ = "duty_slots"

    event_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid, sa.ForeignKey("events.id"), nullable=False, index=True
        )
    )
    title: str = Field(sa_column=sa.Column(sa.String, nullable=False, index=True))
    description: str | None = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )
    date: date = Field(sa_column=sa.Column(sa.Date, nullable=False))
    start_time: time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    end_time: time | None = Field(
        default=None, sa_column=sa.Column(sa.Time, nullable=True)
    )
    location: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    category: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True, index=True)
    )
    max_bookings: int = Field(
        default=1, sa_column=sa.Column(sa.Integer, nullable=False)
    )

    event: "Event" = Relationship(back_populates="duty_slots")  # type: ignore[name-defined]
    bookings: list["Booking"] = Relationship(
        back_populates="duty_slot",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
```

---

### Task 4: Create Booking model

**Files:**
- Create: `backend/app/models/booking.py`
- Modify: `backend/app/models/__init__.py` (now register all three)

**Step 1: Write the Booking model**

```python
# backend/app/models/booking.py
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlmodel import Field, Relationship

from app.models.base import Base


class Booking(Base, table=True):
    __tablename__ = "bookings"
    __table_args__ = (
        sa.UniqueConstraint("duty_slot_id", "user_id", name="uq_booking_slot_user"),
    )

    duty_slot_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid, sa.ForeignKey("duty_slots.id"), nullable=False, index=True
        )
    )
    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid, sa.ForeignKey("users.id"), nullable=False, index=True
        )
    )
    status: str = Field(
        default="confirmed",
        sa_column=sa.Column(sa.String, nullable=False, index=True),
    )
    notes: str | None = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )

    duty_slot: "DutySlot" = Relationship(back_populates="bookings")  # type: ignore[name-defined]
```

**Step 2: Update `backend/app/models/__init__.py`**

Add these imports:

```python
from app.models.booking import Booking
from app.models.duty_slot import DutySlot
from app.models.event import Event
```

Add `"Booking"`, `"DutySlot"`, `"Event"` to `__all__`.

**Step 3: Generate Alembic migration**

```bash
cd backend && uv run alembic revision --autogenerate -m "Add events duty_slots bookings"
```

**Step 4: Run the migration**

```bash
cd backend && uv run alembic upgrade head
```

**Step 5: Commit**

```bash
git add backend/app/models/event.py backend/app/models/duty_slot.py backend/app/models/booking.py backend/app/models/__init__.py backend/app/alembic/versions/
git commit -m "feat: add Event, DutySlot, Booking models with migration"
```

---

## Phase 2: Backend — Schemas

### Task 5: Create Event schemas

**Files:**
- Create: `backend/app/schemas/event.py`

**Step 1: Write the schemas**

```python
# backend/app/schemas/event.py
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator

from typing import Literal


EventStatus = Literal["draft", "published", "archived"]


class EventBase(BaseModel):
    name: str
    description: str | None = None
    start_date: date
    end_date: date
    status: EventStatus = "draft"
    created_by_id: uuid.UUID | None = None

    @field_validator("end_date")
    @classmethod
    def end_date_after_start(cls, v: date, info: Any) -> date:
        start = info.data.get("start_date")
        if start and v < start:
            msg = "end_date must be on or after start_date"
            raise ValueError(msg)
        return v


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: EventStatus | None = None


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class EventListResponse(BaseModel):
    items: list[EventRead]
    total: int
    skip: int
    limit: int
```

> **Note:** Add missing imports at the top: `from datetime import date, datetime` and `from typing import Any, Literal`.

---

### Task 6: Create DutySlot schemas

**Files:**
- Create: `backend/app/schemas/duty_slot.py`

**Step 1: Write the schemas**

```python
# backend/app/schemas/duty_slot.py
from __future__ import annotations

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict


class DutySlotBase(BaseModel):
    event_id: uuid.UUID
    title: str
    description: str | None = None
    date: date
    start_time: time | None = None
    end_time: time | None = None
    location: str | None = None
    category: str | None = None
    max_bookings: int = 1


class DutySlotCreate(DutySlotBase):
    pass


class DutySlotUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    location: str | None = None
    category: str | None = None
    max_bookings: int | None = None


class DutySlotRead(DutySlotBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    current_bookings: int = 0  # computed in route, not stored


class DutySlotListResponse(BaseModel):
    items: list[DutySlotRead]
    total: int
    skip: int
    limit: int
```

---

### Task 7: Create Booking schemas

**Files:**
- Create: `backend/app/schemas/booking.py`

**Step 1: Write the schemas**

```python
# backend/app/schemas/booking.py
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from typing import Literal


BookingStatus = Literal["confirmed", "cancelled"]


class BookingBase(BaseModel):
    duty_slot_id: uuid.UUID
    user_id: uuid.UUID
    status: BookingStatus = "confirmed"
    notes: str | None = None


class BookingCreate(BaseModel):
    """User only provides the slot and optional notes. user_id is set server-side."""

    duty_slot_id: uuid.UUID
    notes: str | None = None


class BookingUpdate(BaseModel):
    status: BookingStatus | None = None
    notes: str | None = None


class BookingRead(BookingBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class BookingListResponse(BaseModel):
    items: list[BookingRead]
    total: int
    skip: int
    limit: int
```

**Step 2: Commit**

```bash
git add backend/app/schemas/event.py backend/app/schemas/duty_slot.py backend/app/schemas/booking.py
git commit -m "feat: add Event, DutySlot, Booking schemas"
```

---

## Phase 3: Backend — CRUD

### Task 8: Create Event CRUD

**Files:**
- Create: `backend/app/crud/event.py`

**Step 1: Write the CRUD class**

```python
# backend/app/crud/event.py
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.event import Event
from app.schemas.event import EventCreate, EventUpdate

EventSortField = Literal["name", "start_date", "end_date", "status", "created_at"]


class CRUDEvent(CRUDBase[Event, EventCreate, EventUpdate]):
    async def get_multi_filtered(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        search: str | None = None,
        status: str | None = None,
        created_by_id: str | None = None,
        sort_by: EventSortField = "start_date",
        sort_dir: Literal["asc", "desc"] = "asc",
    ) -> list[Event]:
        query = select(Event)
        if search:
            query = query.where(
                Event.name.ilike(f"%{search}%")  # type: ignore[union-attr]
                | Event.description.ilike(f"%{search}%")  # type: ignore[union-attr]
            )
        if status:
            query = query.where(Event.status == status)
        if created_by_id:
            query = query.where(Event.created_by_id == created_by_id)

        order_col = getattr(Event, sort_by)
        query = query.order_by(
            order_col.asc() if sort_dir == "asc" else order_col.desc()
        )
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_count_filtered(
        self,
        db: AsyncSession,
        *,
        search: str | None = None,
        status: str | None = None,
        created_by_id: str | None = None,
    ) -> int:
        query = select(func.count()).select_from(Event)
        if search:
            query = query.where(
                Event.name.ilike(f"%{search}%")  # type: ignore[union-attr]
                | Event.description.ilike(f"%{search}%")  # type: ignore[union-attr]
            )
        if status:
            query = query.where(Event.status == status)
        if created_by_id:
            query = query.where(Event.created_by_id == created_by_id)
        result = await db.execute(query)
        return result.scalar_one()


event = CRUDEvent(Event)
```

---

### Task 9: Create DutySlot CRUD

**Files:**
- Create: `backend/app/crud/duty_slot.py`

**Step 1: Write the CRUD class**

```python
# backend/app/crud/duty_slot.py
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.duty_slot import DutySlot
from app.schemas.duty_slot import DutySlotCreate, DutySlotUpdate

DutySlotSortField = Literal["title", "date", "start_time", "category", "created_at"]


class CRUDDutySlot(CRUDBase[DutySlot, DutySlotCreate, DutySlotUpdate]):
    async def get_multi_filtered(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        event_id: str | None = None,
        category: str | None = None,
        search: str | None = None,
        sort_by: DutySlotSortField = "date",
        sort_dir: Literal["asc", "desc"] = "asc",
    ) -> list[DutySlot]:
        query = select(DutySlot)
        if event_id:
            query = query.where(DutySlot.event_id == event_id)
        if category:
            query = query.where(DutySlot.category == category)
        if search:
            query = query.where(
                DutySlot.title.ilike(f"%{search}%")  # type: ignore[union-attr]
                | DutySlot.description.ilike(f"%{search}%")  # type: ignore[union-attr]
            )
        order_col = getattr(DutySlot, sort_by)
        query = query.order_by(
            order_col.asc() if sort_dir == "asc" else order_col.desc()
        )
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_count_filtered(
        self,
        db: AsyncSession,
        *,
        event_id: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> int:
        query = select(func.count()).select_from(DutySlot)
        if event_id:
            query = query.where(DutySlot.event_id == event_id)
        if category:
            query = query.where(DutySlot.category == category)
        if search:
            query = query.where(
                DutySlot.title.ilike(f"%{search}%")  # type: ignore[union-attr]
                | DutySlot.description.ilike(f"%{search}%")  # type: ignore[union-attr]
            )
        result = await db.execute(query)
        return result.scalar_one()


duty_slot = CRUDDutySlot(DutySlot)
```

---

### Task 10: Create Booking CRUD

**Files:**
- Create: `backend/app/crud/booking.py`
- Modify: `backend/app/crud/__init__.py`

**Step 1: Write the CRUD class**

```python
# backend/app/crud/booking.py
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.booking import Booking
from app.schemas.booking import BookingCreate, BookingUpdate


class CRUDBooking(CRUDBase[Booking, BookingCreate, BookingUpdate]):
    async def get_by_slot_and_user(
        self,
        db: AsyncSession,
        *,
        duty_slot_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Booking | None:
        query = select(Booking).where(
            Booking.duty_slot_id == duty_slot_id,
            Booking.user_id == user_id,
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_confirmed_count(
        self,
        db: AsyncSession,
        *,
        duty_slot_id: uuid.UUID,
    ) -> int:
        query = (
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.duty_slot_id == duty_slot_id,
                Booking.status == "confirmed",
            )
        )
        result = await db.execute(query)
        return result.scalar_one()

    async def get_multi_by_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
        status: str | None = None,
    ) -> list[Booking]:
        query = select(Booking).where(Booking.user_id == user_id)
        if status:
            query = query.where(Booking.status == status)
        query = query.order_by(Booking.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def count_by_user(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        status: str | None = None,
    ) -> int:
        query = (
            select(func.count())
            .select_from(Booking)
            .where(Booking.user_id == user_id)
        )
        if status:
            query = query.where(Booking.status == status)
        result = await db.execute(query)
        return result.scalar_one()

    async def get_multi_by_slot(
        self,
        db: AsyncSession,
        *,
        duty_slot_id: uuid.UUID,
        status: str | None = None,
    ) -> list[Booking]:
        query = select(Booking).where(Booking.duty_slot_id == duty_slot_id)
        if status:
            query = query.where(Booking.status == status)
        result = await db.execute(query)
        return list(result.scalars().all())


booking = CRUDBooking(Booking)
```

**Step 2: Update `backend/app/crud/__init__.py`**

Add:

```python
from app.crud.booking import booking
from app.crud.duty_slot import duty_slot
from app.crud.event import event
```

**Step 3: Commit**

```bash
git add backend/app/crud/event.py backend/app/crud/duty_slot.py backend/app/crud/booking.py backend/app/crud/__init__.py
git commit -m "feat: add Event, DutySlot, Booking CRUD classes"
```

---

## Phase 4: Backend — Routes

### Task 11: Create Events route

**Files:**
- Create: `backend/app/api/routes/events.py`

**Step 1: Write the events router**

```python
# backend/app/api/routes/events.py
from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, CurrentSuperuser, DBDep
from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.schemas.event import (
    EventCreate,
    EventListResponse,
    EventRead,
    EventUpdate,
    EventStatus,
)

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/", response_model=EventListResponse)
async def list_events(
    session: DBDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    search: str | None = None,
    status: EventStatus | None = None,
) -> EventListResponse:
    """List published events (all users) or all events (admin)."""
    effective_status = status
    if not current_user.is_admin and effective_status is None:
        effective_status = "published"

    items = await crud_event.get_multi_filtered(
        session, skip=skip, limit=limit, search=search, status=effective_status
    )
    total = await crud_event.get_count_filtered(
        session, search=search, status=effective_status
    )
    return EventListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/{event_id}", response_model=EventRead)
async def get_event(
    event_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> EventRead:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    if not current_user.is_admin and db_event.status != "published":
        raise_problem(403, code="event.not_published", detail="Event is not published")
    return db_event


@router.post("/", response_model=EventRead, status_code=201)
async def create_event(
    event_in: EventCreate,
    session: DBDep,
    current_user: CurrentSuperuser,
) -> EventRead:
    event_in.created_by_id = current_user.id
    return await crud_event.create(session, obj_in=event_in)


@router.patch("/{event_id}", response_model=EventRead)
async def update_event(
    event_id: str,
    event_in: EventUpdate,
    session: DBDep,
    current_user: CurrentSuperuser,
) -> EventRead:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    return await crud_event.update(session, db_obj=db_event, obj_in=event_in)


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    session: DBDep,
    current_user: CurrentSuperuser,
) -> None:
    db_event = await crud_event.get(session, event_id, raise_404_error=True)
    await session.delete(db_event)
    await session.commit()
```

---

### Task 12: Create DutySlots route

**Files:**
- Create: `backend/app/api/routes/duty_slots.py`

**Step 1: Write the duty_slots router**

```python
# backend/app/api/routes/duty_slots.py
from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, CurrentSuperuser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.duty_slot import duty_slot as crud_duty_slot
from app.crud.event import event as crud_event
from app.schemas.duty_slot import (
    DutySlotCreate,
    DutySlotListResponse,
    DutySlotRead,
    DutySlotUpdate,
)

router = APIRouter(prefix="/duty-slots", tags=["duty-slots"])


async def _enrich_slot(session, slot) -> DutySlotRead:
    """Add current_bookings count to a DutySlotRead."""
    count = await crud_booking.get_confirmed_count(session, duty_slot_id=slot.id)
    read = DutySlotRead.model_validate(slot)
    read.current_bookings = count
    return read


@router.get("/", response_model=DutySlotListResponse)
async def list_duty_slots(
    session: DBDep,
    current_user: CurrentUser,
    event_id: str | None = None,
    category: str | None = None,
    search: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> DutySlotListResponse:
    if event_id:
        db_event = await crud_event.get(session, event_id, raise_404_error=True)
        if not current_user.is_admin and db_event.status != "published":
            raise_problem(403, code="event.not_published", detail="Event is not published")

    items = await crud_duty_slot.get_multi_filtered(
        session, skip=skip, limit=limit, event_id=event_id, category=category, search=search
    )
    enriched = [await _enrich_slot(session, s) for s in items]
    total = await crud_duty_slot.get_count_filtered(
        session, event_id=event_id, category=category, search=search
    )
    return DutySlotListResponse(items=enriched, total=total, skip=skip, limit=limit)


@router.get("/{slot_id}", response_model=DutySlotRead)
async def get_duty_slot(
    slot_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> DutySlotRead:
    slot = await crud_duty_slot.get(session, slot_id, raise_404_error=True)
    return await _enrich_slot(session, slot)


@router.post("/", response_model=DutySlotRead, status_code=201)
async def create_duty_slot(
    slot_in: DutySlotCreate,
    session: DBDep,
    current_user: CurrentSuperuser,
) -> DutySlotRead:
    await crud_event.get(session, str(slot_in.event_id), raise_404_error=True)
    slot = await crud_duty_slot.create(session, obj_in=slot_in)
    return await _enrich_slot(session, slot)


@router.patch("/{slot_id}", response_model=DutySlotRead)
async def update_duty_slot(
    slot_id: str,
    slot_in: DutySlotUpdate,
    session: DBDep,
    current_user: CurrentSuperuser,
) -> DutySlotRead:
    db_slot = await crud_duty_slot.get(session, slot_id, raise_404_error=True)
    updated = await crud_duty_slot.update(session, db_obj=db_slot, obj_in=slot_in)
    return await _enrich_slot(session, updated)


@router.delete("/{slot_id}", status_code=204)
async def delete_duty_slot(
    slot_id: str,
    session: DBDep,
    current_user: CurrentSuperuser,
) -> None:
    slot = await crud_duty_slot.get(session, slot_id, raise_404_error=True)
    await session.delete(slot)
    await session.commit()
```

---

### Task 13: Create Bookings route

**Files:**
- Create: `backend/app/api/routes/bookings.py`

**Step 1: Write the bookings router**

This is the core of the system — implements the "locked booking" logic.

```python
# backend/app/api/routes/bookings.py
from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.booking import booking as crud_booking
from app.crud.duty_slot import duty_slot as crud_duty_slot
from app.schemas.booking import (
    BookingCreate,
    BookingListResponse,
    BookingRead,
    BookingUpdate,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.get("/me", response_model=BookingListResponse)
async def list_my_bookings(
    session: DBDep,
    current_user: CurrentUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    status: str | None = None,
) -> BookingListResponse:
    """List the current user's bookings."""
    items = await crud_booking.get_multi_by_user(
        session, user_id=current_user.id, skip=skip, limit=limit, status=status
    )
    total = await crud_booking.count_by_user(
        session, user_id=current_user.id, status=status
    )
    return BookingListResponse(items=items, total=total, skip=skip, limit=limit)


@router.post("/", response_model=BookingRead, status_code=201)
async def create_booking(
    booking_in: BookingCreate,
    session: DBDep,
    current_user: CurrentUser,
) -> BookingRead:
    """Book a duty slot for the current user."""
    # Check slot exists
    slot = await crud_duty_slot.get(
        session, str(booking_in.duty_slot_id), raise_404_error=True
    )

    # Check not already booked by this user
    existing = await crud_booking.get_by_slot_and_user(
        session, duty_slot_id=slot.id, user_id=current_user.id
    )
    if existing and existing.status == "confirmed":
        raise_problem(
            409, code="booking.already_exists", detail="You already have a confirmed booking for this slot"
        )

    # Check slot capacity
    confirmed_count = await crud_booking.get_confirmed_count(
        session, duty_slot_id=slot.id
    )
    if confirmed_count >= slot.max_bookings:
        raise_problem(
            409, code="booking.slot_full", detail="This duty slot is fully booked"
        )

    # If previously cancelled, reactivate
    if existing and existing.status == "cancelled":
        updated = await crud_booking.update(
            session,
            db_obj=existing,
            obj_in=BookingUpdate(status="confirmed", notes=booking_in.notes),
        )
        return updated

    # Create new booking
    from app.schemas.booking import BookingBase

    full_booking = BookingBase(
        duty_slot_id=booking_in.duty_slot_id,
        user_id=current_user.id,
        notes=booking_in.notes,
    )
    return await crud_booking.create(session, obj_in=full_booking)


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> BookingRead:
    db_booking = await crud_booking.get(session, booking_id, raise_404_error=True)
    if not current_user.is_admin and db_booking.user_id != current_user.id:
        raise_problem(403, code="booking.forbidden", detail="You can only view your own bookings")
    return db_booking


@router.patch("/{booking_id}", response_model=BookingRead)
async def update_booking(
    booking_id: str,
    booking_in: BookingUpdate,
    session: DBDep,
    current_user: CurrentUser,
) -> BookingRead:
    """Update a booking. Only the owner or admin can modify."""
    db_booking = await crud_booking.get(session, booking_id, raise_404_error=True)
    if not current_user.is_admin and db_booking.user_id != current_user.id:
        raise_problem(
            403, code="booking.forbidden", detail="You can only modify your own bookings"
        )
    return await crud_booking.update(session, db_obj=db_booking, obj_in=booking_in)


@router.delete("/{booking_id}", response_model=BookingRead)
async def cancel_booking(
    booking_id: str,
    session: DBDep,
    current_user: CurrentUser,
) -> BookingRead:
    """Cancel a booking (soft-cancel by setting status to 'cancelled')."""
    db_booking = await crud_booking.get(session, booking_id, raise_404_error=True)
    if not current_user.is_admin and db_booking.user_id != current_user.id:
        raise_problem(
            403, code="booking.forbidden", detail="You can only cancel your own bookings"
        )
    return await crud_booking.update(
        session, db_obj=db_booking, obj_in=BookingUpdate(status="cancelled")
    )
```

---

### Task 14: Register routes and regenerate client

**Files:**
- Modify: `backend/app/api/api.py`
- Run: `just generate-client`

**Step 1: Register the new routers in `api.py`**

Add to `backend/app/api/api.py`:

```python
from app.api.routes import events, duty_slots, bookings

api_router.include_router(events.router)
api_router.include_router(duty_slots.router)
api_router.include_router(bookings.router)
```

**Step 2: Verify backend starts**

```bash
cd backend && uv run fastapi dev app/main.py &
# Wait a few seconds for startup, then test:
curl http://localhost:8000/api/v1/healthz
# Kill the dev server
kill %1
```

**Step 3: Regenerate the frontend client**

```bash
just generate-client
```

**Step 4: Commit**

```bash
git add backend/app/api/ backend/app/crud/ frontend/src/client/
git commit -m "feat: add events, duty-slots, bookings routes and regenerate client"
```

---

## Phase 5: Backend — Tests

### Task 15: Create test fixtures

**Files:**
- Create: `backend/tests/fixtures/events.py`
- Create: `backend/tests/fixtures/duty_slots.py`
- Create: `backend/tests/fixtures/bookings.py`
- Modify: `backend/tests/conftest.py`

**Step 1: Write event fixtures**

```python
# backend/tests/fixtures/events.py
from datetime import date

import pytest

from app.models.event import Event


@pytest.fixture
async def test_event(db_session, test_user) -> Event:
    event = Event(
        name="Pfingsten 2026",
        description="Überregionale Dienstliste Pfingsten",
        start_date=date(2026, 5, 24),
        end_date=date(2026, 5, 26),
        status="published",
        created_by_id=test_user.id,
    )
    db_session.add(event)
    await db_session.flush()
    await db_session.refresh(event)
    return event


@pytest.fixture
async def test_draft_event(db_session, test_user) -> Event:
    event = Event(
        name="Kirchentag 2026",
        description="Draft event",
        start_date=date(2026, 6, 10),
        end_date=date(2026, 6, 14),
        status="draft",
        created_by_id=test_user.id,
    )
    db_session.add(event)
    await db_session.flush()
    await db_session.refresh(event)
    return event
```

**Step 2: Write duty_slot fixtures**

```python
# backend/tests/fixtures/duty_slots.py
from datetime import date, time

import pytest

from app.models.duty_slot import DutySlot


@pytest.fixture
async def test_duty_slot(db_session, test_event) -> DutySlot:
    slot = DutySlot(
        event_id=test_event.id,
        title="Einlasskontrolle",
        description="Einlass am Haupteingang",
        date=date(2026, 5, 24),
        start_time=time(8, 0),
        end_time=time(12, 0),
        location="Haupteingang",
        category="Sicherheit",
        max_bookings=2,
    )
    db_session.add(slot)
    await db_session.flush()
    await db_session.refresh(slot)
    return slot
```

**Step 3: Write booking fixtures**

```python
# backend/tests/fixtures/bookings.py
import pytest

from app.models.booking import Booking


@pytest.fixture
async def test_booking(db_session, test_duty_slot, test_user) -> Booking:
    booking = Booking(
        duty_slot_id=test_duty_slot.id,
        user_id=test_user.id,
        status="confirmed",
        notes="I'll be there!",
    )
    db_session.add(booking)
    await db_session.flush()
    await db_session.refresh(booking)
    return booking
```

**Step 4: Register fixtures in conftest.py**

Add to `backend/tests/conftest.py`:

```python
from tests.fixtures.events import *  # noqa: F403
from tests.fixtures.duty_slots import *  # noqa: F403
from tests.fixtures.bookings import *  # noqa: F403
```

---

### Task 16: Write Event CRUD tests

**Files:**
- Create: `backend/tests/crud/test_event.py`

**Step 1: Write the test file**

```python
# backend/tests/crud/test_event.py
from datetime import date

import pytest

from app.crud.event import event as crud_event
from app.schemas.event import EventCreate, EventUpdate


class TestCRUDEvent:
    @pytest.mark.asyncio
    async def test_create_event(self, db_session, test_user):
        event_in = EventCreate(
            name="Test Event",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 6, 3),
            status="draft",
            created_by_id=test_user.id,
        )
        event = await crud_event.create(db_session, obj_in=event_in)
        assert event.name == "Test Event"
        assert event.status == "draft"

    @pytest.mark.asyncio
    async def test_get_event(self, db_session, test_event):
        event = await crud_event.get(db_session, test_event.id)
        assert event is not None
        assert event.name == test_event.name

    @pytest.mark.asyncio
    async def test_update_event(self, db_session, test_event):
        update = EventUpdate(name="Updated Event")
        updated = await crud_event.update(db_session, db_obj=test_event, obj_in=update)
        assert updated.name == "Updated Event"

    @pytest.mark.asyncio
    async def test_get_multi_filtered_by_status(self, db_session, test_event, test_draft_event):
        published = await crud_event.get_multi_filtered(db_session, status="published")
        assert len(published) >= 1
        assert all(e.status == "published" for e in published)

    @pytest.mark.asyncio
    async def test_get_count_filtered(self, db_session, test_event):
        count = await crud_event.get_count_filtered(db_session, status="published")
        assert count >= 1
```

**Step 2: Run tests**

```bash
cd backend && uv run pytest tests/crud/test_event.py -v
```

Expected: all PASS.

---

### Task 17: Write Booking CRUD tests

**Files:**
- Create: `backend/tests/crud/test_booking.py`

**Step 1: Write the test file**

```python
# backend/tests/crud/test_booking.py
import pytest

from app.crud.booking import booking as crud_booking
from app.schemas.booking import BookingBase, BookingUpdate


class TestCRUDBooking:
    @pytest.mark.asyncio
    async def test_create_booking(self, db_session, test_duty_slot, test_user):
        booking_in = BookingBase(
            duty_slot_id=test_duty_slot.id,
            user_id=test_user.id,
        )
        booking = await crud_booking.create(db_session, obj_in=booking_in)
        assert booking.status == "confirmed"
        assert booking.user_id == test_user.id

    @pytest.mark.asyncio
    async def test_get_by_slot_and_user(self, db_session, test_booking):
        found = await crud_booking.get_by_slot_and_user(
            db_session,
            duty_slot_id=test_booking.duty_slot_id,
            user_id=test_booking.user_id,
        )
        assert found is not None
        assert found.id == test_booking.id

    @pytest.mark.asyncio
    async def test_get_confirmed_count(self, db_session, test_booking):
        count = await crud_booking.get_confirmed_count(
            db_session, duty_slot_id=test_booking.duty_slot_id
        )
        assert count == 1

    @pytest.mark.asyncio
    async def test_cancel_booking(self, db_session, test_booking):
        updated = await crud_booking.update(
            db_session,
            db_obj=test_booking,
            obj_in=BookingUpdate(status="cancelled"),
        )
        assert updated.status == "cancelled"
        count = await crud_booking.get_confirmed_count(
            db_session, duty_slot_id=test_booking.duty_slot_id
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_multi_by_user(self, db_session, test_booking, test_user):
        bookings = await crud_booking.get_multi_by_user(
            db_session, user_id=test_user.id
        )
        assert len(bookings) >= 1
```

**Step 2: Run tests**

```bash
cd backend && uv run pytest tests/crud/test_booking.py -v
```

---

### Task 18: Write route tests for events

**Files:**
- Create: `backend/tests/api/routes/test_events.py`

**Step 1: Write the test file**

```python
# backend/tests/api/routes/test_events.py
import pytest


class TestEventsRoutes:
    @pytest.mark.asyncio
    async def test_list_events(self, async_client, test_event):
        r = await async_client.get("/api/v1/events/")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_get_event(self, async_client, test_event):
        r = await async_client.get(f"/api/v1/events/{test_event.id}")
        assert r.status_code == 200
        assert r.json()["name"] == test_event.name

    @pytest.mark.asyncio
    async def test_create_event_admin_only(self, async_client):
        """Non-admin should get 403 creating events."""
        r = await async_client.post(
            "/api/v1/events/",
            json={
                "name": "New Event",
                "start_date": "2026-07-01",
                "end_date": "2026-07-03",
            },
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_create_event_as_admin(self, async_client, as_admin):
        r = await async_client.post(
            "/api/v1/events/",
            json={
                "name": "Admin Event",
                "start_date": "2026-07-01",
                "end_date": "2026-07-03",
            },
        )
        assert r.status_code == 201
        assert r.json()["name"] == "Admin Event"

    @pytest.mark.asyncio
    async def test_draft_event_hidden_from_normal_user(self, async_client, test_draft_event):
        r = await async_client.get(f"/api/v1/events/{test_draft_event.id}")
        assert r.status_code == 403
```

**Step 2: Run tests**

```bash
cd backend && uv run pytest tests/api/routes/test_events.py -v
```

---

### Task 19: Write route tests for bookings

**Files:**
- Create: `backend/tests/api/routes/test_bookings.py`

**Step 1: Write the test file**

```python
# backend/tests/api/routes/test_bookings.py
import pytest


class TestBookingsRoutes:
    @pytest.mark.asyncio
    async def test_create_booking(self, async_client, test_duty_slot):
        r = await async_client.post(
            "/api/v1/bookings/",
            json={"duty_slot_id": str(test_duty_slot.id)},
        )
        assert r.status_code == 201
        assert r.json()["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_double_booking_prevented(self, async_client, test_booking, test_duty_slot):
        r = await async_client.post(
            "/api/v1/bookings/",
            json={"duty_slot_id": str(test_duty_slot.id)},
        )
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_list_my_bookings(self, async_client, test_booking):
        r = await async_client.get("/api/v1/bookings/me")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    @pytest.mark.asyncio
    async def test_cancel_booking(self, async_client, test_booking):
        r = await async_client.delete(f"/api/v1/bookings/{test_booking.id}")
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_slot_capacity_enforced(self, async_client, db_session, test_event):
        """When a slot has max_bookings=1 and it's full, return 409."""
        from datetime import date, time
        from app.models.duty_slot import DutySlot
        from app.models.booking import Booking

        slot = DutySlot(
            event_id=test_event.id,
            title="Limited Slot",
            date=date(2026, 5, 24),
            start_time=time(14, 0),
            end_time=time(18, 0),
            max_bookings=1,
        )
        db_session.add(slot)
        await db_session.flush()
        await db_session.refresh(slot)

        # First booking via fixture user (already in DB through test override)
        # We need a different user to fill the slot, use admin user
        from app.models.user import User

        other_user = User(
            auth0_sub="auth0|other_user_cap_test",
            email="other@example.com",
            name="Other",
            roles=[],
        )
        db_session.add(other_user)
        await db_session.flush()

        existing = Booking(
            duty_slot_id=slot.id, user_id=other_user.id, status="confirmed"
        )
        db_session.add(existing)
        await db_session.flush()

        # Now try to book as current user — should be full
        r = await async_client.post(
            "/api/v1/bookings/",
            json={"duty_slot_id": str(slot.id)},
        )
        assert r.status_code == 409
```

**Step 2: Run all backend tests**

```bash
cd backend && uv run pytest -v
```

**Step 3: Commit**

```bash
git add backend/tests/
git commit -m "test: add Event, DutySlot, Booking CRUD and route tests"
```

---

## Phase 6: Frontend — i18n

### Task 20: Add i18n keys for duty booking

**Files:**
- Create: `frontend/src/locales/en/duties.json`
- Create: `frontend/src/locales/de/duties.json`
- Modify: `frontend/src/locales/en/navigation.json`
- Modify: `frontend/src/locales/de/navigation.json`
- Modify: `frontend/src/locales/en/errorCodes.json`
- Modify: `frontend/src/locales/de/errorCodes.json`

**Step 1: Create English locale**

```json
{
  "events": {
    "title": "Events",
    "subtitle": "Browse upcoming duty events",
    "create": "Create Event",
    "edit": "Edit Event",
    "delete": "Delete Event",
    "deleteConfirm": "Are you sure you want to delete this event? All duty slots and bookings will be lost.",
    "fields": {
      "name": "Name",
      "description": "Description",
      "startDate": "Start Date",
      "endDate": "End Date",
      "status": "Status"
    },
    "statuses": {
      "draft": "Draft",
      "published": "Published",
      "archived": "Archived"
    },
    "empty": "No events found.",
    "detail": {
      "title": "Event Details",
      "slots": "Duty Slots",
      "addSlot": "Add Duty Slot"
    }
  },
  "dutySlots": {
    "title": "Duty Slot",
    "create": "Create Duty Slot",
    "edit": "Edit Duty Slot",
    "delete": "Delete Duty Slot",
    "deleteConfirm": "Are you sure you want to delete this duty slot?",
    "fields": {
      "title": "Title",
      "description": "Description",
      "date": "Date",
      "startTime": "Start Time",
      "endTime": "End Time",
      "location": "Location",
      "category": "Category",
      "maxBookings": "Max Bookings"
    },
    "availability": "{current} / {max} booked",
    "full": "Fully booked",
    "available": "Available",
    "book": "Book this slot",
    "empty": "No duty slots for this event yet."
  },
  "bookings": {
    "title": "My Bookings",
    "subtitle": "Your duty slot reservations",
    "cancel": "Cancel Booking",
    "cancelConfirm": "Are you sure you want to cancel this booking?",
    "statuses": {
      "confirmed": "Confirmed",
      "cancelled": "Cancelled"
    },
    "empty": "You have no bookings yet.",
    "bookSuccess": "Slot booked successfully!",
    "cancelSuccess": "Booking cancelled."
  }
}
```

**Step 2: Create German locale**

```json
{
  "events": {
    "title": "Veranstaltungen",
    "subtitle": "Anstehende Dienst-Veranstaltungen durchsuchen",
    "create": "Veranstaltung erstellen",
    "edit": "Veranstaltung bearbeiten",
    "delete": "Veranstaltung löschen",
    "deleteConfirm": "Sind Sie sicher, dass Sie diese Veranstaltung löschen möchten? Alle Dienstschichten und Buchungen gehen verloren.",
    "fields": {
      "name": "Name",
      "description": "Beschreibung",
      "startDate": "Startdatum",
      "endDate": "Enddatum",
      "status": "Status"
    },
    "statuses": {
      "draft": "Entwurf",
      "published": "Veröffentlicht",
      "archived": "Archiviert"
    },
    "empty": "Keine Veranstaltungen gefunden.",
    "detail": {
      "title": "Veranstaltungsdetails",
      "slots": "Dienstschichten",
      "addSlot": "Dienstschicht hinzufügen"
    }
  },
  "dutySlots": {
    "title": "Dienstschicht",
    "create": "Dienstschicht erstellen",
    "edit": "Dienstschicht bearbeiten",
    "delete": "Dienstschicht löschen",
    "deleteConfirm": "Sind Sie sicher, dass Sie diese Dienstschicht löschen möchten?",
    "fields": {
      "title": "Titel",
      "description": "Beschreibung",
      "date": "Datum",
      "startTime": "Startzeit",
      "endTime": "Endzeit",
      "location": "Ort",
      "category": "Kategorie",
      "maxBookings": "Max. Buchungen"
    },
    "availability": "{current} / {max} gebucht",
    "full": "Ausgebucht",
    "available": "Verfügbar",
    "book": "Dienstschicht buchen",
    "empty": "Noch keine Dienstschichten für diese Veranstaltung."
  },
  "bookings": {
    "title": "Meine Buchungen",
    "subtitle": "Ihre Dienstschicht-Reservierungen",
    "cancel": "Buchung stornieren",
    "cancelConfirm": "Sind Sie sicher, dass Sie diese Buchung stornieren möchten?",
    "statuses": {
      "confirmed": "Bestätigt",
      "cancelled": "Storniert"
    },
    "empty": "Sie haben noch keine Buchungen.",
    "bookSuccess": "Dienstschicht erfolgreich gebucht!",
    "cancelSuccess": "Buchung storniert."
  }
}
```

**Step 3: Add navigation keys for sidebar**

Add to both `en/navigation.json` and `de/navigation.json` under `sidebar.items`:

English:
```json
"events": { "label": "Events", "description": "Browse duty events" },
"myBookings": { "label": "My Bookings", "description": "Your reservations" }
```

German:
```json
"events": { "label": "Veranstaltungen", "description": "Dienst-Veranstaltungen durchsuchen" },
"myBookings": { "label": "Meine Buchungen", "description": "Ihre Reservierungen" }
```

**Step 4: Add error code keys**

Add to both `en/errorCodes.json` and `de/errorCodes.json`:

English:
```json
"event.not_found": "Event not found",
"event.not_published": "This event is not yet published",
"booking.already_exists": "You already have a booking for this slot",
"booking.slot_full": "This duty slot is fully booked",
"booking.forbidden": "You can only manage your own bookings",
"duty_slot.not_found": "Duty slot not found"
```

German:
```json
"event.not_found": "Veranstaltung nicht gefunden",
"event.not_published": "Diese Veranstaltung ist noch nicht veröffentlicht",
"booking.already_exists": "Sie haben bereits eine Buchung für diese Schicht",
"booking.slot_full": "Diese Dienstschicht ist ausgebucht",
"booking.forbidden": "Sie können nur Ihre eigenen Buchungen verwalten",
"duty_slot.not_found": "Dienstschicht nicht gefunden"
```

**Step 5: Commit**

```bash
git add frontend/src/locales/
git commit -m "feat: add i18n keys for duty booking system (en + de)"
```

---

## Phase 7: Frontend — Views & Router

### Task 21: Create EventsView

**Files:**
- Create: `frontend/src/views/events/EventsView.vue`

**Step 1: Write the events list view**

This follows the same pattern as `ProjectsView.vue`. Key features:
- Lists published events with search
- Admins see a "Create Event" button and can see draft/archived events
- Each event card shows name, dates, status, slot count
- Click to navigate to event detail

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'
import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useAuthStore } from '@/stores/auth'
import { useDialog } from '@/composables/useDialog'
import { toastApiError } from '@/lib/api-errors'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { CalendarDays, Plus, Search, Trash2, Pencil } from 'lucide-vue-next'
import type { EventRead, EventListResponse } from '@/client'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const dialog = useDialog()
const { get, post, patch, delete: del } = useAuthenticatedClient()

const events = ref<EventRead[]>([])
const total = ref(0)
const search = ref('')
const loading = ref(false)
const showCreateDialog = ref(false)

const newEvent = ref({
  name: '',
  description: '',
  start_date: '',
  end_date: '',
  status: 'draft' as const,
})

async function loadEvents() {
  loading.value = true
  try {
    const response = await get<{ data: EventListResponse }>({
      url: '/events/',
      query: { search: search.value || undefined, limit: 100 },
    })
    events.value = response.data.items
    total.value = response.data.total
  } catch (error) {
    toastApiError(error, t('common.errors.api.fetchFailed'))
  } finally {
    loading.value = false
  }
}

async function createEvent() {
  try {
    await post({
      url: '/events/',
      body: newEvent.value,
    })
    toast.success(t('events.create') + ' ✓')
    showCreateDialog.value = false
    newEvent.value = { name: '', description: '', start_date: '', end_date: '', status: 'draft' }
    await loadEvents()
  } catch (error) {
    toastApiError(error)
  }
}

async function deleteEvent(event: EventRead) {
  const confirmed = await dialog.confirmDestructive({
    title: t('events.delete'),
    text: t('events.deleteConfirm'),
  })
  if (!confirmed) return
  try {
    await del({ url: `/events/${event.id}` })
    toast.success(t('events.delete') + ' ✓')
    await loadEvents()
  } catch (error) {
    toastApiError(error)
  }
}

function navigateToEvent(eventId: string) {
  router.push({ name: 'event-detail', params: { eventId } })
}

onMounted(loadEvents)
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-3xl font-bold tracking-tight">{{ t('events.title') }}</h1>
        <p class="text-muted-foreground">{{ t('events.subtitle') }}</p>
      </div>
      <Button v-if="authStore.isAdmin" @click="showCreateDialog = true">
        <Plus class="mr-2 h-4 w-4" />
        {{ t('events.create') }}
      </Button>
    </div>

    <div class="flex items-center gap-2">
      <div class="relative flex-1 max-w-sm">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          v-model="search"
          class="pl-9"
          placeholder="Search..."
          @input="loadEvents"
        />
      </div>
    </div>

    <div v-if="events.length === 0 && !loading" class="text-center py-12 text-muted-foreground">
      {{ t('events.empty') }}
    </div>

    <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <Card
        v-for="event in events"
        :key="event.id"
        class="cursor-pointer hover:shadow-md transition-shadow"
        @click="navigateToEvent(event.id)"
      >
        <CardHeader>
          <div class="flex items-center justify-between">
            <CardTitle class="text-lg">{{ event.name }}</CardTitle>
            <Badge :variant="event.status === 'published' ? 'default' : 'secondary'">
              {{ t(`events.statuses.${event.status}`) }}
            </Badge>
          </div>
          <CardDescription v-if="event.description">{{ event.description }}</CardDescription>
        </CardHeader>
        <CardContent>
          <div class="flex items-center gap-2 text-sm text-muted-foreground">
            <CalendarDays class="h-4 w-4" />
            <span>{{ event.start_date }} — {{ event.end_date }}</span>
          </div>
          <div v-if="authStore.isAdmin" class="mt-4 flex gap-2" @click.stop>
            <Button size="sm" variant="outline" @click="deleteEvent(event)">
              <Trash2 class="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Create Event Dialog -->
    <Dialog v-model:open="showCreateDialog">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t('events.create') }}</DialogTitle>
        </DialogHeader>
        <div class="space-y-4">
          <div>
            <Label>{{ t('events.fields.name') }}</Label>
            <Input v-model="newEvent.name" />
          </div>
          <div>
            <Label>{{ t('events.fields.description') }}</Label>
            <Input v-model="newEvent.description" />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <Label>{{ t('events.fields.startDate') }}</Label>
              <Input v-model="newEvent.start_date" type="date" />
            </div>
            <div>
              <Label>{{ t('events.fields.endDate') }}</Label>
              <Input v-model="newEvent.end_date" type="date" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showCreateDialog = false">
            {{ t('common.actions.cancel') }}
          </Button>
          <Button @click="createEvent" :disabled="!newEvent.name || !newEvent.start_date || !newEvent.end_date">
            {{ t('common.actions.create') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
```

---

### Task 22: Create EventDetailView

**Files:**
- Create: `frontend/src/views/events/EventDetailView.vue`

**Step 1: Write the event detail view with duty slots and booking**

This is the main view where users see duty slots and book them. Key features:
- Shows event info at top
- Lists duty slots grouped by date
- Each slot shows availability (X/Y booked), time, location
- "Book" button per slot — disabled if full or already booked
- Admin can create/edit/delete slots
- Admin can publish/archive events

```vue
<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'
import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useAuthStore } from '@/stores/auth'
import { useBreadcrumbStore } from '@/stores/breadcrumb'
import { useDialog } from '@/composables/useDialog'
import { toastApiError } from '@/lib/api-errors'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { CalendarDays, Clock, MapPin, Plus, Trash2, Check, X } from 'lucide-vue-next'
import type { EventRead, DutySlotRead, DutySlotListResponse, BookingListResponse, BookingRead } from '@/client'

const { t } = useI18n()
const route = useRoute()
const authStore = useAuthStore()
const breadcrumbStore = useBreadcrumbStore()
const dialog = useDialog()
const { get, post, patch, delete: del } = useAuthenticatedClient()

const eventId = computed(() => route.params.eventId as string)
const event = ref<EventRead | null>(null)
const slots = ref<DutySlotRead[]>([])
const myBookings = ref<BookingRead[]>([])
const loading = ref(false)
const showAddSlotDialog = ref(false)

const newSlot = ref({
  title: '',
  description: '',
  date: '',
  start_time: '',
  end_time: '',
  location: '',
  category: '',
  max_bookings: 1,
})

// Group slots by date
const slotsByDate = computed(() => {
  const groups: Record<string, DutySlotRead[]> = {}
  for (const slot of slots.value) {
    const d = slot.date
    if (!groups[d]) groups[d] = []
    groups[d].push(slot)
  }
  return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
})

// Set of duty_slot_ids I've booked (confirmed)
const myBookedSlotIds = computed(() =>
  new Set(myBookings.value.filter(b => b.status === 'confirmed').map(b => b.duty_slot_id))
)

function myBookingForSlot(slotId: string): BookingRead | undefined {
  return myBookings.value.find(b => b.duty_slot_id === slotId && b.status === 'confirmed')
}

async function loadEvent() {
  loading.value = true
  try {
    const res = await get<{ data: EventRead }>({ url: `/events/${eventId.value}` })
    event.value = res.data
    breadcrumbStore.setBreadcrumbs([
      { titleKey: 'events.title', to: { name: 'events' } },
      { title: res.data.name },
    ])
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

async function loadSlots() {
  try {
    const res = await get<{ data: DutySlotListResponse }>({
      url: '/duty-slots/',
      query: { event_id: eventId.value, limit: 200 },
    })
    slots.value = res.data.items
  } catch (error) {
    toastApiError(error)
  }
}

async function loadMyBookings() {
  try {
    const res = await get<{ data: BookingListResponse }>({
      url: '/bookings/me',
      query: { status: 'confirmed', limit: 200 },
    })
    myBookings.value = res.data.items
  } catch (error) {
    toastApiError(error)
  }
}

async function bookSlot(slotId: string) {
  try {
    await post({ url: '/bookings/', body: { duty_slot_id: slotId } })
    toast.success(t('bookings.bookSuccess'))
    await Promise.all([loadSlots(), loadMyBookings()])
  } catch (error) {
    toastApiError(error)
  }
}

async function cancelBooking(slotId: string) {
  const booking = myBookingForSlot(slotId)
  if (!booking) return
  const confirmed = await dialog.confirmDestructive({
    title: t('bookings.cancel'),
    text: t('bookings.cancelConfirm'),
  })
  if (!confirmed) return
  try {
    await del({ url: `/bookings/${booking.id}` })
    toast.success(t('bookings.cancelSuccess'))
    await Promise.all([loadSlots(), loadMyBookings()])
  } catch (error) {
    toastApiError(error)
  }
}

async function createSlot() {
  try {
    await post({
      url: '/duty-slots/',
      body: {
        ...newSlot.value,
        event_id: eventId.value,
        start_time: newSlot.value.start_time || null,
        end_time: newSlot.value.end_time || null,
        location: newSlot.value.location || null,
        category: newSlot.value.category || null,
      },
    })
    toast.success(t('dutySlots.create') + ' ✓')
    showAddSlotDialog.value = false
    newSlot.value = { title: '', description: '', date: '', start_time: '', end_time: '', location: '', category: '', max_bookings: 1 }
    await loadSlots()
  } catch (error) {
    toastApiError(error)
  }
}

async function deleteSlot(slotId: string) {
  const confirmed = await dialog.confirmDestructive({
    title: t('dutySlots.delete'),
    text: t('dutySlots.deleteConfirm'),
  })
  if (!confirmed) return
  try {
    await del({ url: `/duty-slots/${slotId}` })
    await loadSlots()
  } catch (error) {
    toastApiError(error)
  }
}

async function publishEvent() {
  if (!event.value) return
  try {
    await patch({ url: `/events/${eventId.value}`, body: { status: 'published' } })
    toast.success('Event published')
    await loadEvent()
  } catch (error) {
    toastApiError(error)
  }
}

onMounted(async () => {
  await loadEvent()
  await Promise.all([loadSlots(), loadMyBookings()])
})
</script>

<template>
  <div class="space-y-6" v-if="event">
    <!-- Event Header -->
    <div class="flex items-start justify-between">
      <div>
        <h1 class="text-3xl font-bold tracking-tight">{{ event.name }}</h1>
        <p v-if="event.description" class="text-muted-foreground mt-1">{{ event.description }}</p>
        <div class="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
          <div class="flex items-center gap-1">
            <CalendarDays class="h-4 w-4" />
            {{ event.start_date }} — {{ event.end_date }}
          </div>
          <Badge :variant="event.status === 'published' ? 'default' : 'secondary'">
            {{ t(`events.statuses.${event.status}`) }}
          </Badge>
        </div>
      </div>
      <div v-if="authStore.isAdmin" class="flex gap-2">
        <Button v-if="event.status === 'draft'" @click="publishEvent" variant="outline">
          Publish
        </Button>
        <Button @click="showAddSlotDialog = true">
          <Plus class="mr-2 h-4 w-4" />
          {{ t('events.detail.addSlot') }}
        </Button>
      </div>
    </div>

    <Separator />

    <!-- Duty Slots grouped by date -->
    <div v-if="slots.length === 0" class="text-center py-12 text-muted-foreground">
      {{ t('dutySlots.empty') }}
    </div>

    <div v-for="[date, dateSlots] in slotsByDate" :key="date" class="space-y-3">
      <h2 class="text-xl font-semibold flex items-center gap-2">
        <CalendarDays class="h-5 w-5" />
        {{ date }}
      </h2>
      <div class="grid gap-3 md:grid-cols-2">
        <Card v-for="slot in dateSlots" :key="slot.id">
          <CardHeader class="pb-2">
            <div class="flex items-center justify-between">
              <CardTitle class="text-base">{{ slot.title }}</CardTitle>
              <Badge v-if="slot.current_bookings >= slot.max_bookings" variant="destructive">
                {{ t('dutySlots.full') }}
              </Badge>
              <Badge v-else variant="outline">
                {{ t('dutySlots.availability', { current: slot.current_bookings, max: slot.max_bookings }) }}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <p v-if="slot.description" class="text-sm text-muted-foreground mb-2">{{ slot.description }}</p>
            <div class="flex flex-wrap gap-3 text-sm text-muted-foreground">
              <div v-if="slot.start_time" class="flex items-center gap-1">
                <Clock class="h-3 w-3" />
                {{ slot.start_time }}{{ slot.end_time ? ` – ${slot.end_time}` : '' }}
              </div>
              <div v-if="slot.location" class="flex items-center gap-1">
                <MapPin class="h-3 w-3" />
                {{ slot.location }}
              </div>
              <Badge v-if="slot.category" variant="secondary" class="text-xs">{{ slot.category }}</Badge>
            </div>
            <div class="mt-3 flex gap-2">
              <Button
                v-if="myBookedSlotIds.has(slot.id)"
                variant="outline"
                size="sm"
                @click="cancelBooking(slot.id)"
              >
                <X class="mr-1 h-4 w-4" />
                {{ t('bookings.cancel') }}
              </Button>
              <Button
                v-else
                size="sm"
                :disabled="slot.current_bookings >= slot.max_bookings"
                @click="bookSlot(slot.id)"
              >
                <Check class="mr-1 h-4 w-4" />
                {{ t('dutySlots.book') }}
              </Button>
              <Button
                v-if="authStore.isAdmin"
                size="sm"
                variant="ghost"
                @click="deleteSlot(slot.id)"
              >
                <Trash2 class="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>

    <!-- Add Slot Dialog -->
    <Dialog v-model:open="showAddSlotDialog">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t('dutySlots.create') }}</DialogTitle>
        </DialogHeader>
        <div class="space-y-4">
          <div>
            <Label>{{ t('dutySlots.fields.title') }}</Label>
            <Input v-model="newSlot.title" />
          </div>
          <div>
            <Label>{{ t('dutySlots.fields.description') }}</Label>
            <Input v-model="newSlot.description" />
          </div>
          <div>
            <Label>{{ t('dutySlots.fields.date') }}</Label>
            <Input v-model="newSlot.date" type="date" />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <Label>{{ t('dutySlots.fields.startTime') }}</Label>
              <Input v-model="newSlot.start_time" type="time" />
            </div>
            <div>
              <Label>{{ t('dutySlots.fields.endTime') }}</Label>
              <Input v-model="newSlot.end_time" type="time" />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <Label>{{ t('dutySlots.fields.location') }}</Label>
              <Input v-model="newSlot.location" />
            </div>
            <div>
              <Label>{{ t('dutySlots.fields.category') }}</Label>
              <Input v-model="newSlot.category" />
            </div>
          </div>
          <div>
            <Label>{{ t('dutySlots.fields.maxBookings') }}</Label>
            <Input v-model.number="newSlot.max_bookings" type="number" min="1" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showAddSlotDialog = false">
            {{ t('common.actions.cancel') }}
          </Button>
          <Button @click="createSlot" :disabled="!newSlot.title || !newSlot.date">
            {{ t('common.actions.create') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
```

---

### Task 23: Create MyBookingsView

**Files:**
- Create: `frontend/src/views/bookings/MyBookingsView.vue`

**Step 1: Write the my-bookings view**

Shows all of the current user's bookings with slot/event details and cancel option.

```vue
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'
import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'
import { toastApiError } from '@/lib/api-errors'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { X } from 'lucide-vue-next'
import type { BookingRead, BookingListResponse, DutySlotRead } from '@/client'

const { t } = useI18n()
const dialog = useDialog()
const { get, delete: del } = useAuthenticatedClient()

interface BookingWithSlot extends BookingRead {
  slot?: DutySlotRead
}

const bookings = ref<BookingWithSlot[]>([])
const loading = ref(false)

async function loadBookings() {
  loading.value = true
  try {
    const res = await get<{ data: BookingListResponse }>({
      url: '/bookings/me',
      query: { limit: 200 },
    })
    // Enrich each booking with its slot details
    const enriched: BookingWithSlot[] = []
    for (const booking of res.data.items) {
      try {
        const slotRes = await get<{ data: DutySlotRead }>({
          url: `/duty-slots/${booking.duty_slot_id}`,
        })
        enriched.push({ ...booking, slot: slotRes.data })
      } catch {
        enriched.push(booking)
      }
    }
    bookings.value = enriched
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

async function cancelBooking(booking: BookingWithSlot) {
  const confirmed = await dialog.confirmDestructive({
    title: t('bookings.cancel'),
    text: t('bookings.cancelConfirm'),
  })
  if (!confirmed) return
  try {
    await del({ url: `/bookings/${booking.id}` })
    toast.success(t('bookings.cancelSuccess'))
    await loadBookings()
  } catch (error) {
    toastApiError(error)
  }
}

onMounted(loadBookings)
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-3xl font-bold tracking-tight">{{ t('bookings.title') }}</h1>
      <p class="text-muted-foreground">{{ t('bookings.subtitle') }}</p>
    </div>

    <div v-if="bookings.length === 0 && !loading" class="text-center py-12 text-muted-foreground">
      {{ t('bookings.empty') }}
    </div>

    <div class="grid gap-4 md:grid-cols-2">
      <Card v-for="booking in bookings" :key="booking.id">
        <CardHeader class="pb-2">
          <div class="flex items-center justify-between">
            <CardTitle class="text-base">{{ booking.slot?.title ?? 'Unknown Slot' }}</CardTitle>
            <Badge :variant="booking.status === 'confirmed' ? 'default' : 'secondary'">
              {{ t(`bookings.statuses.${booking.status}`) }}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div v-if="booking.slot" class="text-sm text-muted-foreground space-y-1">
            <p>{{ booking.slot.date }}{{ booking.slot.start_time ? ` · ${booking.slot.start_time}` : '' }}{{ booking.slot.end_time ? ` – ${booking.slot.end_time}` : '' }}</p>
            <p v-if="booking.slot.location">{{ booking.slot.location }}</p>
          </div>
          <p v-if="booking.notes" class="text-sm mt-2">{{ booking.notes }}</p>
          <div class="mt-3" v-if="booking.status === 'confirmed'">
            <Button size="sm" variant="outline" @click="cancelBooking(booking)">
              <X class="mr-1 h-4 w-4" />
              {{ t('bookings.cancel') }}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
```

---

### Task 24: Register routes and update sidebar

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/components/navigation/AppSidebar.vue`

**Step 1: Add routes to `router/index.ts`**

Inside the `postauth-layout` children array, add:

```typescript
{
  path: '/app/events',
  name: 'events',
  component: () => import('@/views/events/EventsView.vue'),
  meta: {
    breadcrumbs: [{ titleKey: 'events.title' }],
  },
},
{
  path: '/app/events/:eventId',
  name: 'event-detail',
  component: () => import('@/views/events/EventDetailView.vue'),
  meta: {
    breadcrumbs: [
      { titleKey: 'events.title', to: { name: 'events' } },
      { titleKey: 'events.detail.title' },
    ],
  },
},
{
  path: '/app/bookings',
  name: 'my-bookings',
  component: () => import('@/views/bookings/MyBookingsView.vue'),
  meta: {
    breadcrumbs: [{ titleKey: 'bookings.title' }],
  },
},
```

**Step 2: Update AppSidebar.vue**

Add navigation items to the `navMain` array in `AppSidebar.vue`. Import `CalendarDays` and `BookCheck` from `lucide-vue-next`.

```typescript
{
  titleKey: 'navigation.sidebar.items.events.label',
  icon: CalendarDays,
  routeName: 'events',
  isActive: true,
},
{
  titleKey: 'navigation.sidebar.items.myBookings.label',
  icon: BookCheck,
  routeName: 'my-bookings',
},
```

**Step 3: Verify**

```bash
cd frontend && pnpm type-check
```

**Step 4: Commit**

```bash
git add frontend/src/views/ frontend/src/router/ frontend/src/components/navigation/
git commit -m "feat: add Events, EventDetail, MyBookings views with routing and sidebar nav"
```

---

## Phase 8: Final Integration

### Task 25: Full verification

**Step 1: Run backend linting**

```bash
just lint-backend
```

Fix any issues.

**Step 2: Run backend tests**

```bash
just test-backend
```

All tests should pass.

**Step 3: Run frontend type-check**

```bash
cd frontend && pnpm type-check
```

**Step 4: Run frontend lint**

```bash
just lint-frontend
```

**Step 5: Start the full stack and manually test**

```bash
docker compose watch
```

Test manually:
1. Log in → see Events in sidebar
2. As admin: create an event, add duty slots, publish event
3. As regular user: see published events, book a slot, see it in "My Bookings"
4. Verify: another user cannot cancel your booking
5. Cancel your own booking → slot becomes available again
6. Verify: slot capacity is enforced (try to overbook)

**Step 6: Final commit**

```bash
git add -A
git commit -m "feat: complete duty booking system (events, duty slots, bookings)"
```

---

## Summary

| Phase | Tasks | What |
|-------|-------|------|
| 0 | 1 | Template cleanup |
| 1 | 2–4 | Models: Event, DutySlot, Booking + migration |
| 2 | 5–7 | Schemas |
| 3 | 8–10 | CRUD classes |
| 4 | 11–14 | Routes + API registration + client regen |
| 5 | 15–19 | Test fixtures + CRUD tests + route tests |
| 6 | 20 | i18n (en + de) |
| 7 | 21–24 | Frontend views + router + sidebar |
| 8 | 25 | Full verification |

**Future enhancements (not in scope):**
- Email reminders (SMTP is configured — add a scheduled job with APScheduler or Celery)
- Bulk slot creation (admin creates many slots at once for a date range)
- Export duty list as PDF/CSV
- User profile with phone number for SMS reminders
