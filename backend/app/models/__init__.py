"""
SQLModel imports and base classes for the application.

This module provides the base SQLModel class and imports for database models.
"""

from sqlmodel import SQLModel

from .base import Base  # Import the Base model for common fields and functionality
from .booking import Booking
from .duty_slot import DutySlot
from .event import Event
from .event_group import EventGroup
from .notification import (
    Notification,
    NotificationSubscription,
    NotificationType,
    PushSubscription,
    TelegramBinding,
)
from .site_settings import SiteSettings
from .slot_batch import SlotBatch
from .user import User
from .user_availability import UserAvailability, UserAvailabilityDate

__all__ = [
    "SQLModel",
    "Base",
    "Booking",
    "DutySlot",
    "Event",
    "EventGroup",
    "Notification",
    "NotificationSubscription",
    "NotificationType",
    "PushSubscription",
    "SiteSettings",
    "SlotBatch",
    "TelegramBinding",
    "User",
    "UserAvailability",
    "UserAvailabilityDate",
]
