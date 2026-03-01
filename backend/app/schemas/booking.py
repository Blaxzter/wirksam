from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

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
