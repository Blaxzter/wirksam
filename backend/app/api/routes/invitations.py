"""Redeeming an event invitation.

Kept off ``/events/{id}`` on purpose: the holder of a token should not need to
know — or be able to guess — the event id before accepting, and a private
event must stay 404 to them until the token proves they were invited.

A targeted invitation can ask its invitee to be in charge of tasks
(``event_invitation_tasks``). Accepting applies them, together with those of
any other open invitation to the same address in the event: holding a token
sent to that mailbox shows the person controls the address. Joining another
way (a share link, a join request) applies none of them, because addresses
are not verified in this app; the organisers' dialog offers "Add now"
instead.
"""

import uuid
from typing import NoReturn

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.event import event as crud_event
from app.crud.event_invitation import event_invitation as crud_invitation
from app.crud.event_invitation import invitation_invalid_reason
from app.crud.event_invitation_task import event_invitation_task as crud_links
from app.crud.event_membership import event_membership as crud_membership
from app.crud.task_manager import task_manager as crud_task_manager
from app.crud.user import user as crud_user
from app.logic.permissions import role_at_least
from app.models.event_invitation import EventInvitation
from app.models.event_invitation_task import EventInvitationTask
from app.models.task import Task
from app.schemas.event import EventRead
from app.schemas.event_invitation import EventInvitationPreview, InvitationTaskBrief
from app.schemas.event_membership import AssignableEventRole

router = APIRouter(prefix="/invitations", tags=["invitations"])


def _email_matches(invitation_email: str | None, user_email: str | None) -> bool:
    """Whether a targeted invitation was addressed to this user.

    A link invitation (no address) matches everyone.
    """
    if invitation_email is None:
        return True
    if not user_email:
        return False
    return invitation_email.lower() == user_email.lower()


async def _targeted_for_address(
    session: AsyncSession, invitation: EventInvitation, *, lock: bool = False
) -> list[EventInvitation]:
    """This targeted invitation and every other open, valid one to its address
    in its event.

    Normally just this one: inviting an address that already has one adds the
    task to it. Two organisers inviting at the same moment can leave two.

    With ``lock`` (accepting) the rows stay locked until commit, so a task an
    organiser links at the same moment is either seen here or lands on a new
    invitation (``invite_to_task`` locks the same rows). If this invitation
    stopped being valid while the lock was awaited, the accept is refused
    as it would have been a moment later.
    """
    assert invitation.email is not None
    others = await crud_links.open_for_address(
        session, event_id=invitation.event_id, email=invitation.email, for_update=lock
    )
    if lock and all(i.id != invitation.id for i in others):
        await session.refresh(invitation)
        _refuse(invitation_invalid_reason(invitation) or "already_used")
    return [invitation, *(i for i in others if i.id != invitation.id)]


def _refuse(reason: str) -> NoReturn:
    raise_problem(
        410,
        code=f"invitation.{reason}",
        detail="This invitation can no longer be used",
    )


async def _linked_tasks(
    session: AsyncSession,
    invitations: list[EventInvitation],
    *,
    event_id: uuid.UUID,
) -> list[tuple[Task, EventInvitationTask]]:
    """The tasks the invitations ask for that still belong to the event, each
    with the link that asked first (who asked is on it).

    A task moved to another event has lost its links already
    (``detach_task``); filtering on the event as well keeps a straggler from
    making someone in charge of a task in an event they did not join.
    """
    seen: dict[uuid.UUID, tuple[Task, EventInvitationTask]] = {}
    for link, task in await crud_links.links_with_tasks(
        session, invitation_ids=[i.id for i in invitations]
    ):
        if task.event_id == event_id:
            seen.setdefault(task.id, (task, link))
    return list(seen.values())


@router.get("/{token}", response_model=EventInvitationPreview)
async def preview_invitation(
    token: str,
    session: DBDep,
    current_user: CurrentUser,
) -> EventInvitationPreview:
    """What this token grants, so the invitee can decide before accepting.

    Returns 404 for an unknown token, but a *known* token that is expired or
    revoked still resolves — the invitee deserves to be told which it was
    rather than staring at a dead link.
    """
    invitation = await crud_invitation.get_by_token(session, token=token)
    if not invitation:
        raise_problem(
            404,
            code="invitation.not_found",
            detail="This invitation link is not valid",
        )

    db_event = await crud_event.get(session, invitation.event_id)
    if not db_event:
        raise_problem(
            404,
            code="invitation.event_gone",
            detail="The event this invitation points to no longer exists",
        )

    reason = invitation_invalid_reason(invitation)
    if reason is None and not _email_matches(invitation.email, current_user.email):
        reason = "email_mismatch"

    inviter_name: str | None = None
    if invitation.invited_by_id:
        inviter = await crud_user.get(session, id=invitation.invited_by_id)
        inviter_name = inviter.name if inviter else None

    already_member = (
        await crud_membership.get(
            session, user_id=current_user.id, event_id=db_event.id
        )
        is not None
    )

    # The tasks only for the addressee: the token alone shows the event, not
    # what its organisers asked of whom.
    tasks: list[InvitationTaskBrief] = []
    if (
        invitation.email is not None
        and _email_matches(invitation.email, current_user.email)
        and (reason is None or already_member)
    ):
        pending = (
            await _targeted_for_address(session, invitation)
            if reason is None
            else [invitation]
        )
        tasks = [
            InvitationTaskBrief(
                task_id=t.id, name=t.name, start_date=t.start_date, end_date=t.end_date
            )
            for t, _ in await _linked_tasks(session, pending, event_id=db_event.id)
        ]

    return EventInvitationPreview(
        event_id=db_event.id,
        event_name=db_event.name,
        event_description=db_event.description,
        start_date=db_event.start_date,
        end_date=db_event.end_date,
        role=invitation.role,  # type: ignore[arg-type]
        invited_by_name=inviter_name,
        is_valid=reason is None,
        invalid_reason=reason,
        already_member=already_member,
        tasks=tasks,
    )


@router.post("/{token}/accept", response_model=EventRead)
async def accept_invitation(
    token: str,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EventRead:
    """Redeem an invitation and join the event.

    A targeted invitation also puts the person in charge of every task it
    asks for, and of those of any other open invitation to their address in
    this event; all of them are marked accepted, even when the person was a
    member already. A share link only counts up, and only for a newcomer.
    """
    invitation = await crud_invitation.get_by_token(session, token=token)
    if not invitation:
        raise_problem(
            404,
            code="invitation.not_found",
            detail="This invitation link is not valid",
        )

    reason = invitation_invalid_reason(invitation)
    if reason is not None:
        _refuse(reason)
    if not _email_matches(invitation.email, current_user.email):
        raise_problem(
            403,
            code="invitation.email_mismatch",
            detail="This invitation was sent to a different email address",
        )

    db_event = await crud_event.get(session, invitation.event_id)
    if not db_event:
        raise_problem(
            404,
            code="invitation.event_gone",
            detail="The event this invitation points to no longer exists",
        )

    # Locked before anything is read from them or written, see
    # ``_targeted_for_address``.
    targeted = (
        await _targeted_for_address(session, invitation, lock=True)
        if invitation.email is not None
        else []
    )
    existing = await crud_membership.get(
        session, user_id=current_user.id, event_id=db_event.id
    )
    if existing is None:
        # The strongest role among them: an organiser invitation must not be
        # used up as a plain one because a task invitation was opened first.
        role: AssignableEventRole = invitation.role  # type: ignore[assignment]
        for other in targeted:
            if role_at_least(other.role, role):  # type: ignore[arg-type]
                role = other.role  # type: ignore[assignment]
        await crud_membership.upsert(
            session,
            user_id=current_user.id,
            event_id=db_event.id,
            role=role,
        )
        if not targeted:
            await crud_invitation.mark_redeemed(
                session, invitation=invitation, user_id=current_user.id
            )

    applied: list[uuid.UUID] = []
    if targeted:
        for task, link in await _linked_tasks(session, targeted, event_id=db_event.id):
            if await crud_task_manager.is_manager(
                session, task_id=task.id, user_id=current_user.id
            ):
                continue
            try:
                async with session.begin_nested():
                    # The organiser who asked put them in charge, not the
                    # invitee who accepted.
                    await crud_task_manager.add_asked_by(
                        session,
                        task_id=task.id,
                        user_id=current_user.id,
                        added_by_id=link.added_by_id,
                        added_by_name=link.added_by_name,
                    )
            except IntegrityError:
                # A concurrent accept put them in charge first.
                continue
            applied.append(task.id)
        for each in targeted:
            await crud_invitation.mark_redeemed(
                session, invitation=each, user_id=current_user.id
            )

    if existing is None:
        from app.logic.notifications.triggers import dispatch_event_invitation_accepted

        background_tasks.add_task(
            dispatch_event_invitation_accepted,
            event_id=db_event.id,
            user_id=current_user.id,
            task_ids=applied,
        )

    # An accepted invitation supersedes any request the user had pending.
    from app.crud.event_join_request import event_join_request as crud_join_request

    await crud_join_request.delete_for_user(
        session, user_id=current_user.id, event_id=db_event.id
    )

    from app.api.routes.events import decorate_event

    return await decorate_event(session, current_user, db_event)
