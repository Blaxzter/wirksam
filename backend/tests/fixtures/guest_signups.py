"""Helpers for the tests of signing up through a shared list (plain functions,
not fixtures, like ``make_png`` in ``locations.py``).

The fixture event runs 10-14 June 2026 and its shift (``test_shift``) lies in
May, so these tests freeze both clocks at :data:`NOW_UTC`: early on 1 June,
after ``test_shift`` and before every shift added here. Reminders a day before
a June shift are then still ahead (``pending``), as they would be for real.
"""

import datetime as dt
import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.logic import clock
from app.logic.shared_lists import guest_account, guest_tokens
from app.logic.shared_lists.guest_tokens import GuestKey
from app.models.shared_list import SharedList, SharedListGuest
from app.models.shift import Shift
from app.models.task import Task
from tests.fixtures.clock import set_instant
from tests.fixtures.shared_lists import ListGuest, ListGuestFactory

#: 08:00 on 1 June 2026 in Berlin.
NOW_UTC = dt.datetime(2026, 6, 1, 6, 0)


def freeze_clocks(monkeypatch: pytest.MonkeyPatch, utc: dt.datetime = NOW_UTC) -> None:
    """Both clocks at ``utc``: the wall clock of every zone and ``utc_now``."""
    set_instant(monkeypatch, utc)


def configure_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make guest mail count as deliverable; tests replace the sending itself."""
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(settings, "EMAILS_FROM_EMAIL", "sender@example.test")


def disable_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SMTP_HOST", None)


async def add_shift(
    db: AsyncSession,
    task: Task,
    *,
    day: dt.date = dt.date(2026, 6, 11),
    start: dt.time | None = dt.time(10, 0),
    end: dt.time | None = dt.time(12, 0),
    max_bookings: int = 2,
    location: str | None = "Foyer",
) -> Shift:
    shift = Shift(
        task_id=task.id,
        title=f"{task.name} {day} {start}",
        date=day,
        start_time=start,
        end_time=end,
        max_bookings=max_bookings,
        location=location,
    )
    db.add(shift)
    await db.flush()
    return shift


def signup_body(shift: Shift, **fields: Any) -> dict[str, Any]:
    """A sign-up form for ``shift``, from a page that names nobody; ``fields``
    override the defaults."""
    body: dict[str, Any] = {
        "shift_id": str(shift.id),
        "name": "Anna Gast",
        "email": f"anna-{uuid.uuid4().hex[:6]}@example.org",
        "language": "de",
        "show_names": "none",
    }
    body.update(fields)
    return body


async def confirm_address(db: AsyncSession, guest: SharedListGuest) -> GuestKey:
    """Press "Ja, das bin ich" on the link in the chain's mail, as the route
    does: the token is verified first, then confirmed. Returns the account."""
    token = guest_tokens.mail_token(guest)
    peeked = await guest_tokens.peek(db, token)
    assert peeked is not None
    return await guest_account.confirm(
        db, peeked=peeked, token=token, now=clock.utc_now()
    )


async def pooled_family(
    db: AsyncSession,
    shared_list: SharedList,
    make_list_guest: ListGuestFactory,
    first: Shift,
    second: Shift,
) -> tuple[ListGuest, ListGuest]:
    """Maria on ``first`` and Tom on ``second``, with one address and a
    phone each, and Tom's sign-up confirmed into Maria's guest account: one
    guest user, two people."""
    maria = await make_list_guest(
        shared_list,
        name="Maria Muster",
        email="fam@example.org",
        phone="0170 1",
        shifts=[first],
    )
    tom = await make_list_guest(
        shared_list,
        name="Tom Muster",
        email="fam@example.org",
        phone="0170 2",
        shifts=[second],
    )
    await confirm_address(db, maria.guest)
    await confirm_address(db, tom.guest)
    return maria, tom
