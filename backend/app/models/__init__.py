"""
SQLModel imports and base classes for the application.

This module provides the base SQLModel class and imports for database models.
"""

from sqlmodel import SQLModel

from .base import Base  # Import the Base model for common fields and functionality
from .booking import Booking
from .duty_slot import DutySlot
from .event import Event
from .user import User

__all__ = [
    "SQLModel",
    "Base",
    "Booking",
    "DutySlot",
    "Event",
    "User",
]
