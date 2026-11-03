"""The invitation mail to an address that has no account yet.

Driven through ``send_event_invitation_email`` with only the SMTP transport
replaced, as ``test_auth_emails.py`` does for the auth mails, so the subject,
sender, both bodies and the links are read off the message that would have
gone out.
"""

import datetime as dt
import logging
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import parseaddr
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.logic.invitation_emails import InvitedTask, send_event_invitation_email
from app.models.event import Event

TRANSPORT = "app.logic.auth.emails._smtp_send"
TOKEN = "invite-token-123"
INVITE_URL = f"https://app.example.test/invite/{TOKEN}"

EVENT = Event(
    id=uuid.uuid4(),
    name="Sommerfest am Fluss",
    start_date=dt.date(2026, 7, 17),
    end_date=dt.date(2026, 7, 19),
    created_by_id=uuid.uuid4(),
)
CAFE = InvitedTask(
    name="Cafétheke",
    location="Foyer-Café",
    first_date=dt.date(2026, 7, 17),
    last_date=dt.date(2026, 7, 19),
    is_voucher_point=True,
    managers=("Mira Lindqvist", "Pia Incharge"),
)
GRILL = InvitedTask(
    name="Grill",
    location=None,
    first_date=dt.date(2026, 7, 18),
    last_date=dt.date(2026, 7, 18),
    is_voucher_point=False,
)
#: 23:30 UTC on 17.11. is already the 18th in Berlin.
EXPIRES = dt.datetime(2026, 11, 17, 23, 30)


@contextmanager
def _email_settings(*, configured: bool = True) -> Generator[None, None, None]:
    with (
        patch.object(settings, "PROJECT_NAME", "Wirksam Test"),
        patch.object(
            settings, "SMTP_HOST", "smtp.example.test" if configured else None
        ),
        patch.object(
            settings, "EMAILS_FROM_EMAIL", "sender@example.test" if configured else None
        ),
        patch.object(settings, "EMAILS_FROM_NAME", "Wirksam Test Sender"),
        patch.object(settings, "FRONTEND_HOST", "https://app.example.test"),
        patch.object(settings, "EVENT_TIMEZONE", "Europe/Berlin"),
        # A date in the current year is written without it.
        patch("app.logic.clock.wall_clock_now", lambda: dt.datetime(2026, 7, 1, 9)),
    ):
        yield


async def _send(
    *,
    tasks: list[InvitedTask] | None = None,
    inviter_name: str | None = "Anna Berger",
    event: Event = EVENT,
    expires_at: dt.datetime | None = EXPIRES,
    language: str = "de",
) -> EmailMessage:
    with _email_settings(), patch(TRANSPORT, new_callable=AsyncMock) as smtp:
        sent = await send_event_invitation_email(
            email="jonas@example.org",
            inviter_name=inviter_name,
            event=event,
            tasks=tasks if tasks is not None else [CAFE],
            token=TOKEN,
            expires_at=expires_at,
            language=language,
        )
    assert sent is True
    smtp.assert_awaited_once()
    call = smtp.await_args
    assert call is not None
    return cast(EmailMessage, call.args[0])


def _part(message: EmailMessage, subtype: str) -> str:
    part = message.get_body(preferencelist=(subtype,))
    assert part is not None
    content = part.get_content()
    assert isinstance(content, str)
    return content


@pytest.mark.asyncio
class TestTaskInvitation:
    async def test_german_mail_names_the_task_and_who_asks(self) -> None:
        message = await _send()
        assert message["To"] == "jonas@example.org"
        assert message["Subject"] == (
            "[Wirksam Test] Anna Berger bittet dich, „Cafétheke“ zu übernehmen"
        )
        name, address = parseaddr(str(message["From"]))
        assert (name, address) == (
            "Anna Berger über Wirksam Test",
            "sender@example.test",
        )
        text = _part(message, "plain")
        assert "Hallo," in text
        assert (
            "Anna Berger hat dich gebeten, „Cafétheke“ bei „Sommerfest am Fluss“ "
            "zu verantworten." in text
        )
        assert "Ort: Foyer-Café" in text
        assert "Wann: Fr, 17. – So, 19. Juli" in text
        assert "löst bei „Cafétheke“ Marken ein" in text
        assert "Mira Lindqvist und Pia Incharge sind auch dabei." in text
        assert "Die Einladung gilt bis Mi, 18. November." in text
        # "diese Mail", not "sie": that could read as ignoring the person.
        assert (
            "Wenn du die Person nicht kennst, kannst du diese Mail einfach ignorieren."
            in text
        )

    async def test_the_button_and_the_fallback_link_open_the_invitation(self) -> None:
        html = _part(await _send(), "html")
        # The button's href, the fallback link's href and its visible text.
        assert html.count(INVITE_URL) == 3
        assert "Konto anlegen und zusagen" in html
        assert "Übernimmst du „Cafétheke“?" in html
        assert (
            "https://app.example.test/login?redirect=%2Finvite%2Finvite-token-123"
            in (html)
        )
        # Not the notification footer: there are no settings to manage.
        assert "/app/settings/notifications" not in html
        assert "Du bekommst diese Mail, weil Anna Berger" in html

    async def test_english_and_several_tasks(self) -> None:
        message = await _send(tasks=[CAFE, GRILL], language="en")
        assert message["Subject"] == (
            "[Wirksam Test] Anna Berger asks you to take on “Cafétheke” and “Grill”"
        )
        text = _part(message, "plain")
        assert "Tasks: Cafétheke, Grill" in text
        assert "Event: Sommerfest am Fluss" in text
        assert "When: Fri 17 – Sun 19 July" in text
        assert "redeem vouchers at “Cafétheke”" in text
        # Who else runs which task is only said for a single task.
        assert "in charge too" not in text
        assert "The invitation is valid until Wed 18 November." in text

    async def test_a_task_next_year_names_the_year(self) -> None:
        task = InvitedTask(
            name="Cafétheke",
            location=None,
            first_date=dt.date(2027, 7, 17),
            last_date=dt.date(2027, 7, 19),
            is_voucher_point=False,
        )
        message = await _send(tasks=[task])
        assert "Wann: Sa, 17. – Mo, 19. Juli 2027" in _part(message, "plain")
        assert "Sa, 17. – Mo, 19. Juli 2027</td>" in _part(message, "html")

    async def test_user_text_is_escaped(self) -> None:
        sneaky = Event(
            id=uuid.uuid4(),
            name="Fest <b>gratis</b>",
            start_date=dt.date(2026, 7, 17),
            end_date=dt.date(2026, 7, 17),
            created_by_id=uuid.uuid4(),
        )
        task = InvitedTask(
            name="<script>x</script>",
            location=None,
            first_date=dt.date(2026, 7, 17),
            last_date=dt.date(2026, 7, 17),
            is_voucher_point=False,
        )
        html = _part(
            await _send(inviter_name="<b>Eve</b>", event=sneaky, tasks=[task]), "html"
        )
        assert "<b>" not in html
        assert "<script>" not in html
        assert "&lt;b&gt;Eve&lt;/b&gt;" in html
        assert "Fest &lt;b&gt;gratis&lt;/b&gt;" in html

    async def test_no_expiry_sentence_without_an_expiry(self) -> None:
        text = _part(await _send(expires_at=None), "plain")
        assert "gilt bis" not in text
        assert "Möchtest du nicht?" in text


@pytest.mark.asyncio
class TestPlainInvitation:
    async def test_names_the_event_not_a_task(self) -> None:
        message = await _send(tasks=[], language="en")
        assert message["Subject"] == (
            "[Wirksam Test] Anna Berger invites you to “Sommerfest am Fluss”"
        )
        text = _part(message, "plain")
        assert "take part in “Sommerfest am Fluss”" in text
        assert "Event: Sommerfest am Fluss" in text
        assert "Being in charge" not in text
        assert "Will you join “Sommerfest am Fluss”?" in _part(message, "html")

    async def test_an_unknown_inviter_reads_as_someone_and_keeps_the_sender(
        self,
    ) -> None:
        message = await _send(tasks=[], inviter_name=None, language="en")
        assert message["Subject"] == (
            "[Wirksam Test] Someone invites you to “Sommerfest am Fluss”"
        )
        assert parseaddr(str(message["From"]))[0] == "Wirksam Test Sender"

    async def test_a_long_or_odd_inviter_name_stays_on_one_line(self) -> None:
        message = await _send(inviter_name="Anna\r\nBcc: Berger " + "a" * 80)
        name = parseaddr(str(message["From"]))[0]
        assert "\n" not in name
        assert "\r" not in name
        assert name.startswith("Anna Bcc: Berger")
        assert name.endswith("über Wirksam Test")
        assert message["Bcc"] is None

    @pytest.mark.parametrize(
        "inviter_name",
        [
            "security@bank.example",
            "Kundenservice <hilfe@bank.example>",
            "bank.example",
            "Support www.bank.de",
            "https://bank.example/login",
            "Anna\r\nBcc: x@y.z",
        ],
    )
    async def test_a_name_that_passes_for_an_address_keeps_the_sender(
        self, inviter_name: str
    ) -> None:
        """Anyone can sign up with any name and mail a stranger: one that
        could pass for an address or a site never reaches the sender column.
        The subject still says who invited."""
        message = await _send(tasks=[], inviter_name=inviter_name, language="en")
        assert parseaddr(str(message["From"])) == (
            "Wirksam Test Sender",
            "sender@example.test",
        )
        assert message["Bcc"] is None
        assert " ".join(inviter_name.split()) in str(message["Subject"])

    @pytest.mark.parametrize("inviter_name", ["J.R.R. Tolkien", "Dr. Anna Berger"])
    async def test_initials_and_titles_still_name_the_sender(
        self, inviter_name: str
    ) -> None:
        message = await _send(tasks=[], inviter_name=inviter_name, language="en")
        assert parseaddr(str(message["From"]))[0] == (
            f"{inviter_name} via Wirksam Test"
        )


@pytest.mark.asyncio
class TestDelivery:
    async def test_without_smtp_it_logs_the_link_and_reports_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            _email_settings(configured=False),
            patch(TRANSPORT, new_callable=AsyncMock) as smtp,
            caplog.at_level(logging.WARNING, logger="app.logic.auth.emails"),
        ):
            sent = await send_event_invitation_email(
                email="jonas@example.org",
                inviter_name="Anna",
                event=EVENT,
                tasks=[],
                token=TOKEN,
                expires_at=None,
                language="en",
            )
        assert sent is False
        smtp.assert_not_awaited()
        assert any(INVITE_URL in record.message for record in caplog.records)

    async def test_a_transport_failure_is_contained(self) -> None:
        with (
            _email_settings(),
            patch(TRANSPORT, new_callable=AsyncMock, side_effect=OSError("down")),
        ):
            sent = await send_event_invitation_email(
                email="jonas@example.org",
                inviter_name="Anna",
                event=EVENT,
                tasks=[],
                token=TOKEN,
                expires_at=None,
                language="en",
            )
        assert sent is False
