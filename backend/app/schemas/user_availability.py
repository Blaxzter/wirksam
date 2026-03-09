import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

AvailabilityType = Literal["fully_available", "specific_dates", "time_range"]


class UserAvailabilityDateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    slot_date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None


class UserAvailabilityDateInput(BaseModel):
    date: dt.date
    start_time: dt.time | None = None
    end_time: dt.time | None = None


class UserAvailabilityBase(BaseModel):
    availability_type: AvailabilityType
    notes: str | None = None
    default_start_time: dt.time | None = None
    default_end_time: dt.time | None = None

    @model_validator(mode="after")
    def check_default_time_order(self) -> "UserAvailabilityBase":
        if (
            self.default_start_time is not None
            and self.default_end_time is not None
            and self.default_start_time >= self.default_end_time
        ):
            msg = "default_start_time must be before default_end_time"
            raise ValueError(msg)
        return self


class UserAvailabilityCreate(UserAvailabilityBase):
    dates: list[dt.date | UserAvailabilityDateInput] = []


class UserAvailabilityUpdate(BaseModel):
    availability_type: AvailabilityType | None = None
    notes: str | None = None
    dates: list[dt.date | UserAvailabilityDateInput] | None = None


class UserAvailabilityRead(UserAvailabilityBase):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    event_group_id: uuid.UUID
    available_dates: list[UserAvailabilityDateRead] = []
    created_at: dt.datetime
    updated_at: dt.datetime


class UserAvailabilityWithUser(UserAvailabilityRead):
    """Extended read schema for admin view — includes basic user info."""

    user_full_name: str | None = None
    user_email: str | None = None
