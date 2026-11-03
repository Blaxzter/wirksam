"""Naming, inviting and removing the people in charge of a task.

There is no list endpoint for the people in charge: ``TaskRead.managers`` is
the list, and the editor reloads the task after each change. What being in
charge allows is decided in ``app.logic.permissions``
(``require_task_manager``).

Event admins can also type an address (``POST .../managers/invite``,
``app.logic.invitations.invite_to_task``): a member's is put in charge at
once, anyone else gets an event invitation that names the task and puts them
in charge when they accept (``POST /invitations/{token}/accept``). The
dialog lists those invitations, sends them again and withdraws them through
``.../managers/invitations``. Only organisers invite, and never from a demo.

Whoever is put in charge, or taken off, by someone else hears about it
(``task.manager_added`` / ``task.manager_removed``); an invited address gets
the invitation (``dispatch_event_invitation``). The dispatchers are imported
by name so tests can replace them on this module.
"""

import uuid
from typing import NoReturn

from fastapi import APIRouter, BackgroundTasks, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DBDep
from app.core.errors import raise_problem
from app.crud.event_invitation import event_invitation as crud_invitation
from app.crud.event_invitation_task import event_invitation_task as crud_links
from app.crud.event_membership import event_membership as crud_membership
from app.crud.task import task as crud_task
from app.crud.task_manager import task_manager as crud_task_manager
from app.crud.user import user as crud_user
from app.logic import clock
from app.logic.invitations import (
    invite_to_task,
    is_expired,
    mark_sent,
    may_resend,
    release_task_invitations,
    task_invitation_reads,
)
from app.logic.notifications.triggers import (
    dispatch_event_invitation,
    dispatch_task_manager_added,
    dispatch_task_manager_removed,
)
from app.logic.permissions import require_event_role
from app.models.event_invitation import EventInvitation
from app.models.task import Task
from app.models.user import User
from app.schemas.task_manager import (
    TaskManagerAdd,
    TaskManagerBrief,
    TaskManagerInvitationRead,
    TaskManagerInvite,
    TaskManagerInviteResult,
)

router = APIRouter()


async def _get_task(session: DBDep, task_id: uuid.UUID) -> Task:
    task = await crud_task.get(session, task_id)
    if task is None:
        raise_problem(404, code="task.not_found", detail="Task not found")
    return task


@router.post(
    "/{task_id}/managers",
    response_model=TaskManagerBrief,
    status_code=status.HTTP_201_CREATED,
)
async def add_task_manager(
    task_id: uuid.UUID,
    body: TaskManagerAdd,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> TaskManagerBrief:
    """Put an event member in charge of this task. Event admins only.

    The person is told, unless they named themselves. An open invitation that
    asked them to run this task (they joined the event another way) loses
    the task, as when their address is typed in.
    """
    task = await _get_task(session, task_id)
    await require_event_role(current_user, session, task.event_id)
    # Locked, not just read: a leave running alongside then waits for this
    # grant and removes it, rather than missing it and leaving it to come
    # back when the person re-joins.
    members = (
        await crud_membership.lock_member_ids(
            session, event_id=task.event_id, user_ids=[body.user_id]
        )
        if task.event_id is not None
        else set[uuid.UUID]()
    )
    if task.event_id is None or body.user_id not in members:
        _not_event_member()
    if await crud_task_manager.is_manager(
        session, task_id=task.id, user_id=body.user_id
    ):
        _already()
    user = await crud_user.get(session, id=body.user_id, raise_404_error=True)
    if user.email:
        await release_task_invitations(
            session, event_id=task.event_id, email=user.email, task_id=task.id
        )
    try:
        async with session.begin_nested():
            await crud_task_manager.add(
                session, task_id=task.id, user_id=body.user_id, added_by=current_user
            )
    except IntegrityError:
        # Someone else added the same person between the check and the insert.
        _already()
    if body.user_id != current_user.id:
        background_tasks.add_task(
            dispatch_task_manager_added,
            task_id=task.id,
            user_ids=[body.user_id],
            actor_id=current_user.id,
        )
    return TaskManagerBrief(
        user_id=user.id, name=user.name, avatar_etag=user.avatar_etag
    )


def _already() -> NoReturn:
    raise_problem(
        409,
        code="task.manager_already",
        detail="That person is already in charge of this task",
    )


@router.delete("/{task_id}/managers/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_task_manager(
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> None:
    """Remove someone from charge of this task.

    Event admins may remove anyone, and that person is told; a person in
    charge may step down, which tells nobody.
    """
    task = await _get_task(session, task_id)
    if user_id != current_user.id:
        await require_event_role(current_user, session, task.event_id)
    if not await crud_task_manager.remove(session, task_id=task.id, user_id=user_id):
        raise_problem(
            404,
            code="task.manager_not_found",
            detail="That person is not in charge of this task",
        )
    if user_id != current_user.id:
        background_tasks.add_task(
            dispatch_task_manager_removed,
            task_id=task.id,
            user_id=user_id,
            actor_id=current_user.id,
        )


# -- Inviting by e-mail ----------------------------------------------


@router.post(
    "/{task_id}/managers/invite",
    response_model=TaskManagerInviteResult,
    status_code=status.HTTP_201_CREATED,
)
async def invite_task_manager(
    task_id: uuid.UUID,
    body: TaskManagerInvite,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> TaskManagerInviteResult:
    """Put the person behind an address in charge, or invite them. Event admins.

    A member is in charge at once (``added``) and told, unless it is the
    caller. Anyone else, with an account or without, gets the same answer
    (``invited``), so this cannot be used to find out who has an account:
    the address is invited into the event with this task linked, by mail or
    notification unless one went out in the last ten minutes (``emailed``).
    Not from a demo (``403 sandbox.invitations_disabled``); a new invitation
    counts against the daily limits (``429 invitation.*``).
    """
    task = await _get_task(session, task_id)
    if task.event_id is None:
        _not_event_member()
    await require_event_role(current_user, session, task.event_id)
    result = await invite_to_task(
        session,
        task=task,
        inviter=current_user,
        email=str(body.email),
        now=clock.utc_now(),
    )
    queue_invite_effects(
        background_tasks, task_id=task.id, actor=current_user, results=[result]
    )
    return result


def queue_invite_effects(
    background_tasks: BackgroundTasks,
    *,
    task_id: uuid.UUID,
    actor: User,
    results: list[TaskManagerInviteResult],
) -> None:
    """Queue what ``invite_to_task`` decided for one task.

    One "you're in charge" notice for every member someone else added, and
    the invitation for every address that is due a mail.
    """
    added = [
        r.manager.user_id
        for r in results
        if r.status == "added" and r.manager and r.manager.user_id != actor.id
    ]
    if added:
        background_tasks.add_task(
            dispatch_task_manager_added,
            task_id=task_id,
            user_ids=added,
            actor_id=actor.id,
        )
    for r in results:
        if r.status == "invited" and r.emailed and r.invitation is not None:
            background_tasks.add_task(
                dispatch_event_invitation, invitation_id=r.invitation.id
            )


@router.get(
    "/{task_id}/managers/invitations",
    response_model=list[TaskManagerInvitationRead],
)
async def list_task_manager_invitations(
    task_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> list[TaskManagerInvitationRead]:
    """The open invitations to be in charge of this task. Event admins only.

    Expired ones are included and flagged, so the dialog can offer "Invite
    again"; ``is_member_now`` marks an address that joined the event another
    way, which the dialog offers to "Add now".
    """
    task = await _get_task(session, task_id)
    await require_event_role(current_user, session, task.event_id)
    if task.event_id is None:
        return []
    invitations = await crud_links.open_invitations_for_task(session, task_id=task.id)
    return await task_invitation_reads(
        session, invitations, event_id=task.event_id, now=clock.utc_now()
    )


@router.post(
    "/{task_id}/managers/invitations/{invitation_id}/resend",
    response_model=TaskManagerInvitationRead,
)
async def resend_task_manager_invitation(
    task_id: uuid.UUID,
    invitation_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> TaskManagerInvitationRead:
    """Send an invitation to be in charge again. Event admins only.

    At most once every ten minutes (``429 invitation.resend_too_soon``). An
    expired invitation is ``409 invitation.expired``: the dialog offers
    "Invite again" instead, which is the invite endpoint. Sending again keeps
    the link open for another two weeks.
    """
    event_id, invitation = await _task_invitation(
        session, current_user, task_id, invitation_id
    )
    now = clock.utc_now()
    if is_expired(invitation, now):
        raise_problem(
            409,
            code="invitation.expired",
            detail="This invitation has expired. Send a new one.",
        )
    if not may_resend(invitation, now):
        raise_problem(
            429,
            code="invitation.resend_too_soon",
            detail="An e-mail went out a few minutes ago. Wait a little.",
        )
    mark_sent(invitation, now)
    session.add(invitation)
    await session.flush()
    background_tasks.add_task(dispatch_event_invitation, invitation_id=invitation.id)
    [read] = await task_invitation_reads(
        session, [invitation], event_id=event_id, now=now
    )
    return read


@router.delete(
    "/{task_id}/managers/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def withdraw_task_manager_invitation(
    task_id: uuid.UUID,
    invitation_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
) -> None:
    """Take this task off an invitation. Event admins only.

    An invitation that existed only for its tasks is revoked once none is
    left, so its link answers "withdrawn"; one from the event settings stays
    valid and just no longer puts the person in charge of this task.
    """
    _, invitation = await _task_invitation(
        session, current_user, task_id, invitation_id
    )
    await crud_links.remove(session, invitation=invitation, task_id=task_id)


async def _task_invitation(
    session: DBDep,
    current_user: User,
    task_id: uuid.UUID,
    invitation_id: uuid.UUID,
) -> tuple[uuid.UUID, EventInvitation]:
    """The task's event and one of its open invitations, for an event admin.

    ``404 task.manager_invitation_not_found`` unless the invitation is in the
    task's event, open, and linked to this task.
    """
    task = await _get_task(session, task_id)
    await require_event_role(current_user, session, task.event_id)
    invitation = await crud_invitation.get(session, invitation_id=invitation_id)
    if (
        invitation is None
        or task.event_id is None
        or invitation.event_id != task.event_id
        or invitation.revoked_at is not None
        or invitation.accepted_at is not None
        or not await crud_links.is_linked(
            session, invitation_id=invitation.id, task_id=task.id
        )
    ):
        raise_problem(
            404,
            code="task.manager_invitation_not_found",
            detail="That invitation could not be found",
        )
    return task.event_id, invitation


def _not_event_member() -> NoReturn:
    raise_problem(
        422,
        code="task.manager_not_event_member",
        detail="Only members of this event can be put in charge of its tasks",
    )
