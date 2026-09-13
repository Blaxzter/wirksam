"""Code-level registry of all notification types.

This is the single source of truth for notification types.
The seeder upserts these into the database on startup.
"""

from dataclasses import dataclass
from typing import Literal, TypedDict

# Classification groups notifications by user intent so the inbox can
# offer a "Reminders / Changes / Matches / Announcements" tab navigation.
# Distinct from `category` (functional domain: booking, shift, …).
NotificationClassification = Literal["reminder", "change", "match", "announcement"]


class NotificationTypeDict(TypedDict):
    code: str
    name: str
    description: str
    category: str
    classification: NotificationClassification
    is_admin_only: bool
    default_channels: list[str]
    is_user_configurable: bool


@dataclass(frozen=True)
class NotificationTypeDef:
    code: str
    name: str
    description: str
    category: str
    classification: NotificationClassification = "announcement"
    is_admin_only: bool = False
    default_channels: list[str] | None = None
    is_user_configurable: bool = True

    def to_dict(self) -> NotificationTypeDict:
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "classification": self.classification,
            "is_admin_only": self.is_admin_only,
            "default_channels": self.default_channels or ["email"],
            "is_user_configurable": self.is_user_configurable,
        }


# ── Booking notifications ─────────────────────────────────────────

BOOKING_CONFIRMED = NotificationTypeDef(
    code="booking.confirmed",
    name="Booking Confirmed",
    description="Notification when your booking is confirmed",
    category="booking",
    classification="change",
    default_channels=["email", "push"],
)

BOOKING_CANCELLED_BY_USER = NotificationTypeDef(
    code="booking.cancelled_by_user",
    name="Booking Cancelled",
    description="Notification when you cancel a booking",
    category="booking",
    classification="change",
    default_channels=["email"],
)

BOOKING_CANCELLED_BY_ADMIN = NotificationTypeDef(
    code="booking.cancelled_by_admin",
    name="Booking Cancelled by Admin",
    description="Notification when an admin cancels your booking (shift deleted or regenerated)",
    category="booking",
    classification="change",
    default_channels=["email", "push"],
)

BOOKING_SHIFT_COBOOKED = NotificationTypeDef(
    code="booking.shift_cobooked",
    name="Shift Co-booked",
    description="Notification when someone else also books a shift you are on",
    category="booking",
    classification="announcement",
    default_channels=["push"],
)

BOOKING_REMINDER = NotificationTypeDef(
    code="booking.reminder",
    name="Booking Reminder",
    description="Reminder before a booked shift starts",
    category="booking",
    classification="reminder",
    default_channels=["push"],
    is_user_configurable=False,
)

# ── Shift notifications ────────────────────────────────────────────

SHIFT_STARTING_SOON_UNFILLED = NotificationTypeDef(
    code="shift.starting_soon_unfilled",
    name="Shift Starting Soon (Unfilled)",
    description="Alert when a shift starts in 30 minutes but still has open spots",
    category="shift",
    classification="reminder",
    is_admin_only=True,
    default_channels=["email", "push"],
)

SHIFT_TIME_CHANGED = NotificationTypeDef(
    code="shift.time_changed",
    name="Shift Time Changed",
    description="Notification when a shift you booked has its time changed",
    category="shift",
    classification="change",
    default_channels=["email", "push"],
)

# ── Task notifications ───────────────────────────────────────────

TASK_PUBLISHED = NotificationTypeDef(
    code="task.published",
    name="Task Published",
    description="Notification when a new task is published",
    category="task",
    classification="match",
    default_channels=["email"],
)

# ── Task group notifications ─────────────────────────────────────

EVENT_PUBLISHED = NotificationTypeDef(
    code="event.published",
    name="Event Published",
    description="Notification when a new event is published",
    category="event",
    classification="match",
    default_channels=["email"],
)

EVENT_CLONED = NotificationTypeDef(
    code="event.cloned",
    name="Event Cloned",
    description=(
        "Notification when an event you were carried over to was set up from "
        "an existing one"
    ),
    category="event",
    # "match", like event.published: the recipient is being told a thing they
    # can take part in now exists. "announcement" is the catch-all for notices
    # that need no action, and "change" is for something they already hold
    # having moved — neither fits an event they have just been added to.
    classification="match",
    default_channels=["email"],
)

# ── Availability notifications ────────────────────────────────────

AVAILABILITY_REMINDER = NotificationTypeDef(
    code="availability.reminder",
    name="Availability Reminder",
    description="Reminder to submit your availability for a published event",
    category="availability",
    classification="reminder",
    default_channels=["email", "push"],
)

# ── Event membership notifications ────────────────────────────────

EVENT_INVITATION = NotificationTypeDef(
    code="event.invitation",
    name="Event Invitation",
    description="Notification when someone invites you to an event",
    category="event",
    classification="match",
    default_channels=["email", "push"],
)

EVENT_INVITATION_ACCEPTED = NotificationTypeDef(
    code="event.invitation_accepted",
    name="Invitation Accepted",
    description="Notification when someone you invited joins your event",
    category="event",
    classification="announcement",
    default_channels=["push"],
)

EVENT_JOIN_REQUESTED = NotificationTypeDef(
    code="event.join_requested",
    name="Join Request",
    description="Notification when someone asks to join an event you manage",
    category="event",
    classification="announcement",
    default_channels=["email", "push"],
)

EVENT_JOIN_APPROVED = NotificationTypeDef(
    code="event.join_approved",
    name="Join Request Approved",
    description="Notification when your request to join an event is approved",
    category="event",
    classification="change",
    default_channels=["email", "push"],
)

EVENT_JOIN_DECLINED = NotificationTypeDef(
    code="event.join_declined",
    name="Join Request Declined",
    description="Notification when your request to join an event is declined",
    category="event",
    classification="change",
    default_channels=["email"],
)

EVENT_ROLE_CHANGED = NotificationTypeDef(
    code="event.role_changed",
    name="Role Changed",
    description="Notification when your role in an event changes",
    category="event",
    classification="change",
    default_channels=["email", "push"],
)

# ── User / admin notifications ────────────────────────────────────

USER_REINSTATED = NotificationTypeDef(
    code="user.reinstated",
    name="Account Reinstated",
    description="Notification when a suspended account is restored",
    category="user",
    classification="change",
    default_channels=["email", "push"],
)

USER_SUSPENDED = NotificationTypeDef(
    code="user.suspended",
    name="Account Suspended",
    description="Notification when your account is suspended by an administrator",
    category="user",
    classification="change",
    default_channels=["email"],
)

# ── All types registry ────────────────────────────────────────────

ALL_NOTIFICATION_TYPES: list[NotificationTypeDef] = [
    BOOKING_CONFIRMED,
    BOOKING_CANCELLED_BY_USER,
    BOOKING_CANCELLED_BY_ADMIN,
    BOOKING_SHIFT_COBOOKED,
    BOOKING_REMINDER,
    SHIFT_STARTING_SOON_UNFILLED,
    SHIFT_TIME_CHANGED,
    TASK_PUBLISHED,
    EVENT_PUBLISHED,
    AVAILABILITY_REMINDER,
    EVENT_INVITATION,
    EVENT_INVITATION_ACCEPTED,
    EVENT_JOIN_REQUESTED,
    EVENT_JOIN_APPROVED,
    EVENT_JOIN_DECLINED,
    EVENT_ROLE_CHANGED,
    USER_REINSTATED,
    USER_SUSPENDED,
    EVENT_CLONED,
]


_CLASSIFICATION_BY_CODE: dict[str, NotificationClassification] = {
    t.code: t.classification for t in ALL_NOTIFICATION_TYPES
}


def classification_for_code(code: str) -> NotificationClassification:
    """Resolve a notification's classification from its type code.

    Falls back to "announcement" for unknown codes (e.g. retired types
    that may still exist on persisted notifications).
    """
    return _CLASSIFICATION_BY_CODE.get(code, "announcement")
