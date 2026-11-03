import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr


class TaskManagerAdd(BaseModel):
    """Put an event member in charge of a task."""

    user_id: uuid.UUID


class TaskManagerBrief(BaseModel):
    """A person in charge of a task, as every viewer of the task sees them."""

    user_id: uuid.UUID
    name: str | None = None
    avatar_etag: str | None = None


class TaskManagerInvite(BaseModel):
    """Put someone in charge by e-mail address: a member at once, anyone else
    through an event invitation that names the task."""

    email: EmailStr


class TaskManagerInvitationRead(BaseModel):
    """An open invitation that asks an address to be in charge of a task.

    Event admins only, so the address is shown in full.
    """

    #: The event invitation.
    id: uuid.UUID
    email: str
    invited_by_name: str | None = None
    created_at: dt.datetime
    expires_at: dt.datetime | None = None
    last_sent_at: dt.datetime | None = None
    expired: bool = False
    #: The address now belongs to an event member (they joined another way):
    #: the dialog offers "Add now" (the invite endpoint's member path).
    is_member_now: bool = False


SkippedReason = Literal["rate_limited", "address_limited", "sandbox"]


class TaskManagerInviteResult(BaseModel):
    """What inviting one address to be in charge did.

    An account that is not a member and an address nobody has get the same
    answer (``invited``), so the dialog cannot be used to find out who has an
    account.
    """

    status: Literal["added", "invited", "skipped"]
    #: ``added``: the member now in charge.
    manager: TaskManagerBrief | None = None
    #: ``invited``: the invitation that now names the task.
    invitation: TaskManagerInvitationRead | None = None
    #: A mail or notification went out with this call (False inside the
    #: 10-minute re-send window, or when added).
    emailed: bool = False
    #: Domain rule with bypass off: someone without an account can't register
    #: with this address. Never depends on whether an account exists.
    registration_may_fail: bool = False
    #: Only from create-with-shifts, which reports instead of failing.
    skipped_reason: SkippedReason | None = None
    #: Echoed, so the create form can match results to what was typed.
    email: str | None = None
