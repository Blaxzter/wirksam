"""Abstract base class for notification delivery channels."""

from abc import ABC, abstractmethod

from app.models.user import User
from app.schemas.notification import NotificationData

# Identity prefixes that must never be sent anything, whatever the channel.
# All three mark accounts that stand in for a person without being one: the
# made-up teammates ``just seed`` puts in the local dev event, the accounts the
# E2E reset endpoint owns, and the guests behind the "try a test event" button.
UNDELIVERABLE_SUBJECT_PREFIXES = ("demo|", "test|", "sandbox|")


def is_undeliverable(recipient: User) -> bool:
    """Whether this account must never be contacted.

    Lives here, once, because it used to live three times - copied into the
    email, push and Telegram channels - and a fourth channel would have shipped
    without it. Any new channel gets the check by calling this.
    """
    return recipient.subject.startswith(UNDELIVERABLE_SUBJECT_PREFIXES)


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
