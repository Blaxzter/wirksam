"""PATCH semantics for ``location_id`` on tasks and shifts.

The create paths call :func:`app.logic.locations.resolve_location` and
:func:`app.logic.locations.apply_location` directly; a partial update needs one
more decision (what was sent, and what is already stored), which lives here so
``PATCH /tasks/{id}`` and ``PATCH /shifts/{id}`` agree.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.logic.locations import HasLocation, resolve_location


async def location_patch(
    session: AsyncSession,
    obj: HasLocation,
    update_data: dict[str, Any],
    *,
    event_id: uuid.UUID | None,
) -> dict[str, Any]:
    """The ``location`` / ``location_id`` values a partial update should write.

    ``update_data`` is the ``exclude_unset`` dump of the request.

    - ``location_id`` sent (also ``null``): it wins. A location's name becomes
      the text; ``null`` clears the link and keeps the sent text, or the stored
      one when no text was sent.
    - Only ``location`` sent, and it differs from the stored text: the row now
      carries free text, so a stored link is dropped. Otherwise the link would
      point at a place whose name no longer matches what everybody sees.
    - Neither sent: nothing changes.
    """
    if "location_id" in update_data:
        loc = await resolve_location(
            session, event_id=event_id, location_id=update_data["location_id"]
        )
        if loc is not None:
            return {"location_id": loc.id, "location": loc.name}
        return {
            "location_id": None,
            "location": update_data.get("location", obj.location),
        }
    if (
        "location" in update_data
        and obj.location_id is not None
        and update_data["location"] != obj.location
    ):
        return {"location_id": None}
    return {}
