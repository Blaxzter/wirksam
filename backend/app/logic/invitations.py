"""Inviting people by e-mail: the daily limits, the re-send rule, and inviting
someone to be in charge of a task.

Anyone can create an event and so be its organiser, and invitation mails now
reach addresses that never signed up (``logic/invitation_emails.py``). Three
limits keep that from becoming a way to send mail to strangers, all counted in
the database so they hold across the backend's worker processes and restarts,
unlike ``core/rate_limit.py``:

* per organiser: at most ``INVITATIONS_PER_INVITER_PER_DAY`` targeted
  invitations created in 24 hours (``429 invitation.rate_limited``);
* per address, across the whole installation: at most
  ``INVITATIONS_PER_ADDRESS_PER_DAY`` (``429 invitation.address_limited``), so
  nobody can fill one inbox from several events;
* per invitation: one mail every ``RESEND_AFTER`` (``last_sent_at``).

The platform superadmin is exempt from the first two. Like ``RateLimiter``
they are off under ``settings.TESTING``, because the E2E fixtures invite the
same seeded people into many events; the backend tests switch them on where
they test them.

:func:`invite_to_task` is ``POST /tasks/{id}/managers/invite``, shared with
``POST /tasks/with-shifts``. It never queues anything itself: the caller reads
the result and queues ``dispatch_task_manager_added`` (``added``, unless the
caller named themselves) or ``dispatch_event_invitation`` (``invited`` with
``emailed``), so both stay imported by name in the route modules, where the
tests replace them.
"""

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Literal, NoReturn

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.config import settings
from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.crud.event_invitation import event_invitation as crud_invitation
from app.crud.event_invitation_task import event_invitation_task as crud_links
from app.crud.event_membership import event_membership as crud_membership
from app.crud.task_manager import task_manager as crud_task_manager
from app.crud.user import user as crud_user
from app.logic.auth.registration import email_domain_allowed, registration_policy
from app.logic.sandbox.guards import refuse_if_sandbox
from app.models.event_invitation import EventInvitation
from app.models.event_membership import EventMembership
from app.models.task import Task
from app.models.user import User
from app.schemas.task_manager import (
    SkippedReason,
    TaskManagerBrief,
    TaskManagerInvitationRead,
    TaskManagerInviteResult,
)

INVITATIONS_PER_INVITER_PER_DAY = 200
INVITATIONS_PER_ADDRESS_PER_DAY = 3
RESEND_AFTER = dt.timedelta(minutes=10)
INVITATION_TTL_DAYS = 14

_QUOTA_WINDOW = dt.timedelta(hours=24)

QuotaRefusal = Literal["rate_limited", "address_limited"]


# ── Limits ────────────────────────────────────────────────────────


async def quota_refusal(
    session: AsyncSession, *, inviter: User, email: str, now: dt.datetime
) -> QuotaRefusal | None:
    """Which daily limit a new targeted invitation to ``email`` would break.

    ``None`` when it may be created. Counts every targeted invitation created
    in the last 24 hours, revoked or accepted ones included: what is limited
    is mail going out, and each of them sent one.
    """
    if inviter.is_admin or settings.TESTING:
        return None
    since = now - _QUOTA_WINDOW
    by_inviter = await session.scalar(
        select(func.count(col(EventInvitation.id))).where(
            col(EventInvitation.invited_by_id) == inviter.id,
            col(EventInvitation.email).is_not(None),
            col(EventInvitation.created_at) > since,
        )
    )
    if (by_inviter or 0) >= INVITATIONS_PER_INVITER_PER_DAY:
        return "rate_limited"
    # Stored lowercased (``crud.event_invitation.create``), so compare with
    # the lowercased address rather than ``lower(email)`` and keep the index.
    by_address = await session.scalar(
        select(func.count(col(EventInvitation.id))).where(
            col(EventInvitation.email) == email.lower(),
            col(EventInvitation.created_at) > since,
        )
    )
    if (by_address or 0) >= INVITATIONS_PER_ADDRESS_PER_DAY:
        return "address_limited"
    return None


def raise_quota_refusal(refusal: QuotaRefusal) -> NoReturn:
    if refusal == "rate_limited":
        raise_problem(
            429,
            code="invitation.rate_limited",
            detail="You have sent a lot of invitations today. Try again tomorrow.",
        )
    raise_problem(
        429,
        code="invitation.address_limited",
        detail="This address has already received several invitations today.",
    )


async def check_new_invitation_quota(
    session: AsyncSession, *, inviter: User, email: str, now: dt.datetime
) -> None:
    """429 ``invitation.rate_limited`` / ``invitation.address_limited``.

    A no-op for the superadmin and under ``settings.TESTING``.
    """
    refusal = await quota_refusal(session, inviter=inviter, email=email, now=now)
    if refusal is not None:
        raise_quota_refusal(refusal)


def may_resend(invitation: EventInvitation, now: dt.datetime) -> bool:
    """Whether a mail for this invitation may go out again now."""
    return (
        invitation.last_sent_at is None or now - invitation.last_sent_at >= RESEND_AFTER
    )


def is_expired(invitation: EventInvitation, now: dt.datetime) -> bool:
    return invitation.expires_at is not None and invitation.expires_at <= now


def mark_sent(invitation: EventInvitation, now: dt.datetime) -> None:
    """Record that a mail is being queued, and keep the link open for a while.

    Sending again moves the expiry out to at least ``INVITATION_TTL_DAYS``
    from now: a mail that arrives with a link expiring tomorrow helps nobody.
    An invitation that never expires keeps never expiring. The caller queues
    ``dispatch_event_invitation``.
    """
    invitation.last_sent_at = now
    if invitation.expires_at is not None:
        invitation.expires_at = max(
            invitation.expires_at, now + dt.timedelta(days=INVITATION_TTL_DAYS)
        )


def registration_may_fail(email: str) -> bool:
    """Whether someone without an account could not register with ``email``.

    Only with an allowed-domains list and the invitation bypass off. Computed
    from the domain rule alone, never from whether an account exists, so it
    gives nothing away.
    """
    policy = registration_policy()
    return (
        bool(policy.allowed_domains)
        and not policy.invite_bypass
        and not email_domain_allowed(email, policy.allowed_domains)
    )


# ── Reading ───────────────────────────────────────────────────────


async def task_invitation_reads(
    session: AsyncSession,
    invitations: Sequence[EventInvitation],
    *,
    event_id: uuid.UUID,
    now: dt.datetime,
) -> list[TaskManagerInvitationRead]:
    """The invitations as the people-in-charge dialog lists them.

    Two queries for the whole list: the inviters' names, and which of the
    addresses now belong to members of the event (they joined another way,
    so the dialog offers "Add now").
    """
    if not invitations:
        return []
    inviter_ids = {i.invited_by_id for i in invitations if i.invited_by_id}
    inviters: dict[uuid.UUID, User] = {}
    if inviter_ids:
        users = await session.execute(select(User).where(col(User.id).in_(inviter_ids)))
        inviters = {u.id: u for u in users.scalars()}
    emails = {i.email for i in invitations if i.email}
    member_emails: set[str] = set()
    if emails:
        rows = await session.execute(
            select(func.lower(col(User.email)))
            .join(EventMembership, col(EventMembership.user_id) == col(User.id))
            .where(
                col(EventMembership.event_id) == event_id,
                func.lower(col(User.email)).in_(emails),
            )
        )
        member_emails = {e for e in rows.scalars() if e}
    reads: list[TaskManagerInvitationRead] = []
    for invitation in invitations:
        inviter = (
            inviters.get(invitation.invited_by_id) if invitation.invited_by_id else None
        )
        reads.append(
            TaskManagerInvitationRead(
                id=invitation.id,
                email=invitation.email or "",
                invited_by_name=(inviter.name or inviter.email) if inviter else None,
                created_at=invitation.created_at,
                expires_at=invitation.expires_at,
                last_sent_at=invitation.last_sent_at,
                expired=is_expired(invitation, now),
                is_member_now=(invitation.email or "") in member_emails,
            )
        )
    return reads


# ── Inviting someone to be in charge ──────────────────────────────


def _already_in_charge() -> NoReturn:
    raise_problem(
        409,
        code="task.manager_already",
        detail="That person is already in charge of this task",
    )


def _already_invited() -> NoReturn:
    raise_problem(
        409,
        code="task.manager_already_invited",
        detail="That address is already invited to be in charge of this task",
    )


async def _add_member(
    session: AsyncSession,
    *,
    task: Task,
    member: User,
    inviter: User,
    event_id: uuid.UUID,
    address: str,
) -> TaskManagerInviteResult:
    """The address belongs to a member: put them in charge at once."""
    if await crud_task_manager.is_manager(session, task_id=task.id, user_id=member.id):
        _already_in_charge()
    try:
        async with session.begin_nested():
            await crud_task_manager.add(
                session, task_id=task.id, user_id=member.id, added_by=inviter
            )
    except IntegrityError:
        # Someone else added the same person between the check and the insert.
        _already_in_charge()
    # An earlier invitation that asked them to run this task has done its job.
    for invitation in await crud_links.open_for_address(
        session, event_id=event_id, email=address, include_expired=True
    ):
        await crud_links.remove(session, invitation=invitation, task_id=task.id)
    return TaskManagerInviteResult(
        status="added",
        manager=TaskManagerBrief(
            user_id=member.id, name=member.name, avatar_etag=member.avatar_etag
        ),
        email=address,
    )


def _skipped(reason: SkippedReason, address: str) -> TaskManagerInviteResult:
    return TaskManagerInviteResult(
        status="skipped", skipped_reason=reason, email=address
    )


async def invite_to_task(
    session: AsyncSession,
    *,
    task: Task,
    inviter: User,
    email: str,
    now: dt.datetime,
    skip_refusals: bool = False,
) -> TaskManagerInviteResult:
    """Put the person behind ``email`` in charge of ``task``, or invite them.

    The caller has checked that ``task`` has an event and that ``inviter`` is
    an admin there. Then:

    * the address belongs to a **member**: they are in charge at once
      (``added``), and this task's link goes from any open invitation to that
      address;
    * anyone else, account or not, gets the same answer (``invited``). The
      task is added to the address's open, valid invitation in this event if
      there is one (its role stays as it was), mailed again unless one went
      out within ``RESEND_AFTER``. Otherwise a new invitation is created
      (role ``member``, ``INVITATION_TTL_DAYS``), marked ``for_tasks_only``
      unless it replaces an expired plain one, and mailed. Expired open
      invitations to the address are revoked and their task links move onto
      it, so "invite again" from any task re-invites for all of them.

    Demo events cannot invite (``403 sandbox.invitations_disabled``), and a
    new invitation counts against the daily limits. With ``skip_refusals``
    (create-with-shifts, which must not roll back the task it just built)
    those two refusals come back as ``skipped`` instead of being raised.
    """
    address = email.strip().lower()
    if task.event_id is None:
        raise_problem(
            422,
            code="task.manager_not_event_member",
            detail="Only members of this event can be put in charge of its tasks",
        )
    event_id = task.event_id

    account = await crud_user.get_by_email(session, email=address)
    if account is not None:
        # Locked, not just read, as in ``POST /tasks/{id}/managers``: a leave
        # running alongside then waits for this grant and removes it.
        members = await crud_membership.lock_member_ids(
            session, event_id=event_id, user_ids=[account.id]
        )
        if account.id in members:
            return await _add_member(
                session,
                task=task,
                member=account,
                inviter=inviter,
                event_id=event_id,
                address=address,
            )

    if skip_refusals:
        event = await crud_event.get(session, event_id)
        if event is not None and event.is_sandbox:
            return _skipped("sandbox", address)
    else:
        await refuse_if_sandbox(session, event_id)

    open_invitations = await crud_links.open_for_address(
        session, event_id=event_id, email=address, include_expired=True
    )
    valid = [i for i in open_invitations if not is_expired(i, now)]
    expired = [i for i in open_invitations if is_expired(i, now)]
    for invitation in valid:
        if await crud_links.is_linked(
            session, invitation_id=invitation.id, task_id=task.id
        ):
            _already_invited()

    emailed = False
    if valid:
        target = valid[0]
    else:
        refusal = await quota_refusal(session, inviter=inviter, email=address, now=now)
        if refusal is not None:
            if skip_refusals:
                return _skipped(refusal, address)
            raise_quota_refusal(refusal)
        target = await crud_invitation.create(
            session,
            event_id=event_id,
            email=address,
            role="member",
            invited_by_id=inviter.id,
            expires_in_days=INVITATION_TTL_DAYS,
            # Replacing an expired invitation from the event settings keeps
            # it one: the person was invited to the event, not just the tasks.
            for_tasks_only=all(old.for_tasks_only for old in expired),
        )
    for old in expired:
        await crud_links.move_links(session, from_id=old.id, to_id=target.id)
        await crud_invitation.revoke(session, invitation=old)
    # "Invite again" on an expired row: its link may have just moved over.
    if not await crud_links.is_linked(
        session, invitation_id=target.id, task_id=task.id
    ):
        await crud_links.add(
            session, invitation_id=target.id, task_id=task.id, added_by=inviter
        )
    if may_resend(target, now):
        mark_sent(target, now)
        emailed = True
    session.add(target)
    await session.flush()

    [read] = await task_invitation_reads(session, [target], event_id=event_id, now=now)
    return TaskManagerInviteResult(
        status="invited",
        invitation=read,
        emailed=emailed,
        registration_may_fail=registration_may_fail(address),
        email=address,
    )
