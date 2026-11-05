"""Write semantics for ``location_id`` on tasks, shift batches and shifts.

A row that points at a :class:`Location` also carries its name in the
``location`` text column. That text is the display value every read path uses,
so the two have to be written together: :func:`apply_location` sets both,
:func:`propagate_rename` keeps the copies current when a location is renamed, and
:func:`follow_task_place` takes a task's new place to what still has its old one.
"""

import uuid
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.core.errors import raise_problem
from app.models.location import Location
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task


class HasLocation(Protocol):
    location: str | None
    location_id: uuid.UUID | None


#: A place as a row stores it: the text everybody sees and the link, if any.
Place = tuple[str | None, uuid.UUID | None]


async def resolve_location(
    session: AsyncSession,
    *,
    event_id: uuid.UUID | None,
    location_id: uuid.UUID | None,
) -> Location | None:
    """Load ``location_id`` and check it belongs to ``event_id``.

    ``None`` in gives ``None`` out. A location that does not exist, belongs to
    another event, or is offered for a row with no event at all is a 422
    ``location.wrong_event``: the caller sent an id that cannot apply here, and
    whether it exists elsewhere is none of their business.
    """
    if location_id is None:
        return None
    loc = await session.get(Location, location_id)
    if loc is None or event_id is None or loc.event_id != event_id:
        raise_problem(
            422,
            code="location.wrong_event",
            detail="Location does not belong to this event",
        )
    return loc


def apply_location(obj: HasLocation, loc: Location | None, text: str | None) -> None:
    """Point ``obj`` at ``loc`` (name copied into the text), or clear the id.

    Without a location the free ``text`` is kept as the display value.
    """
    if loc is not None:
        obj.location_id = loc.id
        obj.location = loc.name
    else:
        obj.location_id = None
        obj.location = text


async def propagate_rename(
    session: AsyncSession, location_id: uuid.UUID, new_name: str
) -> None:
    """Rewrite the ``location`` text of every row pointing at ``location_id``."""
    for model in (Task, ShiftBatch, Shift):
        await session.execute(
            update(model)
            .where(col(model.location_id) == location_id)
            .values(location=new_name)
            .execution_options(synchronize_session="fetch")
        )


def has_place(obj: HasLocation, place: Place) -> bool:
    """Whether ``obj`` still shows ``place`` rather than a place of its own.

    The text decides, because that is what everybody sees. A link to a different
    location is a place of its own even under the same name.
    """
    text, location_id = place
    return (obj.location or None) == (text or None) and obj.location_id in (
        None,
        location_id,
    )


async def follow_task_place(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    old: Place,
    new: Place,
    shifts: bool = True,
) -> None:
    """Take a task's new place to its batches and shifts still showing the old one.

    Anything with a place of its own keeps it (:func:`has_place`). The batches
    come along because a batch is what its later shifts are generated from.
    """
    models = (ShiftBatch, Shift) if shifts else (ShiftBatch,)
    for model in models:
        rows = await session.execute(select(model).where(col(model.task_id) == task_id))
        for row in rows.scalars():
            if has_place(row, old):
                row.location, row.location_id = new
                session.add(row)


async def unlink_task_children(session: AsyncSession, task_id: uuid.UUID) -> None:
    """Drop the location link on a task's batches and shifts, keeping the text.

    Used when a task moves to another event: its locations stay behind, and a
    link left in place would let the old event's renames rewrite rows that now
    belong to the new one.
    """
    for model in (ShiftBatch, Shift):
        await session.execute(
            update(model)
            .where(
                col(model.task_id) == task_id,
                col(model.location_id).is_not(None),
            )
            .values(location_id=None)
            .execution_options(synchronize_session="fetch")
        )
