"""Code-level registry of all notification types.

This is the single source of truth for notification types.
The seeder upserts these into the database on startup.
"""

from dataclasses import dataclass
from typing import TypedDict


class NotificationTypeDict(TypedDict):
    code: str
    name: str
    description: str
    category: str
    is_admin_only: bool
    default_channels: list[str]


@dataclass(frozen=True)
class NotificationTypeDef:
    code: str
    name: str
    description: str
    category: str
    is_admin_only: bool = False
    default_channels: list[str] | None = None

    def to_dict(self) -> NotificationTypeDict:
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "is_admin_only": self.is_admin_only,
            "default_channels": self.default_channels or ["email"],
        }


# ── Booking notifications ─────────────────────────────────────────

BOOKING_CONFIRMED = NotificationTypeDef(
    code="booking.confirmed",
    name="Booking Confirmed",
    description="Notification when your booking is confirmed",
    category="booking",
    default_channels=["email", "push"],
)

BOOKING_CANCELLED_BY_USER = NotificationTypeDef(
    code="booking.cancelled_by_user",
    name="Booking Cancelled",
    description="Notification when you cancel a booking",
    category="booking",
    default_channels=["email"],
)

BOOKING_CANCELLED_BY_ADMIN = NotificationTypeDef(
    code="booking.cancelled_by_admin",
    name="Booking Cancelled by Admin",
    description="Notification when an admin cancels your booking (slot deleted or regenerated)",
    category="booking",
    default_channels=["email", "push"],
)

BOOKING_SLOT_COBOOKED = NotificationTypeDef(
    code="booking.slot_cobooked",
    name="Slot Co-booked",
    description="Notification when someone else also books a slot you are on",
    category="booking",
    default_channels=["push"],
)

# ── Slot notifications ────────────────────────────────────────────

SLOT_STARTING_SOON_UNFILLED = NotificationTypeDef(
    code="slot.starting_soon_unfilled",
    name="Slot Starting Soon (Unfilled)",
    description="Alert when a slot starts in 30 minutes but still has open spots",
    category="slot",
    is_admin_only=True,
    default_channels=["email", "push"],
)

SLOT_TIME_CHANGED = NotificationTypeDef(
    code="slot.time_changed",
    name="Slot Time Changed",
    description="Notification when a slot you booked has its time changed",
    category="slot",
    default_channels=["email", "push"],
)

# ── Event notifications ───────────────────────────────────────────

EVENT_PUBLISHED = NotificationTypeDef(
    code="event.published",
    name="Event Published",
    description="Notification when a new event is published",
    category="event",
    default_channels=["email"],
)

# ── Event group notifications ─────────────────────────────────────

EVENT_GROUP_PUBLISHED = NotificationTypeDef(
    code="event_group.published",
    name="Event Group Published",
    description="Notification when a new event group is published",
    category="event_group",
    default_channels=["email"],
)

# ── Availability notifications ────────────────────────────────────

AVAILABILITY_REMINDER = NotificationTypeDef(
    code="availability.reminder",
    name="Availability Reminder",
    description="Reminder to submit your availability for a published event group",
    category="availability",
    default_channels=["email", "push"],
)

# ── User / admin notifications ────────────────────────────────────

USER_REGISTERED = NotificationTypeDef(
    code="user.registered",
    name="New User Registered",
    description="Alert when a new user signs up and is pending approval",
    category="admin",
    is_admin_only=True,
    default_channels=["email", "push"],
)

USER_APPROVED = NotificationTypeDef(
    code="user.approved",
    name="Account Approved",
    description="Notification when your account is approved by an admin",
    category="user",
    default_channels=["email", "push"],
)

USER_REJECTED = NotificationTypeDef(
    code="user.rejected",
    name="Account Rejected",
    description="Notification when your account is rejected by an admin",
    category="user",
    default_channels=["email"],
)

# ── All types registry ────────────────────────────────────────────

ALL_NOTIFICATION_TYPES: list[NotificationTypeDef] = [
    BOOKING_CONFIRMED,
    BOOKING_CANCELLED_BY_USER,
    BOOKING_CANCELLED_BY_ADMIN,
    BOOKING_SLOT_COBOOKED,
    SLOT_STARTING_SOON_UNFILLED,
    SLOT_TIME_CHANGED,
    EVENT_PUBLISHED,
    EVENT_GROUP_PUBLISHED,
    AVAILABILITY_REMINDER,
    USER_REGISTERED,
    USER_APPROVED,
    USER_REJECTED,
]
