"""Reading who signed up through shared lists: the organisers' table of one
list's sign-ups, and the operator's lookup and export of guest data.

Both are plain SQL with ORDER BY, OFFSET and LIMIT. Which rows an organiser
sees is decided by the caller through the shared-list gates and passed in as
task ids; ``None`` there means every task, for event admins only, and an empty
set means none.

A sign-up shows its own person (``crud.booking.person_name``), never the
guest user's: a guest account pools the sign-ups of everyone who confirmed
one address.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import (
    ColumnElement,
    Select,
    SQLColumnExpression,
    UnaryExpression,
    and_,
    case,
    exists,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlmodel import col

from app.crud.booking import person_name, person_name_sql, person_phone
from app.crud.search import like_pattern
from app.logic.shared_lists import guest_vouchers
from app.logic.shared_lists.guest_manage import bookings_of
from app.logic.shared_lists.normalize import normalize_email
from app.logic.work_hours import shift_ends_at
from app.models.booking import Booking
from app.models.event import Event
from app.models.shared_list import SharedList, SharedListGuest
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User
from app.schemas.shared_list import SortDir
from app.schemas.shared_list_guest import (
    ListGuestAdminRow,
    ListGuestExport,
    ListGuestExportBooking,
    SharedListSignup,
    SignupSort,
)

# The rows as they come back: the contact row is outer-joined, since a guest
# whose event was deleted has none.
_SignupRow = tuple[Booking, User, SharedListGuest | None, Shift, Task, bool, int]
_GuestRow = tuple[User, SharedListGuest | None, str | None, int]


def _ordered(
    key: SQLColumnExpression[Any], *, descending: bool, nulls_first: bool = False
) -> UnaryExpression[Any]:
    ordered = key.desc() if descending else key.asc()
    return ordered.nulls_first() if nulls_first else ordered.nulls_last()


def _possible_duplicate() -> ColumnElement[bool]:
    """Another confirmed guest sign-up of the same name, through any list, is
    on the shift of the Booking row."""
    other = aliased(Booking, name="dup_booking")
    other_user = aliased(User, name="dup_user")
    same_name = (
        select(func.count())
        .select_from(other)
        .join(other_user, col(other_user.id) == col(other.user_id))
        .where(
            col(other.shift_id) == col(Booking.shift_id),
            col(other.status) == "confirmed",
            col(other_user.is_list_guest),
            func.lower(person_name_sql(other, other_user))
            == func.lower(person_name_sql()),
        )
        .correlate(Booking, User)
        .scalar_subquery()
    )
    return same_name > 1


def _pooled_signups() -> ColumnElement[int]:
    """The other confirmed sign-ups of the Booking row's guest, when that
    guest is a live guest account; 0 otherwise. Erasing the account's data
    takes them along."""
    other = aliased(Booking, name="pooled_booking")
    others = (
        select(func.count())
        .select_from(other)
        .where(
            col(other.user_id) == col(Booking.user_id),
            col(other.status) == "confirmed",
            col(other.id) != col(Booking.id),
        )
        .correlate(Booking)
        .scalar_subquery()
    )
    live_account = and_(
        col(SharedListGuest.confirmed_at).is_not(None),
        col(SharedListGuest.erased_at).is_(None),
    )
    return case((live_account, others), else_=0)


def _signups_through(shared_list: SharedList) -> Select[int]:
    """Confirmed sign-ups through the list on tasks still in its event: a
    task moved away takes its bookings out of this list's view."""
    return (
        select(func.count())
        .select_from(Booking)
        .join(User, col(User.id) == col(Booking.user_id))
        .outerjoin(SharedListGuest, col(SharedListGuest.user_id) == col(User.id))
        .join(Shift, col(Shift.id) == col(Booking.shift_id))
        .join(Task, col(Task.id) == col(Shift.task_id))
        .where(
            col(Booking.shared_list_id) == shared_list.id,
            col(Booking.status) == "confirmed",
            col(Task.event_id) == shared_list.event_id,
        )
    )


async def list_signups(
    session: AsyncSession,
    *,
    shared_list: SharedList,
    task_ids: frozenset[uuid.UUID] | None,
    q: str | None,
    sort_by: SignupSort,
    sort_dir: SortDir | None,
    skip: int,
    limit: int,
    now_wall: dt.datetime,
) -> tuple[list[SharedListSignup], int, int]:
    """One page of the list's sign-ups, their total, and how many are hidden.

    ``task_ids`` None shows every task (event admins); otherwise only sign-ups
    on those tasks are listed, and the rest are counted as hidden. ``q``
    matches the sign-up's name and the address, which the caller may see on
    every row listed. ``now_wall`` is the event's clock, for ``can_remove``.
    """
    base = _signups_through(shared_list)
    hidden = 0
    if task_ids is not None:
        hidden = (await session.scalar(base.where(col(Task.id).not_in(task_ids)))) or 0
        base = base.where(col(Task.id).in_(task_ids))
    if q:
        pattern = like_pattern(q)
        base = base.where(
            or_(
                person_name_sql().ilike(pattern),
                col(SharedListGuest.email).ilike(pattern),
            )
        )
    total = (await session.scalar(base)) or 0

    descending = (sort_dir or ("desc" if sort_by == "created_at" else "asc")) == "desc"
    if sort_by == "created_at":
        order = [_ordered(col(Booking.created_at), descending=descending)]
    elif sort_by == "name":
        # Erased guests, who have no name, last.
        order = [_ordered(func.lower(person_name_sql()), descending=descending)]
    else:
        # A shift without a start time starts with its day.
        order = [
            _ordered(col(Shift.date), descending=descending),
            _ordered(
                col(Shift.start_time), descending=descending, nulls_first=not descending
            ),
        ]
    rows = await session.execute(
        base.with_only_columns(
            Booking,
            User,
            SharedListGuest,
            Shift,
            Task,
            _possible_duplicate(),
            _pooled_signups(),
        )
        .order_by(*order, col(Booking.id))
        .offset(skip)
        .limit(limit)
    )
    items = [
        SharedListSignup(
            booking_id=booking.id,
            name=person_name(booking, user),
            erased=guest is None or guest.erased_at is not None,
            email=guest.email if guest is not None else None,
            phone=person_phone(booking, user),
            task_id=task.id,
            task_name=task.name,
            shift_id=shift.id,
            shift_date=shift.date,
            start_time=shift.start_time,
            end_time=shift.end_time,
            created_at=booking.created_at,
            possible_duplicate=bool(duplicate),
            can_remove=shift_ends_at(shift.date, shift.start_time, shift.end_time)
            > now_wall,
            pooled_signups=pooled,
        )
        for booking, user, guest, shift, task, duplicate, pooled in cast(
            Sequence[_SignupRow], rows.all()
        )
    ]
    return items, total, hidden


# ── The operator's lookup ─────────────────────────────────────────


def _booking_count() -> ColumnElement[int]:
    return (
        select(func.count())
        .where(col(Booking.user_id) == col(User.id))
        .correlate(User)
        .scalar_subquery()
    )


def _admin_row(
    user: User, guest: SharedListGuest | None, event_name: str | None, bookings: int
) -> ListGuestAdminRow:
    return ListGuestAdminRow(
        guest_user_id=user.id,
        name=user.name,
        email=guest.email if guest is not None else None,
        phone=user.phone_number,
        event_id=guest.event_id if guest is not None else None,
        event_name=event_name,
        booking_count=bookings,
        last_signup_at=guest.last_signup_at if guest is not None else None,
        # Without a contact row (its event was deleted) only the name is left
        # to tell.
        erased=guest.erased_at is not None if guest is not None else user.name is None,
    )


def _guests() -> Select[User, SharedListGuest, str, int]:
    return (
        select(User, SharedListGuest, col(Event.name), _booking_count())
        .outerjoin(SharedListGuest, col(SharedListGuest.user_id) == col(User.id))
        .outerjoin(Event, col(Event.id) == col(SharedListGuest.event_id))
        .where(col(User.is_list_guest))
    )


async def search_guests(
    session: AsyncSession, *, q: str, skip: int, limit: int
) -> tuple[list[ListGuestAdminRow], int]:
    """Guests matching ``q``: the address exactly, once normalised, or a part
    of the name or the phone number, the guest's or one of their sign-ups'
    (a pooled account holds sign-ups under other names). Their address is not
    in ``users.email``, so the admin user search never finds them."""
    pattern = like_pattern(q)
    matches: list[ColumnElement[bool]] = [
        col(User.name).ilike(pattern),
        col(User.phone_number).ilike(pattern),
        exists().where(
            col(Booking.user_id) == col(User.id),
            or_(
                col(Booking.guest_name).ilike(pattern),
                col(Booking.guest_phone).ilike(pattern),
            ),
        ),
    ]
    try:
        email = normalize_email(q)
    except ValueError:
        pass
    else:
        matches.append(func.lower(col(SharedListGuest.email)) == email)
    query = _guests().where(or_(*matches))
    total = (
        await session.scalar(select(func.count()).select_from(query.subquery()))
    ) or 0
    rows = await session.execute(
        query.order_by(
            col(SharedListGuest.last_signup_at).desc().nulls_last(), col(User.id)
        )
        .offset(skip)
        .limit(limit)
    )
    return [_admin_row(*row) for row in cast(Sequence[_GuestRow], rows.all())], total


async def export_guest(
    session: AsyncSession, *, user_id: uuid.UUID
) -> ListGuestExport | None:
    """Everything stored about one guest; None for anyone who is not one."""
    row = cast(
        _GuestRow | None,
        (await session.execute(_guests().where(col(User.id) == user_id))).first(),
    )
    if row is None:
        return None
    user, guest, event_name, bookings = row
    return ListGuestExport(
        **_admin_row(user, guest, event_name, bookings).model_dump(),
        preferred_language=user.preferred_language,
        shared_list_id=guest.shared_list_id if guest is not None else None,
        created_at=user.created_at,
        erased_at=guest.erased_at if guest is not None else None,
        confirmed_at=guest.confirmed_at if guest is not None else None,
        bookings=[
            ListGuestExportBooking(**shown.model_dump(), phone=booking.guest_phone)
            for booking, shown in await bookings_of(session, user_id=user.id)
        ],
        vouchers=await guest_vouchers.guest_vouchers(
            session,
            user_id=user.id,
            own_event_id=guest.event_id if guest is not None else None,
        ),
    )
