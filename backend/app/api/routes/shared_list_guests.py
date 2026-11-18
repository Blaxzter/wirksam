"""Who signed up through a shared list: the organisers' view and removal, and
the operator's lookup, export and erasure of guest data, and lifting a "Das
war ich nicht" from an address.

Guest contact data goes only to the event admins and the people in charge of
the task; the gates are the shared-list ones in ``app.logic.permissions``.
A person in charge sees the sign-ups on their own tasks, and how many others
there are.

The organisers' routes answer 404 ``shared_list.disabled`` while
``SHARED_LISTS_ENABLED`` is off. The operator's ``/list-guests`` routes do
not: switching the lists off stops new sign-ups, not the answer to someone
asking what is stored about them, or to delete it. They live under
``/list-guests`` because ``GET /users/{user_id}`` would shadow a path under
``/users``.

``send_guest_mail`` is imported by name so tests can replace it here.
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    CurrentSuperuser,
    CurrentUser,
    DBDep,
    require_shared_lists_enabled,
)
from app.core.errors import raise_problem
from app.crud.shared_list import shared_list as crud_shared_list
from app.crud.shared_list_guest import shared_list_guest as crud_guest
from app.logic import clock
from app.logic.permissions import (
    SharedListAccess,
    require_shared_list_visible,
    shared_list_scope,
)
from app.logic.shared_lists import guest_quota
from app.logic.shared_lists.erase import erase_guests
from app.logic.shared_lists.guest_mail import send_guest_mail
from app.logic.shared_lists.public_page import build_public_list
from app.logic.shared_lists.removal import remove_signups
from app.logic.shared_lists.signups_query import (
    export_guest,
    list_signups,
    search_guests,
)
from app.models.event import Event
from app.models.shared_list import SharedList
from app.models.user import User
from app.schemas.public_shared_list import PublicSharedList
from app.schemas.shared_list import SortDir
from app.schemas.shared_list_guest import (
    ListGuestAdminListResponse,
    ListGuestExport,
    MailSuppressionLift,
    SharedListSignupListResponse,
    SharedListSignupRemoveRequest,
    SharedListSignupRemoveResult,
    SignupSort,
)

router = APIRouter(tags=["shared-list-guests"])

#: The kill switch, on the organisers' routes only.
_ENABLED = [Depends(require_shared_lists_enabled)]


async def _visible_list(
    session: AsyncSession, user: User, list_id: uuid.UUID
) -> tuple[SharedList, Event, SharedListAccess]:
    """The list, its event and the caller's access, after the read gate."""
    shared_list = await crud_shared_list.get(session, shared_list_id=list_id)
    if shared_list is None:
        raise_problem(404, code="shared_list.not_found", detail="Shared list not found")
    access = await require_shared_list_visible(user, session, shared_list)
    event = await session.get(Event, shared_list.event_id)
    assert event is not None  # shared_lists.event_id is a foreign key
    return shared_list, event, access


@router.get(
    "/shared-lists/{list_id}/signups",
    response_model=SharedListSignupListResponse,
    dependencies=_ENABLED,
)
async def list_shared_list_signups(
    list_id: uuid.UUID,
    session: DBDep,
    current_user: CurrentUser,
    sort_by: SignupSort = "created_at",
    sort_dir: SortDir | None = None,
    q: str | None = Query(default=None, max_length=100),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> SharedListSignupListResponse:
    """The list's confirmed sign-ups, a page at a time.

    ``sort_dir`` defaults to newest first for ``created_at`` and ascending
    otherwise. Event admins see every sign-up; a person in charge those on
    their tasks, with ``hidden_count`` for the rest.
    """
    shared_list, event, _ = await _visible_list(session, current_user, list_id)
    scope = await shared_list_scope(current_user, session, event)
    items, total, hidden = await list_signups(
        session,
        shared_list=shared_list,
        # Explicit: an empty set of managed tasks means none, never all.
        task_ids=None if scope.is_admin else scope.managed_task_ids,
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        skip=skip,
        limit=limit,
        now_wall=clock.wall_clock_now(event.timezone),
    )
    return SharedListSignupListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        hidden_count=hidden,
        can_erase=scope.is_admin,
    )


@router.post(
    "/shared-lists/{list_id}/signups/remove",
    response_model=SharedListSignupRemoveResult,
    dependencies=_ENABLED,
)
async def remove_shared_list_signups(
    list_id: uuid.UUID,
    body: SharedListSignupRemoveRequest,
    session: DBDep,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> SharedListSignupRemoveResult:
    """Take guests off shifts they signed up for through this list.

    Partial success: what may not be removed is listed in ``skipped``. With
    ``notify`` each guest taken off gets one mail; with ``erase`` (event
    admins only) their data is erased instead, and nobody is mailed.
    """
    shared_list, event, access = await _visible_list(session, current_user, list_id)
    outcome = await remove_signups(
        session,
        user=current_user,
        shared_list=shared_list,
        event=event,
        access=access,
        request=body,
        now=clock.utc_now(),
        now_wall=clock.wall_clock_now(event.timezone),
    )
    for mail in outcome.mails:
        background_tasks.add_task(send_guest_mail, mail)
    return outcome.result


@router.get(
    "/shared-lists/{list_id}/preview",
    response_model=PublicSharedList,
    dependencies=_ENABLED,
)
async def preview_shared_list(
    list_id: uuid.UUID, session: DBDep, current_user: CurrentUser
) -> PublicSharedList:
    """The public page as strangers see it now; not counted as a view."""
    shared_list, event, _ = await _visible_list(session, current_user, list_id)
    return await build_public_list(session, shared_list, event=event)


@router.get("/list-guests", response_model=ListGuestAdminListResponse)
async def search_list_guests(
    session: DBDep,
    _: CurrentSuperuser,
    q: str = Query(min_length=3, max_length=100),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ListGuestAdminListResponse:
    """Find guests by address (exact), name or phone number (in part)."""
    items, total = await search_guests(session, q=q, skip=skip, limit=limit)
    return ListGuestAdminListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get("/list-guests/{guest_user_id}", response_model=ListGuestExport)
async def export_list_guest(
    guest_user_id: uuid.UUID, session: DBDep, _: CurrentSuperuser
) -> ListGuestExport:
    """Everything stored about one guest."""
    export = await export_guest(session, user_id=guest_user_id)
    if export is None:
        raise_problem(404, code="guest_signup.not_found", detail="Guest not found")
    return export


@router.post("/list-guests/{guest_user_id}/erase", status_code=204)
async def erase_list_guest(
    guest_user_id: uuid.UUID, session: DBDep, _: CurrentSuperuser
) -> None:
    """Erase one guest's data, as their own "Meine Daten löschen" does.

    404 ``guest_signup.not_found`` also for a guest that a confirmation
    merged into its address's guest account while this waited for its row:
    the sign-ups are the account's now, and the search finds them there by
    their names.
    """
    # Locked first, as on every path that changes a guest, and only then
    # read: a merge holding the row deletes the user before it lets go. One
    # whose event was deleted has no row left to lock.
    await crud_guest.get_for_update(session, user_id=guest_user_id)
    user = await session.get(User, guest_user_id)
    if user is None or not user.is_list_guest:
        raise_problem(404, code="guest_signup.not_found", detail="Guest not found")
    await erase_guests(session, user_ids=[guest_user_id], now=clock.utc_now())


@router.post("/list-guests/mail-suppressions/lift", status_code=204)
async def lift_mail_suppression(
    body: MailSuppressionLift, session: DBDep, _: CurrentSuperuser
) -> None:
    """Mail an address again after "Das war ich nicht", when its owner asks:
    they may have chosen it by mistake, or someone else reading the mailbox
    did. 404 ``guest_signup.not_suppressed`` when nothing stops mail to it."""
    if not await guest_quota.lift_suppression(session, address=body.email):
        raise_problem(
            404,
            code="guest_signup.not_suppressed",
            detail="Mail to this address is not stopped",
        )
