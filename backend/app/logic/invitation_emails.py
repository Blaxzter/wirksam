"""The invitation mail to an address that has no account yet.

An invitation to someone with an account goes out as the ``event.invitation``
notification, so their preferences apply. Without an account there is nobody
to notify, so ``dispatch_event_invitation`` sends this mail directly, like the
verification and reset mails (``send_action_mail`` in ``logic/auth/emails``),
for plain event invitations and invitations to be in charge alike.

Laid out after the approved design: who invites, a question as the heading,
what and when, what being in charge means and who else runs the task, one
button to the invitation, a sign-in line for whoever already has an account,
and a note that ignoring it is fine. Written in the inviter's language, the
best guess for a stranger.

It carries no free text from the organiser beyond names: no personal message
and no task description. A mail that reaches addresses nobody signed up with
must not be a vehicle for someone else's text (``logic/invitations.py`` has
the daily limits). Everything interpolated is escaped.
"""

import datetime as dt
import html
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from urllib.parse import quote
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.config import settings
from app.core.logger import get_logger
from app.crud.task_manager import task_manager as crud_task_manager
from app.logic.auth.emails import send_action_mail
from app.logic.notifications.channels.email import (
    button_html,
    card_html,
    details_table_html,
)
from app.logic.notifications.messages import (
    DEFAULT_LANGUAGE,
    date_range,
    get_email_strings,
    get_message,
    name_list,
    quoted_list,
)
from app.models.event import Event
from app.models.shift import Shift
from app.models.task import Task

logger = get_logger(__name__)

#: A display name longer than this is cut in the sender line.
_SENDER_NAME_MAX = 60


@dataclass(frozen=True)
class InvitedTask:
    """What the mail says about one task the invitee is asked to run."""

    name: str
    location: str | None
    first_date: dt.date
    last_date: dt.date
    is_voucher_point: bool
    #: Everyone in charge of it now, by name.
    managers: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class RenderedInvitation:
    title: str
    text: str
    html: str
    action_url: str
    action_label: str
    footer: str
    #: The sender's display name ("Anna via Wirksam"); None keeps the default.
    from_name: str | None


async def load_invited_tasks(
    db: AsyncSession, tasks: Sequence[Task]
) -> list[InvitedTask]:
    """Read what the mail says about ``tasks``: when, where, who runs them.

    "When" spans each task's shifts, falling back to the task's own dates
    while it has none (as the "you're in charge" mail does). People in charge
    without a name are left out, as the task page shows them by name only.
    """
    if not tasks:
        return []
    ids = [t.id for t in tasks]
    spans: dict[uuid.UUID, tuple[dt.date, dt.date]] = {
        task_id: (first, last)
        for task_id, first, last in (
            await db.execute(
                select(
                    col(Shift.task_id),
                    func.min(col(Shift.date)),
                    func.max(col(Shift.date)),
                )
                .where(col(Shift.task_id).in_(ids))
                .group_by(col(Shift.task_id))
            )
        ).all()
    }
    managers = await crud_task_manager.managers_for_tasks(db, task_ids=ids)
    out: list[InvitedTask] = []
    for task in tasks:
        first, last = spans.get(task.id, (task.start_date, task.end_date))
        out.append(
            InvitedTask(
                name=task.name,
                location=task.location,
                first_date=first,
                last_date=last,
                is_voucher_point=task.is_voucher_point,
                managers=tuple(
                    user.name for _, user in managers.get(task.id, []) if user.name
                ),
            )
        )
    return out


def _strings(language: str) -> dict[str, str]:
    """The ``email`` block, falling back to English per key (see ``_chrome``)."""
    english = get_email_strings(DEFAULT_LANGUAGE)
    return {**english, **get_email_strings(language)}


def _sender_name(name: str) -> str:
    """A name someone typed, made safe and short for a ``From`` display name."""
    flat = re.sub(r"[\x00-\x1f\x7f]+", " ", name)
    flat = " ".join(flat.split())
    if len(flat) > _SENDER_NAME_MAX:
        flat = flat[: _SENDER_NAME_MAX - 1].rstrip() + "…"
    return flat


def _initials(name: str) -> str:
    """Up to two letters for the inviter's round badge."""
    words = [w for w in re.split(r"[\s@._-]+", name) if w]
    letters = "".join(w[0] for w in words[:2]).upper()
    return letters or "?"


def _expiry_date(expires_at: dt.datetime) -> str:
    """The last day the invitation works, on the events' wall clock."""
    local = expires_at.replace(tzinfo=dt.UTC).astimezone(
        ZoneInfo(settings.EVENT_TIMEZONE)
    )
    return local.strftime("%d.%m.%Y")


def render_event_invitation_email(
    *,
    inviter_name: str | None,
    event_name: str,
    event_start: dt.date,
    event_end: dt.date,
    tasks: Sequence[InvitedTask],
    token: str,
    expires_at: dt.datetime | None,
    language: str,
) -> RenderedInvitation:
    """The mail, in ``language``, as subject, plain text, HTML and sender name."""
    s = _strings(language)
    inviter = inviter_name or get_message("someone", language)[0]
    project = settings.PROJECT_NAME
    names = [t.name for t in tasks]

    if tasks:
        task_list = quoted_list(names, language)
        title, intro = get_message(
            "invite.email.tasks",
            language,
            inviter=inviter,
            tasks=task_list,
            event_name=event_name,
        )
        heading = s["invite_heading_tasks"].format(tasks=task_list)
        if len(tasks) == 1:
            task = tasks[0]
            details = [(s["detail_task"], task.name)]
            if task.location:
                details.append((s["detail_location"], task.location))
            details.append(
                (s["detail_when"], date_range(task.first_date, task.last_date))
            )
        else:
            details = [
                (s["detail_tasks"], ", ".join(names)),
                (s["detail_event"], event_name),
                (s["detail_when"], date_range(event_start, event_end)),
            ]
        points = [t.name for t in tasks if t.is_voucher_point]
        means = (
            s["invite_in_charge_means_redeem"].format(
                points=quoted_list(points, language)
            )
            if points
            else s["invite_in_charge_means"]
        )
        others = list(tasks[0].managers) if len(tasks) == 1 else []
        if others:
            key = (
                "invite_also_in_charge_one"
                if len(others) == 1
                else "invite_also_in_charge_other"
            )
            means = f"{means} {s[key].format(names=name_list(others, language))}"
    else:
        title, intro = get_message(
            "invite.email", language, inviter=inviter, event_name=event_name
        )
        heading = s["invite_heading"].format(event_name=event_name)
        details = [
            (s["detail_event"], event_name),
            (s["detail_when"], date_range(event_start, event_end)),
        ]
        means = ""

    greeting = s["greeting_no_name"]
    organiser = s["invite_organiser"].format(event_name=event_name)
    action_url = f"{settings.FRONTEND_HOST}/invite/{token}"
    action_label = s["invite_cta"]
    login_url = (
        f"{settings.FRONTEND_HOST}/login?redirect={quote(f'/invite/{token}', safe='')}"
    )
    sign_in_label = s["invite_sign_in_link"]
    sign_in_template = s["invite_sign_in"]
    note_parts: list[str] = []
    if expires_at is not None:
        note_parts.append(
            get_message("invite.email.expiry", language, date=_expiry_date(expires_at))[
                1
            ]
        )
    note_parts.append(s["invite_decline"])
    note = " ".join(note_parts)
    footer = s["invite_footer"].format(inviter=inviter, project_name=project)

    text_blocks = [
        greeting,
        intro,
        "\n".join(f"{label}: {value}" for label, value in details),
    ]
    if means:
        text_blocks.append(means)
    text_blocks += [
        f"{action_label}:\n{action_url}",
        f"{sign_in_template.format(link=sign_in_label)}\n{login_url}",
        note,
        f"--\n{footer}",
    ]
    text = "\n\n".join(text_blocks)

    # The sign-in sentence holds a link in the middle: escape the sentence
    # (our own copy) first, then put the escaped anchor where it says {link}.
    before, _, after = sign_in_template.partition("{link}")
    sign_in_html = (
        f"{html.escape(before)}"
        f'<a href="{html.escape(login_url)}" style="color: #1f2937; font-weight: 700;">'
        f"{html.escape(sign_in_label)}</a>"
        f"{html.escape(after)}"
    )
    means_html = (
        f"""
                    <p style="margin: 18px 0 0; color: #4b5563; font-size: 14px; line-height: 1.6;">{html.escape(means)}</p>"""
        if means
        else ""
    )
    content = f"""
                    <table role="presentation" style="border-collapse: collapse; margin: 0 0 20px;">
                        <tr>
                            <td style="width: 44px; height: 44px; border-radius: 22px; background-color: #f3e3d3;
                                       text-align: center; vertical-align: middle; font-size: 15px;
                                       font-weight: 700; color: #1f2937;">{html.escape(_initials(inviter))}</td>
                            <td style="padding-left: 12px; font-size: 14px; color: #4b5563; line-height: 1.4;">
                                <strong style="color: #1f2937;">{html.escape(inviter)}</strong><br />{html.escape(organiser)}
                            </td>
                        </tr>
                    </table>
                    <h1 style="margin: 0 0 12px; font-size: 22px; line-height: 1.25; color: #1f2937;">{html.escape(heading)}</h1>
                    <p style="margin: 0 0 8px; color: #1f2937; font-size: 15px; line-height: 1.6;">{html.escape(greeting)}</p>
                    <p style="margin: 0; color: #1f2937; font-size: 15px; line-height: 1.6;">{html.escape(intro)}</p>{details_table_html(details)}{means_html}
                    <div style="height: 24px;"></div>
                    {button_html(action_url, action_label)}
                    <p style="margin: 16px 0 0; text-align: center; color: #4b5563; font-size: 14px; line-height: 1.6;">{sign_in_html}</p>
                    <p style="margin: 22px 0 0; color: #6b7280; font-size: 13px; line-height: 1.5;">{html.escape(note)}</p>
                    <!-- Mail clients that strip the button still have to leave a
                         way to reach the link, so it is repeated verbatim. -->
                    <p style="margin: 16px 0 0; font-size: 12px; color: #9ca3af;
                              line-height: 1.5; word-break: break-all;">
                        {html.escape(s["action_url_fallback"])}
                        <br />
                        <a href="{html.escape(action_url)}" style="color: #6b7280;">{html.escape(action_url)}</a>
                    </p>"""
    rendered_html = card_html(
        title=title,
        content=content,
        language=language,
        footer_text=footer,
        show_title=False,
    )
    from_name = (
        s["invite_from"].format(
            inviter=_sender_name(inviter_name), project_name=project
        )
        if inviter_name
        else None
    )
    return RenderedInvitation(
        title=title,
        text=text,
        html=rendered_html,
        action_url=action_url,
        action_label=action_label,
        footer=footer,
        from_name=from_name,
    )


async def send_event_invitation_email(
    *,
    email: str,
    inviter_name: str | None,
    event: Event,
    tasks: Sequence[InvitedTask],
    token: str,
    expires_at: dt.datetime | None,
    language: str,
) -> bool:
    """Send the invitation mail to an address without an account; never raise.

    True when SMTP accepted it. Without SMTP the invitation link is logged,
    as for the auth mails, so a local stack can still be walked through.
    """
    try:
        mail = render_event_invitation_email(
            inviter_name=inviter_name,
            event_name=event.name,
            event_start=event.start_date,
            event_end=event.end_date,
            tasks=tasks,
            token=token,
            expires_at=expires_at,
            language=language,
        )
    except Exception:
        logger.exception(f"Failed to render the event invitation email for {email}")
        return False
    return await send_action_mail(
        to=email,
        language=language,
        title=mail.title,
        text_body=mail.text,
        action_url=mail.action_url,
        action_label=mail.action_label,
        footer=mail.footer,
        kind="event.invitation",
        html_body=mail.html,
        from_name=mail.from_name,
    )
