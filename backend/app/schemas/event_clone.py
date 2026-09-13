"""Request/response shapes for ``POST /events/{event_id}/clone``.

Cloning is "run this event again next year": a new event, the same tasks, the
same shift grid, shifted by however far the new start date sits from the old
one. It is deliberately *not* a deep copy — bookings and the source's featured
or sandbox flags never travel.
"""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.event import EventRead, EventVisibility
from app.schemas.task import TaskStatus

#: How a task's shifts are reproduced in the clone.
#:
#: ``copy`` re-creates every source shift row at its shifted date. ``regenerate``
#: re-runs the shift generator from the stored batch configuration.
#:
#: ``copy`` is the default on purpose. ``excluded_shifts`` and ``specific_dates``
#: are persisted nowhere, and ``remainder_mode`` lives only on the batch — so
#: regenerating from stored config silently fills in days the organiser skipped
#: and can drop the trailing partial shift of every day. Copying is the faithful
#: reproduction; regenerating is the escape hatch for a task whose shift rows
#: were hand-edited into a mess.
CloneMode = Literal["copy", "regenerate"]


class EventCloneTask(BaseModel):
    """One source task to reproduce in the clone, with optional overrides.

    Every override is optional; omitting one keeps the source value (dates keep
    the source value *plus the clone's date offset*).
    """

    source_task_id: uuid.UUID
    mode: CloneMode = "copy"

    name: str | None = None
    status: TaskStatus | None = None
    location: str | None = None
    category: str | None = None

    #: Default: the source task's dates moved by the clone's offset. Setting
    #: ``start_date`` re-dates the task's batches, shifts and overrides with
    #: it — the whole task moves, not just its header row.
    start_date: dt.date | None = None
    end_date: dt.date | None = None

    #: Stored generation config. These are always written onto the cloned Task
    #: row, but they only change the *shifts* under ``mode="regenerate"`` —
    #: ``copy`` reproduces the source shift rows verbatim by definition.
    default_start_time: dt.time | None = None
    default_end_time: dt.time | None = None
    shift_duration_minutes: int | None = None
    people_per_shift: int | None = None


class EventCloneAnnounce(BaseModel):
    """Whether to tell the new event's members about it, and what to add."""

    send: bool = False
    note: str | None = Field(default=None, max_length=500)


class EventCloneRequest(BaseModel):
    name: str
    #: The whole clone is offset by ``start_date - source.start_date``.
    start_date: dt.date
    #: Default: the source's duration, preserved.
    end_date: dt.date | None = None
    #: Default: copied from the source. Send ``null`` explicitly to clear it.
    description: str | None = None
    #: Private by default — a clone starts as a draft nobody else can find.
    visibility: EventVisibility = "private"
    #: Copy the source's default_start_time/default_end_time.
    copy_defaults: bool = True
    #: Copy the source roster (owners are demoted to admin; see the route).
    copy_members: bool = False
    #: The tasks to reproduce, in order. Empty means "just the event shell".
    #: Capped because one request clones every batch and every shift row of
    #: every task named here, in a single transaction. Naming the same task
    #: twice is rejected (``event.duplicate_task``).
    tasks: list[EventCloneTask] = Field(default=[], max_length=50)
    announce: EventCloneAnnounce | None = None


class EventCloneResponse(BaseModel):
    event: EventRead
    tasks_created: int
    shifts_created: int
    members_copied: int
    notified: bool
