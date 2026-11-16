import datetime as dt
import uuid

from pydantic import BaseModel


class ReportingOverviewStats(BaseModel):
    total_bookings: int
    confirmed_bookings: int
    cancelled_bookings: int
    cancellation_rate: float
    total_tasks: int
    total_shifts: int
    total_shift_capacity: int
    filled_shifts: int
    fill_rate: float
    active_volunteers: int
    total_volunteers: int


class BookingsTrendPoint(BaseModel):
    date: dt.date
    confirmed: int
    cancelled: int


class TopVolunteer(BaseModel):
    """A guest account gives one row per name its pooled sign-ups were made
    under, all with its ``user_id``."""

    user_id: uuid.UUID
    name: str | None
    email: str | None
    booking_count: int


class CategoryBreakdown(BaseModel):
    category: str | None
    slot_count: int
    total_capacity: int
    confirmed_bookings: int
    fill_rate: float


class BookingsByHour(BaseModel):
    hour: int  # 0–23
    booking_count: int


class TaskFillRate(BaseModel):
    task_id: uuid.UUID
    task_name: str
    total_capacity: int
    confirmed_bookings: int
    fill_rate: float


class ReportingResponse(BaseModel):
    overview: ReportingOverviewStats
    bookings_trend: list[BookingsTrendPoint]
    top_volunteers: list[TopVolunteer]
    category_breakdown: list[CategoryBreakdown]
    bookings_by_hour: list[BookingsByHour]
    task_fill_rates: list[TaskFillRate]
