"""The "you're in charge" e-mail (``task.manager_added``).

``InChargeMail.render`` is plain data in, text and HTML out, so most cases need
no database. ``load_in_charge_mail`` is checked against real rows for what it
reads: the shifts' span and count, the place, and who else is in charge.
"""

import datetime as dt
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.logic.notifications.in_charge_mail import InChargeMail, load_in_charge_mail
from app.models.shift import Shift
from app.models.task import Task
from app.models.task_manager import TaskManager
from app.models.user import User

PIA = uuid.uuid4()
MIRA = uuid.uuid4()
TASK = uuid.uuid4()


@contextmanager
def _host() -> Generator[None, None, None]:
    # A date in the current year is written without it, so "now" is pinned
    # to the summer the tasks below run in.
    with (
        patch.object(settings, "FRONTEND_HOST", "https://app.example.test"),
        patch("app.logic.clock.wall_clock_now", lambda: dt.datetime(2026, 7, 1, 9)),
    ):
        yield


def _mail(
    *,
    task_name: str = "Cafétheke",
    actor: str | None = "Anna Berger",
    location: str | None = "Foyer-Café",
    first: dt.date = dt.date(2026, 7, 17),
    last: dt.date = dt.date(2026, 7, 19),
    shift_count: int = 8,
    managers: tuple[tuple[uuid.UUID, str], ...] = (
        (MIRA, "Mira Lindqvist"),
        (PIA, "Pia"),
    ),
    is_voucher_point: bool = True,
) -> InChargeMail:
    return InChargeMail(
        task_id=TASK,
        task_name=task_name,
        event_name="Sommerfest am Fluss",
        actor=actor,
        location=location,
        first_date=first,
        last_date=last,
        shift_count=shift_count,
        managers=managers,
        is_voucher_point=is_voucher_point,
    )


def _pia(*, language: str = "de", name: str | None = "Pia") -> User:
    return User(
        id=PIA,
        subject="local|pia",
        email="pia@example.org",
        name=name,
        roles=[],
        is_active=True,
        preferred_language=language,
    )


class TestRender:
    def test_german_mail_follows_the_design(self) -> None:
        with _host():
            body = _mail().render(_pia())

        assert body.text == (
            "Hallo Pia,\n\n"
            "Anna Berger hat dich bei „Sommerfest am Fluss“ für „Cafétheke“ "
            "eingetragen.\n\n"
            "Aufgabe: Cafétheke\n"
            "Ort: Foyer-Café\n"
            "Wann: Fr, 17. – So, 19. Juli · 8 Schichten\n"
            "Auch verantwortlich: Mira Lindqvist\n\n"
            "Das kannst du jetzt\n"
            "- Beschreibung und Infos der Aufgabe ändern\n"
            "- sehen, wer Schicht hat, und die Leute erreichen\n"
            "- bei „Cafétheke“ Marken einlösen\n\n"
            f"Aufgabe öffnen:\nhttps://app.example.test/app/tasks/{TASK}\n\n"
            "Passt das nicht? Du kannst die Verantwortung auf der Aufgabe abgeben."
        )
        assert (
            "Du bist jetzt verantwortlich für Cafétheke · Sommerfest am Fluss"
            in body.html
        )
        assert f"https://app.example.test/app/tasks/{TASK}" in body.html
        assert "Aufgabe öffnen" in body.html
        assert "Fr, 17. – So, 19. Juli · 8 Schichten</td>" in body.html
        assert '<html lang="de">' in body.html

    def test_english_mail(self) -> None:
        with _host():
            body = _mail().render(_pia(language="en"))

        assert body.text.startswith(
            "Hi Pia,\n\nAnna Berger put you in charge of “Cafétheke” at "
            "“Sommerfest am Fluss”."
        )
        assert "When: Fri 17 – Sun 19 July · 8 shifts" in body.text
        assert "Also in charge: Mira Lindqvist" in body.text
        assert "Redeem vouchers at “Cafétheke”" in body.text
        assert "Open task" in body.html

    def test_leaves_out_what_does_not_apply(self) -> None:
        """No place, no one else in charge, no vouchers, one day, no name."""
        with _host():
            body = _mail(
                location=None,
                managers=((PIA, "Pia"),),
                is_voucher_point=False,
                last=dt.date(2026, 7, 17),
                shift_count=1,
            ).render(_pia(name=None))

        assert body.text.startswith("Hallo,\n\n")
        assert "Ort:" not in body.text
        assert "Auch verantwortlich" not in body.text
        assert "Marken" not in body.text
        assert "Wann: Fr, 17. Juli · 1 Schicht\n" in body.text

    def test_no_shifts_yet_gives_just_the_dates(self) -> None:
        with _host():
            body = _mail(shift_count=0).render(_pia())

        assert "Wann: Fr, 17. – So, 19. Juli\n" in body.text

    def test_an_organiser_who_is_gone_reads_as_someone(self) -> None:
        with _host():
            body = _mail(actor=None).render(_pia())

        assert "Jemand hat dich bei" in body.text

    def test_names_are_escaped_in_the_html(self) -> None:
        with _host():
            body = _mail(
                task_name="<b>Bar</b>", managers=((MIRA, "<i>Mira</i>"),)
            ).render(_pia())

        assert "<b>" not in body.html
        assert "<i>" not in body.html
        assert "&lt;b&gt;Bar&lt;/b&gt;" in body.html
        assert "&lt;i&gt;Mira&lt;/i&gt;" in body.html

    def test_braces_in_a_task_name_stay_as_typed(self) -> None:
        with _host():
            body = _mail(task_name="{event_name}").render(_pia())

        assert "Aufgabe: {event_name}" in body.text


@pytest.mark.asyncio
class TestLoad:
    async def test_reads_shifts_place_and_people_in_charge(
        self,
        db_session: AsyncSession,
        test_task: Task,
        test_user: User,
        test_event_admin_user: User,
    ) -> None:
        nameless = User(
            subject="local|nameless-in-charge",
            email="nameless.in.charge@example.com",
            name=None,
            roles=[],
            is_active=True,
        )
        db_session.add(nameless)
        await db_session.flush()
        test_task.location = "Foyer-Café"
        db_session.add_all(
            [
                Shift(task_id=test_task.id, title="A", date=dt.date(2026, 6, 13)),
                Shift(task_id=test_task.id, title="B", date=dt.date(2026, 6, 11)),
                Shift(task_id=test_task.id, title="C", date=dt.date(2026, 6, 12)),
            ]
        )
        for user in (test_user, test_event_admin_user, nameless):
            db_session.add(
                TaskManager(
                    task_id=test_task.id,
                    user_id=user.id,
                    added_by_id=test_event_admin_user.id,
                )
            )
        await db_session.flush()

        mail = await load_in_charge_mail(
            db_session, task=test_task, event_name="Fest", actor="Manager User"
        )

        assert (mail.first_date, mail.last_date) == (
            dt.date(2026, 6, 11),
            dt.date(2026, 6, 13),
        )
        assert mail.shift_count == 3
        assert mail.location == "Foyer-Café"
        assert mail.managers == (
            (test_event_admin_user.id, "Manager User"),
            (test_user.id, "Test User"),
        )
        assert mail.is_voucher_point is test_task.is_voucher_point

    async def test_a_task_without_shifts_uses_its_own_dates(
        self, db_session: AsyncSession, test_task: Task
    ) -> None:
        mail = await load_in_charge_mail(
            db_session, task=test_task, event_name="Fest", actor=None
        )

        assert (mail.first_date, mail.last_date) == (
            test_task.start_date,
            test_task.end_date,
        )
        assert mail.shift_count == 0
        assert mail.managers == ()
