"""Abstract base class for notification delivery channels."""

from abc import ABC, abstractmethod

from app.models.user import User
from app.schemas.notification import NotificationData


class NotificationChannel(ABC):
    """Base class for all notification delivery channels.

    Subclasses implement `send()` to deliver notifications via a specific
    medium (email, push, telegram, etc.).
    """

    name: str

    @abstractmethod
    async def send(
        self,
        *,
        recipient: User,
        title: str,
        body: str,
        data: NotificationData | None = None,
    ) -> bool:
        """Deliver a notification to a single recipient.

        Returns True on success, False on failure.
        """
        ...

    def is_configured(self) -> bool:
        """Check if this channel has the required configuration to operate."""
        return True
