"""
SQLModel imports and base classes for the application.

This module provides the base SQLModel class and imports for database models.
"""

from sqlmodel import SQLModel

from .auth_session import AuthSession
from .base import Base  # Import the Base model for common fields and functionality
from .booking import Booking
from .booking_reminder import BookingReminder
from .calendar_feed import CalendarFeedToken
from .event import Event
from .event_invitation import EventInvitation
from .event_join_request import EventJoinRequest
from .event_membership import EventMembership
from .location import Location
from .notification import (
    Notification,
    NotificationSubscription,
    NotificationType,
    PushSubscription,
    TelegramBinding,
)
from .shift import Shift
from .shift_batch import ShiftBatch
from .task import Task
from .user import User
from .user_availability import UserAvailability, UserAvailabilityDate
from .user_avatar import UserAvatar
from .user_token import UserToken
from .venue_plan import VenueMarker, VenuePlan, VenuePlanImage, VenueShape
from .venue_template import VenueTemplate, VenueTemplateImage

__all__ = [
    "SQLModel",
    "Base",
    "AuthSession",
    "Booking",
    "BookingReminder",
    "CalendarFeedToken",
    "Shift",
    "Task",
    "Event",
    "EventInvitation",
    "EventJoinRequest",
    "EventMembership",
    "Location",
    "Notification",
    "NotificationSubscription",
    "NotificationType",
    "PushSubscription",
    "ShiftBatch",
    "TelegramBinding",
    "User",
    "UserAvailability",
    "UserAvailabilityDate",
    "UserAvatar",
    "UserToken",
    "VenueMarker",
    "VenuePlan",
    "VenuePlanImage",
    "VenueShape",
    "VenueTemplate",
    "VenueTemplateImage",
]
