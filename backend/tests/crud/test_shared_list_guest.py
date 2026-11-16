"""``crud.shared_list_guest``: the guest user and contact row a sign-up chain
starts with, and where the contact address is read from."""

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.shared_list_guest import shared_list_guest as crud_guest
from app.crud.user import user as crud_user
from app.models.shared_list import SharedList
from app.models.shift import Shift
from app.models.user import User
from tests.fixtures.shared_lists import ListGuestFactory, SharedListFactory

NOW = dt.datetime(2026, 6, 1, 12, 0)


@pytest.mark.asyncio
class TestCreate:
    async def test_the_guest_user_can_never_sign_in(
        self, db_session: AsyncSession, test_shared_list: SharedList
    ) -> None:
        guest = await crud_guest.create(
            db_session,
            shared_list=test_shared_list,
            name="Anna Müller",
            email="anna@example.org",
            phone="+49 30 123456",
            language="en",
            now=NOW,
        )
        user = await db_session.get(User, guest.user_id)
        assert user is not None
        assert user.subject.startswith("listguest|")
        assert user.is_list_guest
        assert (user.email, user.password_hash) == (None, None)
        assert (user.name, user.phone_number, user.preferred_language) == (
            "Anna Müller",
            "+49 30 123456",
            "en",
        )
        assert user.default_reminder_offsets == []
        assert not (user.notify_email or user.notify_push or user.notify_telegram)
        assert user.roles == []
        assert (user.approval_status, user.is_active) == ("approved", True)

    async def test_the_contact_row_belongs_to_the_list_it_started_on(
        self, db_session: AsyncSession, test_shared_list: SharedList
    ) -> None:
        guest = await crud_guest.create(
            db_session,
            shared_list=test_shared_list,
            name="Anna",
            email="anna@example.org",
            phone=None,
            language="de",
            now=NOW,
        )
        assert (guest.event_id, guest.shared_list_id) == (
            test_shared_list.event_id,
            test_shared_list.id,
        )
        assert guest.email == "anna@example.org"
        assert guest.last_signup_at == NOW
        assert guest.confirmed_at is None
        assert guest.erased_at is None
        assert guest.manage_nonce is not None
        assert len(guest.manage_nonce) == 32
        int(guest.manage_nonce, 16)

    async def test_each_chain_gets_its_own_nonce_and_user(
        self, test_shared_list: SharedList, make_list_guest: ListGuestFactory
    ) -> None:
        one = await make_list_guest(test_shared_list, email="same@example.org")
        two = await make_list_guest(test_shared_list, email="same@example.org")
        assert one.user.id != two.user.id
        assert one.guest.manage_nonce != two.guest.manage_nonce

    @pytest.mark.parametrize(
        ("show_names", "expected"), [("first", True), ("none", False)]
    )
    async def test_the_first_name_consent_is_what_the_list_said_then(
        self,
        show_names: str,
        expected: bool,
        db_session: AsyncSession,
        make_shared_list: SharedListFactory,
        make_list_guest: ListGuestFactory,
        test_shift: Shift,
    ) -> None:
        """Stored on the booking, so changing the list later changes nothing."""
        shared_list = await make_shared_list(
            show_names="first" if show_names == "first" else "none"
        )
        signed_up = await make_list_guest(shared_list, shifts=[test_shift])
        shared_list.show_names = "none" if expected else "first"
        await db_session.flush()
        [booking] = signed_up.bookings
        await db_session.refresh(booking)
        assert booking.show_first_name is expected

    async def test_the_address_is_not_a_login(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        make_list_guest: ListGuestFactory,
    ) -> None:
        await make_list_guest(test_shared_list, email="nobody-else@example.org")
        assert (
            await crud_user.get_by_email(db_session, email="nobody-else@example.org")
            is None
        )


@pytest.mark.asyncio
class TestLookups:
    async def test_by_user_id_with_and_without_lock(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_user: User,
        make_list_guest: ListGuestFactory,
    ) -> None:
        signed_up = await make_list_guest(test_shared_list)
        assert (
            await crud_guest.get_by_user_id(db_session, user_id=signed_up.user.id)
            is signed_up.guest
        )
        assert (
            await crud_guest.get_for_update(db_session, user_id=signed_up.user.id)
            is signed_up.guest
        )
        assert await crud_guest.get_by_user_id(db_session, user_id=test_user.id) is None

    async def test_contact_emails_only_for_guests_who_gave_one(
        self,
        db_session: AsyncSession,
        test_shared_list: SharedList,
        test_user: User,
        make_list_guest: ListGuestFactory,
    ) -> None:
        with_address = await make_list_guest(test_shared_list, email="a@example.org")
        without = await make_list_guest(test_shared_list, name="Ohne Adresse")

        emails = await crud_guest.contact_emails(
            db_session,
            user_ids=[with_address.user.id, without.user.id, test_user.id],
        )

        assert emails == {with_address.user.id: "a@example.org"}
        assert await crud_guest.contact_emails(db_session, user_ids=[]) == {}
