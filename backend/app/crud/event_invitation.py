import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.event_invitation import EventInvitation
from app.schemas.event_membership import AssignableEventRole


def _now() -> datetime:
    """Naive UTC, matching how every other timestamp in the app is stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CRUDEventInvitation:
    async def get_by_token(
        self,
        session: AsyncSession,
        *,
        token: str,
    ) -> EventInvitation | None:
        result = await session.execute(
            select(EventInvitation).where(col(EventInvitation.token) == token)
        )
        return result.scalar_one_or_none()

    async def get(
        self,
        session: AsyncSession,
        *,
        invitation_id: uuid.UUID,
    ) -> EventInvitation | None:
        result = await session.execute(
            select(EventInvitation).where(col(EventInvitation.id) == invitation_id)
        )
        return result.scalar_one_or_none()

    async def list_open_for_event(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
    ) -> list[EventInvitation]:
        """Invitations still worth showing: neither revoked nor used up."""
        result = await session.execute(
            select(EventInvitation)
            .where(
                col(EventInvitation.event_id) == event_id,
                col(EventInvitation.revoked_at).is_(None),
                col(EventInvitation.accepted_at).is_(None),
            )
            .order_by(col(EventInvitation.created_at).desc())
        )
        return list(result.scalars().all())

    async def list_pending_for_email(
        self,
        session: AsyncSession,
        *,
        email: str,
    ) -> list[EventInvitation]:
        """Open, valid targeted invites addressed to this email, in any event.

        The registration gate counts these (``has_valid_invitation``): an
        address an event admin invited may sign up even without the link.
        """
        now = _now()
        result = await session.execute(
            select(EventInvitation).where(
                func.lower(col(EventInvitation.email)) == email.lower(),
                col(EventInvitation.revoked_at).is_(None),
                col(EventInvitation.accepted_at).is_(None),
                or_(
                    col(EventInvitation.expires_at).is_(None),
                    col(EventInvitation.expires_at) > now,
                ),
            )
        )
        return list(result.scalars().all())

    async def create(
        self,
        session: AsyncSession,
        *,
        event_id: uuid.UUID,
        email: str | None,
        role: AssignableEventRole,
        invited_by_id: uuid.UUID | None,
        expires_in_days: int | None,
        for_tasks_only: bool = False,
    ) -> EventInvitation:
        expires_at = (
            _now() + timedelta(days=expires_in_days)
            if expires_in_days is not None
            else None
        )
        obj = EventInvitation(
            event_id=event_id,
            email=email.lower() if email else None,
            role=role,
            token=secrets.token_urlsafe(32),
            invited_by_id=invited_by_id,
            expires_at=expires_at,
            for_tasks_only=for_tasks_only,
        )
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj

    async def mark_redeemed(
        self,
        session: AsyncSession,
        *,
        invitation: EventInvitation,
        user_id: uuid.UUID,
    ) -> EventInvitation:
        """Record a redemption.

        A targeted invite is closed outright; a share link only counts up, so
        it stays usable for the next person.
        """
        invitation.use_count += 1
        if invitation.email is not None:
            invitation.accepted_at = _now()
            invitation.accepted_by_id = user_id
        session.add(invitation)
        await session.flush()
        await session.refresh(invitation)
        return invitation

    async def revoke(
        self,
        session: AsyncSession,
        *,
        invitation: EventInvitation,
    ) -> EventInvitation:
        invitation.revoked_at = _now()
        session.add(invitation)
        await session.flush()
        await session.refresh(invitation)
        return invitation


def invitation_invalid_reason(invitation: EventInvitation) -> str | None:
    """Why this invitation cannot be redeemed, or None if it can be."""
    if invitation.revoked_at is not None:
        return "revoked"
    if invitation.accepted_at is not None:
        return "already_used"
    if invitation.expires_at is not None and invitation.expires_at <= _now():
        return "expired"
    return None


event_invitation = CRUDEventInvitation()
