"""What a demo event must not do, refused in one place.

Shared by the event routes (invitations, clone) and the task routes (inviting
people in charge by e-mail), so neither router has to import the other.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import raise_problem
from app.crud.event import event as crud_event


async def refuse_if_sandbox(
    session: AsyncSession,
    event_id: uuid.UUID,
    *,
    code: str = "sandbox.invitations_disabled",
    detail: str = "Invitations cannot be sent from a demo event",
) -> None:
    """Block anything a demo event must not do.

    A guest is seeded as ``owner`` of their sandbox so the manager tour can
    show them the screens an organiser uses. That role passes
    ``require_event_role(minimum="admin")``, which means the invitation
    endpoints would happily post an email to any address an anonymous visitor
    typed in. The existing ``demo|`` guard does not help here: it tests the
    *recipient*, and the recipient of an invitation is whoever was named.

    The tour visits these screens deliberately and explains that sending is
    switched off in the demo, so this is the enforcement behind that sentence.

    ``code``/``detail`` default to the invitation wording every existing caller
    wants; cloning passes its own so a refused clone does not talk about
    invitations.
    """
    event = await crud_event.get(session, event_id, raise_404_error=True)
    if event.is_sandbox:
        raise_problem(403, code=code, detail=detail)
