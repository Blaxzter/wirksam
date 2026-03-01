"""Unit tests for Booking CRUD operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.booking import booking as crud_booking
from app.models.booking import Booking
from app.schemas.booking import BookingBase, BookingUpdate


@pytest.mark.asyncio
class TestCRUDBooking:
    """Test suite for Booking CRUD operations."""

    async def test_create_booking(self, db_session: AsyncSession, test_duty_slot, test_user):
        """Test creating a new booking."""
        booking_in = BookingBase(
            duty_slot_id=test_duty_slot.id,
            user_id=test_user.id,
        )
        booking = await crud_booking.create(db_session, obj_in=booking_in)

        assert booking.status == "confirmed"
        assert booking.user_id == test_user.id
        assert booking.duty_slot_id == test_duty_slot.id
        assert booking.id is not None

    async def test_get_by_slot_and_user(
        self, db_session: AsyncSession, test_booking: Booking
    ):
        """Test finding a booking by slot and user."""
        found = await crud_booking.get_by_slot_and_user(
            db_session,
            duty_slot_id=test_booking.duty_slot_id,
            user_id=test_booking.user_id,
        )

        assert found is not None
        assert found.id == test_booking.id

    async def test_get_by_slot_and_user_not_found(
        self, db_session: AsyncSession, test_duty_slot, test_admin_user
    ):
        """Test searching for a non-existent booking by slot and user."""
        found = await crud_booking.get_by_slot_and_user(
            db_session,
            duty_slot_id=test_duty_slot.id,
            user_id=test_admin_user.id,
        )

        assert found is None

    async def test_get_confirmed_count(
        self, db_session: AsyncSession, test_booking: Booking
    ):
        """Test counting confirmed bookings for a slot."""
        count = await crud_booking.get_confirmed_count(
            db_session, duty_slot_id=test_booking.duty_slot_id
        )

        assert count == 1

    async def test_cancel_booking(self, db_session: AsyncSession, test_booking: Booking):
        """Test cancelling a booking and verifying confirmed count."""
        updated = await crud_booking.update(
            db_session,
            db_obj=test_booking,
            obj_in=BookingUpdate(status="cancelled"),
        )

        assert updated.status == "cancelled"

        count = await crud_booking.get_confirmed_count(
            db_session, duty_slot_id=test_booking.duty_slot_id
        )
        assert count == 0

    async def test_get_multi_by_user(
        self, db_session: AsyncSession, test_booking: Booking, test_user
    ):
        """Test getting bookings for a specific user."""
        bookings = await crud_booking.get_multi_by_user(
            db_session, user_id=test_user.id
        )

        assert len(bookings) >= 1
        assert all(b.user_id == test_user.id for b in bookings)

    async def test_count_by_user(
        self, db_session: AsyncSession, test_booking: Booking, test_user
    ):
        """Test counting bookings for a specific user."""
        count = await crud_booking.count_by_user(
            db_session, user_id=test_user.id
        )

        assert count >= 1
