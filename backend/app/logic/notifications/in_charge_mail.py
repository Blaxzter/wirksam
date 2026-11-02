"""The e-mail for ``task.manager_added``, laid out after the approved design.

The in-app row and the push say who put the person in charge of which task.
The mail also says where and when the task is, who else runs it, what being in
charge lets them do, and that they can step down, so they can decide whether
to take it on before opening the app. It goes through ``NotificationService``
like every notice (``email_body=``), so preferences and mutes still decide
whether it is sent; only its content is written per recipient, since the
greeting and the "also in charge" line differ from person to person.
"""

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.config import settings
from app.crud.task_manager import task_manager as crud_task_manager
from app.logic.notifications.channels.email import EmailBody, build_details_html
from app.logic.notifications.messages import (
    date_range,
    get_email_strings,
    get_message,
)
from app.models.shift import Shift
from app.models.task import Task
from app.models.user import User


@dataclass(frozen=True)
class InChargeMail:
    """What the mail says about one task, loaded once for all its recipients."""

    task_id: uuid.UUID
    task_name: str
    event_name: str
    #: The organiser's name or address; ``None`` reads as "Someone".
    actor: str | None
    location: str | None
    first_date: dt.date
    last_date: dt.date
    shift_count: int
    #: Everyone in charge now, by name: ``(user_id, name)``.
    managers: tuple[tuple[uuid.UUID, str], ...]
    is_voucher_point: bool

    def render(self, recipient: User) -> EmailBody:
        """The mail for ``recipient``, in their language."""
        lang = recipient.preferred_language
        strings = get_email_strings(lang)
        actor = self.actor or get_message("someone", lang)[0]
        title, _ = get_message(
            "task.manager_added",
            lang,
            actor=actor,
            task_name=self.task_name,
            event_name=self.event_name,
        )
        greeting = (
            strings["greeting"].format(name=recipient.name)
            if recipient.name
            else strings["greeting_no_name"]
        )
        intro = strings["in_charge_intro"].format(
            actor=actor, task_name=self.task_name, event_name=self.event_name
        )

        when = date_range(self.first_date, self.last_date)
        if self.shift_count == 1:
            when = f"{when} · {strings['shift_count_one']}"
        elif self.shift_count > 1:
            when = f"{when} · {strings['shift_count_other'].format(n=self.shift_count)}"
        details = [(strings["detail_task"], self.task_name)]
        if self.location:
            details.append((strings["detail_location"], self.location))
        details.append((strings["detail_when"], when))
        others = [name for uid, name in self.managers if uid != recipient.id]
        if others:
            details.append((strings["detail_also_in_charge"], ", ".join(others)))

        items = [strings["in_charge_can_edit"], strings["in_charge_can_see"]]
        if self.is_voucher_point:
            items.append(
                strings["in_charge_can_redeem"].format(task_name=self.task_name)
            )

        action_url = f"{settings.FRONTEND_HOST}/app/tasks/{self.task_id}"
        action_label = strings["open_task"]
        note = strings["in_charge_step_down"]

        text = "\n\n".join(
            [
                greeting,
                intro,
                "\n".join(f"{label}: {value}" for label, value in details),
                strings["in_charge_can_heading"]
                + "\n"
                + "\n".join(f"- {item}" for item in items),
                f"{action_label}:\n{action_url}",
                note,
            ]
        )
        html = build_details_html(
            title=title,
            language=lang,
            paragraphs=[greeting, intro],
            details=details,
            list_heading=strings["in_charge_can_heading"],
            items=items,
            action_url=action_url,
            action_label=action_label,
            note=note,
        )
        return EmailBody(text=text, html=html)


async def load_in_charge_mail(
    db: AsyncSession, *, task: Task, event_name: str, actor: str | None
) -> InChargeMail:
    """Read what the mail needs about ``task``: shifts, place, who runs it.

    "When" spans the task's shifts and counts them; a task without shifts yet
    falls back to its own start and end date. People in charge without a name
    are left out of "also in charge" rather than shown by address, as the task
    page shows them to each other by name only.
    """
    first, last, count = (
        await db.execute(
            select(
                func.min(col(Shift.date)),
                func.max(col(Shift.date)),
                func.count(col(Shift.id)),
            ).where(col(Shift.task_id) == task.id)
        )
    ).one()
    rows = await crud_task_manager.managers_for_tasks(db, task_ids=[task.id])
    managers = tuple(
        (user.id, user.name) for _, user in rows.get(task.id, []) if user.name
    )
    return InChargeMail(
        task_id=task.id,
        task_name=task.name,
        event_name=event_name,
        actor=actor,
        location=task.location,
        first_date=first or task.start_date,
        last_date=last or task.end_date,
        shift_count=int(count or 0),
        managers=managers,
        is_voucher_point=task.is_voucher_point,
    )
