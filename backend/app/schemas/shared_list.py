"""Shared lists as the organisers see them: the management tables, the detail
dialog and the create/edit wizard.

Every count and status here is worked out on the event's clock when it is read
(``app.logic.shared_lists.overview``), never stored. Times of day and
``closes_at`` are the event's wall clock; ``created_at`` and the other stamps
are naive UTC, as everywhere.
"""

import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from app.logic.permissions import SharedListAccess
from app.logic.shared_lists.offer import EffectiveStatus
from app.models.shared_list import AskMode, EndsMode, ListStatus, ShowNames

ListTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


def _blank_to_none(value: str) -> str | None:
    return value or None


#: Optional free text: surrounding blanks are dropped, and nothing left means
#: "not given".
Intro = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=1000),
    AfterValidator(_blank_to_none),
]
ShareNote = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=120),
    AfterValidator(_blank_to_none),
]

#: Which lists the management table shows: every one that has not ended, the
#: ones with something to do (``issue``), or one effective status.
ListFilter = Literal["active", "todo", "live", "paused", "ended"]
ListSort = Literal["status", "created_at", "title", "signups", "free", "closes"]
TaskFilter = Literal["all", "todo"]
TaskSort = Literal["name", "free", "unlisted_free"]
SortDir = Literal["asc", "desc"]
BulkAction = Literal["pause", "resume", "end"]


# --- Rows of the lists table ------------------------------------------------


class SharedListTaskRef(BaseModel):
    id: uuid.UUID
    name: str


class SharedListIssue(BaseModel):
    """Something on a list an organiser should act on."""

    #: ``stranded``: a paused or expired list holds free places that no live
    #: list offers. ``expires_soon``: a list closing on a day at most three
    #: days away still has free places.
    kind: Literal["stranded", "expires_soon"]
    #: ``stranded``: the free places no live list offers; ``expires_soon``:
    #: every free place on the list.
    free: int
    #: The tasks those places belong to, once each, in the list's order.
    task_names: list[str]
    #: ``expires_soon`` only: days until the closing day, 0 for today.
    days_left: int | None = None


class SharedListRow(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    share_note: str | None
    status: ListStatus
    effective_status: EffectiveStatus
    ends_mode: EndsMode
    ends_on: dt.date | None
    #: When the list closes by itself, on the event's wall clock; None when
    #: it stays open until someone ends it.
    closes_at: dt.datetime | None
    expires_soon: bool
    #: It still offers shifts, and none of them has a free place.
    is_full: bool
    created_at: dt.datetime
    created_by_name: str | None
    #: The list's tasks that are still in its event, in the list's order.
    tasks: list[SharedListTaskRef]
    #: The days the list offers shifts on, when it leaves out every shift of
    #: some day its tasks have; None when it offers every day.
    only_days: list[dt.date] | None
    #: Shifts left out of the list that have not started yet.
    excluded_shift_count: int
    #: Places on the shifts the list offers now (included and not started).
    capacity: int
    free: int
    #: Confirmed bookings made through this list.
    signup_count: int
    #: Of those, the ones whose person has no account.
    guest_count: int
    view_count: int
    #: Only for callers who may change the list, and never once it has ended.
    issue: SharedListIssue | None
    access: SharedListAccess


class SharedListCounts(BaseModel):
    """How many visible lists each filter chip holds, whatever ``q`` says."""

    active: int
    todo: int
    live: int
    paused: int
    ended: int


class SharedListListResponse(BaseModel):
    items: list[SharedListRow]
    total: int
    skip: int
    limit: int
    counts: SharedListCounts
    #: Ended lists matching ``q``, for "N ended lists are hidden".
    ended_matching: int


class SharedListReusable(BaseModel):
    """The list a printed notice of some tasks reuses."""

    #: None when the caller manages no list of those tasks that has not ended.
    list: SharedListRow | None


# --- Overview ---------------------------------------------------------------


class SharedListSummary(BaseModel):
    live_lists: int
    #: Lists that have not ended (open, paused or expired): the "Links" tab's count.
    active_lists: int
    signups: int
    guests: int
    #: Free places on the shifts live lists offer, each shift counted once.
    free_in_live: int


class UnsharedNotice(BaseModel):
    """Tasks the caller may share whose free places no live list offers."""

    task_count: int
    free: int
    #: The first two of them by name.
    task_names: list[str]


class SharedListOverview(BaseModel):
    summary: SharedListSummary
    unshared: UnsharedNotice
    #: An event admin, or a person in charge of a task they could share while
    #: the event lets them (``managers_share_lists``).
    can_create: bool
    #: An event admin, with a live list to pause.
    can_pause_all: bool
    is_admin: bool
    managers_share_lists: bool
    event_timezone: str


# --- Tasks table ------------------------------------------------------------


class SharedListChip(BaseModel):
    id: uuid.UUID
    title: str
    effective_status: EffectiveStatus


class TeamRef(BaseModel):
    id: uuid.UUID
    name: str


class SharedListTaskRow(BaseModel):
    """A published task with shifts ahead, and the lists it is on.

    The shift figures cover the shifts that have not started, whether a list
    offers them or not.
    """

    id: uuid.UUID
    name: str
    location: str | None
    manager_names: list[str]
    shift_count: int
    dates: list[dt.date]
    capacity: int
    free: int
    #: Only the team's members may book it, so no list can offer it.
    team: TeamRef | None
    #: The lists it is on that have not ended.
    lists: list[SharedListChip]
    ended_list_count: int
    #: Free places no live list offers; 0 for a team task.
    stranded_free: int
    #: Of those, the ones no list offers at all, paused or expired included.
    unlisted_free: int
    can_share: bool


class SharedListTaskCounts(BaseModel):
    all: int
    todo: int


class SharedListTaskListResponse(BaseModel):
    items: list[SharedListTaskRow]
    total: int
    skip: int
    limit: int
    counts: SharedListTaskCounts


# --- The wizard's choices ----------------------------------------------------


class SharedListCandidate(BaseModel):
    """A task the caller may put on a list, with its shifts that have not
    started."""

    id: uuid.UUID
    name: str
    location: str | None
    manager_names: list[str]
    shift_count: int
    dates: list[dt.date]
    capacity: int
    free: int
    #: Set on a team task, which is listed only when searching, to say why it
    #: cannot be chosen.
    team: TeamRef | None
    #: The task earns vouchers. The wizard says that guests earn them too.
    earns_vouchers: bool


class SharedListCandidateListResponse(BaseModel):
    items: list[SharedListCandidate]
    total: int
    skip: int
    limit: int
    #: Team tasks among the caller's tasks, whatever ``q`` says, with the
    #: first three names, for the hint shown without a search.
    locked_count: int
    locked_names: list[str]


class SharedListCandidateShift(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    date: dt.date
    start_time: dt.time | None
    end_time: dt.time | None
    capacity: int
    free: int


# --- Create and edit ---------------------------------------------------------


class SharedListCreate(BaseModel):
    title: ListTitle
    intro: Intro | None = None
    share_note: ShareNote | None = None
    #: The order is the list's order.
    task_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    #: Shifts of those tasks to leave out. Ids of other shifts are ignored.
    excluded_shift_ids: list[uuid.UUID] = Field(default_factory=list, max_length=2000)
    ask_email: AskMode = "required"
    ask_phone: AskMode = "off"
    show_names: ShowNames = "none"
    #: None: as many shifts as are free.
    max_per_person: int | None = Field(default=None, ge=1, le=50)
    ends_mode: EndsMode = "last_shift"
    #: Required with ``ends_mode="date"`` and ignored otherwise.
    ends_on: dt.date | None = None


class SharedListUpdate(BaseModel):
    """Any field of :class:`SharedListCreate`; the code stays the same.

    A field left out keeps its value. So does an explicit null on a field that
    always has one (title, tasks, exclusions, the ask and show settings, the
    ends mode); on ``intro``, ``share_note``, ``max_per_person`` and ``ends_on``
    null is a value. A change of ``show_names`` applies to new sign-ups only:
    each guest keeps what they were told.
    """

    title: ListTitle | None = None
    intro: Intro | None = None
    share_note: ShareNote | None = None
    task_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=50)
    excluded_shift_ids: list[uuid.UUID] | None = Field(default=None, max_length=2000)
    ask_email: AskMode | None = None
    ask_phone: AskMode | None = None
    show_names: ShowNames | None = None
    max_per_person: int | None = Field(default=None, ge=1, le=50)
    ends_mode: EndsMode | None = None
    ends_on: dt.date | None = None


# --- Detail -------------------------------------------------------------------


class SharedListDetailTask(BaseModel):
    """A task linked to the list, and what the list offers of it."""

    id: uuid.UUID
    name: str
    offered: bool
    #: Why the list offers none of its shifts: limited to a team, not
    #: published, or moved to another event.
    not_offered_reason: Literal["team_locked", "not_published", "moved"] | None
    shift_count: int
    capacity: int
    free: int
    only_days: list[dt.date] | None


class SharedListEventRef(BaseModel):
    id: uuid.UUID
    name: str
    start_date: dt.date
    end_date: dt.date
    timezone: str


class SharedListDetail(SharedListRow):
    intro: str | None
    ask_email: AskMode
    ask_phone: AskMode
    show_names: ShowNames
    max_per_person: int | None
    rotated_at: dt.datetime | None
    paused_at: dt.datetime | None
    ended_at: dt.datetime | None
    #: Every linked task, in the list's order, for the wizard.
    task_ids: list[uuid.UUID]
    excluded_shift_ids: list[uuid.UUID]
    detail_tasks: list[SharedListDetailTask]
    event: SharedListEventRef


# --- Several at once --------------------------------------------------------


class SharedListBulkRequest(BaseModel):
    action: BulkAction
    list_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class SharedListBulkSkip(BaseModel):
    id: uuid.UUID
    #: The error code the single action would have answered with, e.g.
    #: ``shared_list.ended``.
    code: str


class SharedListBulkResult(BaseModel):
    """What a bulk action did. A list that already was as asked is in
    neither list."""

    changed: list[uuid.UUID]
    skipped: list[SharedListBulkSkip]


class SharedListPauseAllRequest(BaseModel):
    #: Also switch ``managers_share_lists`` off, so a person in charge cannot
    #: reopen their own list after an emergency stop.
    lock_managers: bool = False
