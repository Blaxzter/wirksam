import datetime as dt
import secrets
import uuid
from collections.abc import Iterable
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.shared_list import SharedList, SharedListGuest, SharedListGuestAlias
from app.models.user import User

#: The subject prefix of a guest user (``User`` docstring). Behavioural, like
#: ``sandbox|``: what the notification channels refuse to send to.
GUEST_SUBJECT_PREFIX = "listguest|"


class CRUDSharedListGuest:
    """The people who signed up through a shared list without an account.

    One guest user per sign-up chain or guest account, identified by that
    user's id everywhere (manage link, sign-up response, the operator's
    lookup); its contact side is the ``shared_list_guests`` row. Never
    commits; the request owns the transaction.
    """

    async def create(
        self,
        session: AsyncSession,
        *,
        shared_list: SharedList,
        name: str,
        email: str | None,
        phone: str | None,
        language: Literal["en", "de"],
        now: dt.datetime,
    ) -> SharedListGuest:
        """Start a chain: a guest user and its contact row.

        ``name``, ``email`` and ``phone`` are already normalised
        (``logic/shared_lists/normalize.py``). The address goes on the contact
        row only, never into ``users.email``, so the guest stays outside login,
        password reset and every lookup by address; with no password the user
        can never sign in. ``now`` is naive UTC.
        """
        user = User(
            subject=f"{GUEST_SUBJECT_PREFIX}{uuid.uuid4().hex}",
            is_list_guest=True,
            email=None,
            password_hash=None,
            name=name,
            phone_number=phone,
            preferred_language=language,
            default_reminder_offsets=[],
            notify_email=False,
            notify_push=False,
            notify_telegram=False,
            roles=[],
            approval_status="approved",
            is_active=True,
        )
        session.add(user)
        # The guest row has no ORM relationship to order its insert after the
        # user's; flush the user first.
        await session.flush()
        guest = SharedListGuest(
            user_id=user.id,
            event_id=shared_list.event_id,
            shared_list_id=shared_list.id,
            email=email,
            manage_nonce=secrets.token_hex(16),
            last_signup_at=now,
        )
        session.add(guest)
        await session.flush()
        return guest

    async def get_by_user_id(
        self, session: AsyncSession, *, user_id: uuid.UUID
    ) -> SharedListGuest | None:
        result = await session.execute(
            select(SharedListGuest).where(col(SharedListGuest.user_id) == user_id)
        )
        return result.scalar_one_or_none()

    async def get_for_update(
        self, session: AsyncSession, *, user_id: uuid.UUID
    ) -> SharedListGuest | None:
        """The guest's contact row, locked ``FOR UPDATE`` until commit.

        Taken before any shift lock by every path that changes a guest's
        sign-ups or data, so two of them never interleave.
        """
        result = await session.execute(
            select(SharedListGuest)
            .where(col(SharedListGuest.user_id) == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def lock_many(
        self, session: AsyncSession, *, user_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, SharedListGuest]:
        """Several guests' contact rows, locked ``FOR UPDATE`` in one statement
        in user-id order, so two callers locking overlapping sets never wait
        for each other in a circle."""
        result = await session.execute(
            select(SharedListGuest)
            .where(col(SharedListGuest.user_id).in_(set(user_ids)))
            .order_by(col(SharedListGuest.user_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {guest.user_id: guest for guest in result.scalars().all()}

    async def lock_unheld(
        self, session: AsyncSession, *, user_ids: Iterable[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Lock ``FOR UPDATE`` the contact rows of these guests that no other
        transaction holds, and return their user ids. Never waits: a held row
        is skipped, for a caller that can come back for it later."""
        result = await session.execute(
            select(col(SharedListGuest.user_id))
            .where(col(SharedListGuest.user_id).in_(set(user_ids)))
            .with_for_update(skip_locked=True)
        )
        return set(result.scalars().all())

    async def lock_guest_user(
        self, session: AsyncSession, *, user_id: uuid.UUID
    ) -> None:
        """The guest's ``users`` row, ``FOR UPDATE`` until commit.

        Every insert of a row that names the user (an earning, a ledger
        entry, a code) takes ``FOR KEY SHARE`` on it for its foreign key, so
        holding it orders those writers against a merge that moves their
        rows and then deletes the user. A member's row is never locked here.
        """
        await session.execute(
            select(col(User.id))
            .where(col(User.id) == user_id, col(User.is_list_guest))
            .with_for_update()
        )

    async def find_account(
        self, session: AsyncSession, *, event_id: uuid.UUID, email: str
    ) -> SharedListGuest | None:
        """The live guest account of ``email`` (normalised) at the event, not
        locked. Served by ``uq_shared_list_guests_account``."""
        result = await session.execute(
            select(SharedListGuest).where(
                col(SharedListGuest.event_id) == event_id,
                col(SharedListGuest.confirmed_at).is_not(None),
                col(SharedListGuest.erased_at).is_(None),
                func.lower(col(SharedListGuest.email)) == email,
            )
        )
        return result.scalar_one_or_none()

    async def has_live_account(self, session: AsyncSession, *, email: str) -> bool:
        """Whether ``email`` (normalised) has a live guest account at any event.
        Served by ``ix_shared_list_guests_email_lower``."""
        result = await session.execute(
            select(col(SharedListGuest.id))
            .where(
                func.lower(col(SharedListGuest.email)) == email,
                col(SharedListGuest.confirmed_at).is_not(None),
                col(SharedListGuest.erased_at).is_(None),
            )
            .limit(1)
        )
        return result.first() is not None

    async def get_alias(
        self, session: AsyncSession, *, user_id: uuid.UUID
    ) -> SharedListGuestAlias | None:
        """What a chain merged into an account left behind under its former
        user id; None for any other id."""
        result = await session.execute(
            select(SharedListGuestAlias).where(
                col(SharedListGuestAlias.user_id) == user_id
            )
        )
        return result.scalar_one_or_none()

    async def contact_emails(
        self, session: AsyncSession, *, user_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        """``{guest user id: address}`` for those of ``user_ids`` that gave one.

        A guest's address is not in ``users.email``; this is where rosters
        shown to the people in charge read it from.
        """
        ids = set(user_ids)
        if not ids:
            return {}
        result = await session.execute(
            select(col(SharedListGuest.user_id), col(SharedListGuest.email)).where(
                col(SharedListGuest.user_id).in_(ids),
                col(SharedListGuest.email).is_not(None),
            )
        )
        return {user_id: email for user_id, email in result.all() if email}


shared_list_guest = CRUDSharedListGuest()
