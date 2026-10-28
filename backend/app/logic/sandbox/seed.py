"""One event's worth of believable data, built around *now*.

The shape here is not arbitrary — it is dictated by the guided tour. Every
screen the tour stops on has an empty state, and an empty state is a worse
first impression than no demo at all, so the seed has a minimum it must satisfy:

* the event spans days either side of today, so the week columns have
  something in every direction and the event never reads as expired;
* shifts land in the past, today and the future, so fill-rate badges, the
  "happening now" markers and the booking history all have material;
* some shifts are full and some are half empty, because a board where
  everything is green teaches the reader nothing about what the app is for;
* the visitor already holds a booking, so "My bookings" is not blank on arrival;
* there are teammates with availabilities, because the staffing heatmap is one
  of the more convincing screens and it needs more than one person;
* the manager variant additionally gets a pending invitation and a pending join
  request, so the two decisions an organiser actually makes are on screen;
* the notification bell carries a badge and the inbox behind it has an entry
  under every classification tab, because nothing the visitor does during the
  tour can produce one — ``NotificationService`` skips a sandbox recipient
  before it writes a row, so a demo inbox is seeded or it is empty forever;
* the tasks point at real locations with venue plans behind them, because a
  sandbox cannot upload an image (``sandbox.upload_disabled``) and the map
  would otherwise be an empty state the visitor can do nothing about; and
  today's shifts at those places are deliberately full, half full and short,
  because the map colours every pin by the day's staffing.

Shifts are produced through ``logic.shift_generator`` and recorded as a real
``ShiftBatch`` with the generation config stored on the task, rather than being
hand-rolled row by row. That is what makes the manager tour's "add more shifts"
step work: the regenerate screen reads that config back, and a task seeded
without it opens an empty form.

Rows are added with ``db.add`` and a single ``flush`` per stage rather than
through ``CRUDBase.create``, which flushes and refreshes once per row — the
difference is a few hundred round trips on every click of the demo button.

The same content doubles as the local dev seed. ``seed_dev_event`` (run by
``just seed`` through ``scripts.seed_demo``) builds the manager variant as an
ordinary, permanent event: ``is_sandbox`` is off on the event, its tasks and
every made-up person, and there is no ``sandbox_expires_at``, so the TTL sweep
never touches it and the sandbox visibility filters do not hide it. The made-up
people get the ``demo|`` subject prefix instead of ``sandbox|`` — still in
``UNDELIVERABLE_SUBJECT_PREFIXES``, and still without an address — so the dev
event can never notify them either. ``seed_sandbox`` is unchanged by this: the
mode only switches those flags, the prefix and the event description.
"""

import datetime as dt
import math
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.crud.event_team import event_team as crud_team
from app.crud.user_availability import user_availability as crud_user_availability
from app.logic.notifications.messages import format_time_until, get_message
from app.logic.sample_document import CONTENT_TYPE as SAMPLE_CONTENT_TYPE
from app.logic.sample_document import FILENAME as SAMPLE_FILENAME
from app.logic.sample_document import render_first_aid_sample
from app.logic.sandbox.venue_plan_shapes import (
    HEIGHT,
    PLAN_KEYS,
    SPOTS,
    WIDTH,
    PlanKey,
    demo_shapes,
    label_text,
)
from app.logic.shift_generator import generate_shifts
from app.logic.team_requirements import add_years
from app.logic.venue_shapes import round_point
from app.models.booking import Booking
from app.models.event import Event
from app.models.event_invitation import EventInvitation
from app.models.event_join_request import EventJoinRequest
from app.models.event_membership import EventMembership
from app.models.event_team import (
    EventTeam,
    EventTeamCheck,
    EventTeamDocument,
    EventTeamMember,
    EventTeamRequirement,
)
from app.models.location import Location
from app.models.notification import Notification
from app.models.shift import Shift
from app.models.shift_batch import ShiftBatch
from app.models.task import Task
from app.models.user import User
from app.models.venue_plan import VenueMarker, VenuePlan, VenueShape
from app.schemas.sandbox import SandboxRole
from app.schemas.user_availability import (
    UserAvailabilityCreate,
    UserAvailabilityDateInput,
)

# The demo is not a stress test — it is a screenshot that happens to be
# interactive. These numbers are what fills the screens the tour visits without
# making the first page load feel slow.
_DAYS_BEFORE_TODAY = 3
_DAYS_AFTER_TODAY = 11
_TEAMMATE_COUNT = 5

# Which of the two reminder offsets every account ships with (see
# ``User.default_reminder_offsets``) the seeded reminder is written against.
# The day-before one, because it is the only one whose send moment reliably
# falls in the past for a shift the visitor has not worked yet.
_REMINDER_OFFSET_MINUTES = 1440

# Subject prefix of every made-up person, by mode. Both are in
# ``UNDELIVERABLE_SUBJECT_PREFIXES``; only ``sandbox|`` is purged with its event.
_SANDBOX_SUBJECT_PREFIX = "sandbox|"
_DEV_SUBJECT_PREFIX = "demo|"


@dataclass(frozen=True, slots=True)
class _GuestBooking:
    """One shift the visitor holds, with the roster standing around them.

    Returned by ``_seed_bookings`` because the inbox is written from it. A
    notification about a shift the visitor is not on, or naming a colleague who
    is not actually rostered beside them, is exactly the kind of detail that
    gives a demo away — and neither is checkable after the fact from the rows
    alone without re-deriving the whole rota.
    """

    booking: Booking
    shift: Shift
    co_workers: tuple[User, ...]

    def starts_at(self) -> dt.datetime:
        """When the shift begins, as a naive datetime to compare against ``now``."""
        return dt.datetime.combine(self.shift.date, self.shift.start_time or dt.time())


@dataclass(frozen=True, slots=True)
class _TaskSpec:
    """One seeded task, in the two languages the app ships."""

    name_en: str
    name_de: str
    description_en: str
    description_de: str
    location_en: str
    location_de: str
    location_desc_en: str
    location_desc_de: str
    #: Which demo plan the location's marker sits on, and at which drawn spot
    #: (a key of ``venue_plan_shapes.SPOTS``); ``None`` keeps it off the map.
    marker: tuple[PlanKey, str] | None
    category_en: str
    category_de: str
    day_offsets: tuple[int, ...]
    start_hour: int
    end_hour: int
    duration_minutes: int
    people_per_shift: int
    #: How full today's shifts of this task are made, as a share of their
    #: places. The map colours each place by the day's staffing, and pills
    #: that all come out one colour show nothing; ``None`` leaves today to
    #: the random fill like every other day.
    today_fill: float | None = None
    #: The key of the seeded team (``_TEAMS``) that alone may book this task.
    team: str | None = None

    def name(self, lang: str) -> str:
        return self.name_de if lang == "de" else self.name_en

    def description(self, lang: str) -> str:
        return self.description_de if lang == "de" else self.description_en

    def location(self, lang: str) -> str:
        return self.location_de if lang == "de" else self.location_en

    def location_desc(self, lang: str) -> str:
        return self.location_desc_de if lang == "de" else self.location_desc_en

    def category(self, lang: str) -> str:
        return self.category_de if lang == "de" else self.category_en


# Deliberately mundane. A demo event about a summer festival invites the reader
# to imagine their own rota; one about "Demo Task 1" invites them to close the
# tab. Offsets are relative to today, so the data is always current.
#
# The first spec must start strictly before every other one: the board sorts
# tasks by start date, and the tour's bookable chip is reserved on the first
# spec (see ``_seed_bookings``), so it has to be the first row on screen.
_TASK_SPECS: tuple[_TaskSpec, ...] = (
    _TaskSpec(
        name_en="Welcome desk",
        name_de="Empfang",
        description_en=(
            "Greet arrivals, hand out programmes and point people at the right "
            "hall. The busiest hour is the first one."
        ),
        description_de=(
            "Ankommende begrüßen, Programme austeilen und den Weg zur richtigen "
            "Halle zeigen. Die erste Stunde ist die vollste."
        ),
        location_en="Main entrance",
        location_de="Haupteingang",
        location_desc_en=(
            "The glass doors on **Riverside Road**. The desk is just inside, "
            "facing the door."
        ),
        location_desc_de=(
            "Die Glastüren am **Uferweg**. Der Tisch steht gleich hinter dem Eingang."
        ),
        marker=("indoor", "welcome_desk"),
        category_en="Front of house",
        category_de="Empfang",
        day_offsets=(-2, 0, 1, 3, 5),
        start_hour=9,
        end_hour=15,
        duration_minutes=120,
        people_per_shift=2,
        today_fill=1.0,
    ),
    _TaskSpec(
        name_en="Café counter",
        name_de="Cafétheke",
        description_en=(
            "Coffee, cake and washing up. Two people per shift, one on the "
            "machine and one on the till."
        ),
        description_de=(
            "Kaffee, Kuchen und Abwasch. Zwei Personen pro Schicht, eine an der "
            "Maschine und eine an der Kasse."
        ),
        location_en="Foyer café",
        location_de="Foyer-Café",
        location_desc_en=(
            "Counter along the back wall of the foyer. Aprons and the till key "
            "are in the cupboard under the coffee machine."
        ),
        location_desc_de=(
            "Theke an der Rückwand des Foyers. Schürzen und der Kassenschlüssel "
            "liegen im Schrank unter der Kaffeemaschine."
        ),
        marker=("indoor", "cafe_counter"),
        category_en="Catering",
        category_de="Verpflegung",
        day_offsets=(-1, 0, 2, 4, 6),
        start_hour=10,
        end_hour=16,
        duration_minutes=90,
        people_per_shift=2,
        today_fill=0.5,
    ),
    _TaskSpec(
        name_en="Stage crew",
        name_de="Bühnentechnik",
        description_en=(
            "Set up between acts, mind the cables and pack down at the end. "
            "Some heavy lifting."
        ),
        description_de=(
            "Zwischen den Auftritten umbauen, auf die Kabel achten und am Ende "
            "abbauen. Teilweise schweres Heben."
        ),
        location_en="Main hall",
        location_de="Große Halle",
        location_desc_en=(
            "Through the foyer and straight on. Crew meet **at the side of the "
            "stage**, not in front of it."
        ),
        location_desc_de=(
            "Durch das Foyer und geradeaus. Treffpunkt ist **seitlich der "
            "Bühne**, nicht davor."
        ),
        marker=("indoor", "stage"),
        category_en="Technical",
        category_de="Technik",
        day_offsets=(0, 1, 4, 7, 9),
        start_hour=14,
        end_hour=20,
        duration_minutes=120,
        people_per_shift=3,
        today_fill=0.2,
    ),
    _TaskSpec(
        name_en="Closing tidy-up",
        name_de="Aufräumen",
        description_en=(
            "The unglamorous one: stacking chairs, taking the bins out and "
            "sweeping the floor. An hour with enough hands, a whole evening without."
        ),
        description_de=(
            "Die undankbare Schicht: Stühle stapeln, Müll rausbringen, fegen. "
            "Mit genug Händen dauert das eine Stunde, sonst einen ganzen Abend."
        ),
        location_en="Whole venue",
        location_de="Gesamtes Gelände",
        location_desc_en="Everywhere at once. Start in the main hall and work outwards.",
        location_desc_de="Überall gleichzeitig. Am besten in der Halle anfangen.",
        marker=None,
        category_en="Logistics",
        category_de="Logistik",
        day_offsets=(0, 3, 6, 8, 10),
        start_hour=18,
        end_hour=21,
        duration_minutes=90,
        people_per_shift=4,
    ),
    _TaskSpec(
        name_en="Grill stand",
        name_de="Grillstand",
        description_en=(
            "Sausages, halloumi and corn on the cob. One on the grill, one on "
            "the buns, one taking the money."
        ),
        description_de=(
            "Würstchen, Halloumi und Maiskolben. Eine Person am Grill, eine an "
            "den Brötchen, eine an der Kasse."
        ),
        location_en="Food stalls",
        location_de="Essensstände",
        location_desc_en=(
            "The row of stalls along the top of the meadow. The grill is the "
            "**middle stall**; gas and tongs are in the crate behind it."
        ),
        location_desc_de=(
            "Die Reihe Stände am oberen Rand der Festwiese. Der Grill ist der "
            "**mittlere Stand**, Gas und Zangen liegen in der Kiste dahinter."
        ),
        marker=("outdoor", "food_stalls"),
        category_en="Catering",
        category_de="Verpflegung",
        day_offsets=(-1, 0, 2, 5, 7),
        start_hour=11,
        end_hour=19,
        duration_minutes=120,
        people_per_shift=3,
        today_fill=1.0,
    ),
    _TaskSpec(
        name_en="Wristband check",
        name_de="Bändchenkontrolle",
        description_en=(
            "Check wristbands at the meadow gate and sell day passes to anyone "
            "without one. Friendly but firm."
        ),
        description_de=(
            "Am Wiesentor die Bändchen kontrollieren und Tageskarten an alle "
            "ohne verkaufen. Freundlich, aber bestimmt."
        ),
        location_en="Meadow gate",
        location_de="Wiesentor",
        location_desc_en=(
            "Where the path from **Riverside Road** reaches the meadow. Pick "
            "up the cash box at the info desk in the foyer."
        ),
        location_desc_de=(
            "Wo der Weg vom **Uferweg** auf die Festwiese trifft. Die Kasse "
            "holst du am Infotisch im Foyer ab."
        ),
        marker=("outdoor", "meadow_gate"),
        category_en="Front of house",
        category_de="Empfang",
        day_offsets=(-1, 0, 1, 6, 8),
        start_hour=10,
        end_hour=18,
        duration_minutes=120,
        people_per_shift=2,
        today_fill=0.5,
        team="cash_desk",
    ),
    _TaskSpec(
        name_en="Kids' games",
        name_de="Kinderspiele",
        description_en=(
            "Sack races, face paint and the sandpit. Someone has to keep count "
            "of the buckets."
        ),
        description_de=(
            "Sackhüpfen, Kinderschminken und der Sandkasten. Irgendwer muss die "
            "Eimer zählen."
        ),
        location_en="Kids' corner",
        location_de="Kinderecke",
        location_desc_en=(
            "The round sandpit on the meadow, right of the beer tables. Games "
            "and face paint are in the blue box."
        ),
        location_desc_de=(
            "Der runde Sandkasten auf der Festwiese, rechts von den "
            "Biertischen. Spiele und Schminke sind in der blauen Kiste."
        ),
        marker=("outdoor", "kids_corner"),
        category_en="Programme",
        category_de="Programm",
        day_offsets=(0, 2, 4, 6, 9),
        start_hour=13,
        end_hour=17,
        duration_minutes=120,
        people_per_shift=2,
        today_fill=0.75,
        team="childcare",
    ),
    _TaskSpec(
        name_en="Parking marshals",
        name_de="Parkplatzeinweisung",
        description_en=(
            "Wave cars into the bays and keep the lane to the road clear. "
            "High-vis vests provided."
        ),
        description_de=(
            "Autos in die Lücken winken und die Zufahrt zur Straße freihalten. "
            "Warnwesten liegen bereit."
        ),
        location_en="Car park",
        location_de="Parkplatz",
        location_desc_en=(
            "Next to the building, way in from **Riverside Road**. Meet in "
            "the middle lane."
        ),
        location_desc_de=(
            "Neben dem Gebäude, Einfahrt vom **Uferweg**. Treffpunkt ist die "
            "mittlere Fahrgasse."
        ),
        marker=("outdoor", "car_park"),
        category_en="Logistics",
        category_de="Logistik",
        day_offsets=(0, 3, 7, 10),
        start_hour=9,
        end_hour=13,
        duration_minutes=120,
        people_per_shift=2,
        today_fill=0.25,
    ),
)

# The demo plans in tab order, by their key in ``venue_plan_shapes``.
_PLAN_NAMES: dict[PlanKey, dict[str, str]] = {
    "indoor": {"en": "Building", "de": "Gebäude"},
    "outdoor": {"en": "Outdoor area", "de": "Außengelände"},
}

# The generic markers: (plan, kind, spot in ``SPOTS``, label by language).
# Between them they use every generic kind, so the demo shows the whole set.
_GENERIC_MARKERS: tuple[tuple[PlanKey, str, str, dict[str, str] | None], ...] = (
    (
        "indoor",
        "entrance",
        "side_entrance",
        {"en": "Side entrance", "de": "Seiteneingang"},
    ),
    ("indoor", "info_desk", "info_desk", None),
    ("indoor", "kitchen", "kitchen", None),
    ("indoor", "first_aid", "first_aid", None),
    ("indoor", "toilets", "toilets", None),
    ("outdoor", "entrance", "side_gate", {"en": "Side gate", "de": "Seitentor"}),
    (
        "outdoor",
        "first_aid",
        "first_aid_tent",
        {"en": "First-aid tent", "de": "Sanitätszelt"},
    ),
    ("outdoor", "toilets", "toilets", None),
    ("outdoor", "parking", "bike_parking", {"en": "Bikes", "de": "Fahrräder"}),
)

_TEAMMATE_NAMES: tuple[tuple[str, str], ...] = (
    ("Mira Lindqvist", "Empfang"),
    ("Tomas Neruda", "Verpflegung"),
    ("Adaeze Okafor", "Technik"),
    ("Ben Halvorsen", "Logistik"),
    ("Yuki Tanabe", "Empfang"),
)

_EVENT_NAME = {
    "en": "Riverside Summer Festival",
    "de": "Sommerfest am Fluss",
}
_EVENT_DESCRIPTION = {
    "en": (
        "A three-weekend village festival run entirely by volunteers. This is a "
        "demo event: everything in it is made up, and it disappears when you "
        "leave."
    ),
    "de": (
        "Ein Dorffest über drei Wochenenden, komplett ehrenamtlich gestemmt. "
        "Das ist eine Demo-Veranstaltung: Alles darin ist erfunden und verschwindet, "
        "sobald du gehst."
    ),
}
_DEV_EVENT_DESCRIPTION = {
    "en": (
        "A three-weekend village festival run entirely by volunteers. Made-up "
        "data from `just seed`, for trying the app locally."
    ),
    "de": (
        "Ein Dorffest über drei Wochenenden, komplett ehrenamtlich gestemmt. "
        "Erfundene Daten aus `just seed`, zum lokalen Ausprobieren."
    ),
}
#: Every name the seeded event can carry, so the dev seed can find its own.
SEEDED_EVENT_NAMES: frozenset[str] = frozenset(_EVENT_NAME.values())
_GUEST_NAME = {"en": "Demo visitor", "de": "Demo-Gast"}


def guest_display_name(language: str) -> str:
    """What the guest is called on every shift they book.

    Exposed because ``service`` mints the user before the event exists, and a
    guest showing up as ``None`` on the staffing board undoes the illusion.
    """
    return _GUEST_NAME.get(language, _GUEST_NAME["en"])


async def seed_sandbox(
    db: AsyncSession,
    *,
    owner: User,
    role: SandboxRole,
    language: str,
    now: dt.datetime,
    expires_at: dt.datetime,
) -> Event:
    """Build the demo event and everything in it. Returns the event.

    ``owner`` must already exist and be flushed — the memberships and the
    ``created_by_id`` below need its id.
    """
    return await _seed_event(
        db,
        owner=owner,
        role=role,
        language=language,
        now=now,
        sandbox_expires_at=expires_at,
    )


async def seed_dev_event(
    db: AsyncSession,
    *,
    owner: User,
    language: str,
    now: dt.datetime,
) -> Event:
    """The same event as the manager demo, as an ordinary permanent event.

    For the local dev database (``just seed``): ``owner`` owns it, nothing in
    it is a sandbox row, and it never expires. See the module docstring.
    """
    return await _seed_event(
        db,
        owner=owner,
        role="manager",
        language=language,
        now=now,
        sandbox_expires_at=None,
    )


async def _seed_event(
    db: AsyncSession,
    *,
    owner: User,
    role: SandboxRole,
    language: str,
    now: dt.datetime,
    sandbox_expires_at: dt.datetime | None,
) -> Event:
    """Both entry points. ``sandbox_expires_at=None`` builds a permanent event."""
    lang = "de" if language == "de" else "en"
    sandbox = sandbox_expires_at is not None
    today = now.date()
    rng = _DeterministicRng(seed=owner.id.int)

    event = Event(
        name=_EVENT_NAME[lang],
        description=(_EVENT_DESCRIPTION if sandbox else _DEV_EVENT_DESCRIPTION)[lang],
        start_date=today - dt.timedelta(days=_DAYS_BEFORE_TODAY),
        end_date=today + dt.timedelta(days=_DAYS_AFTER_TODAY),
        default_start_time=dt.time(hour=9),
        default_end_time=dt.time(hour=21),
        status="published",
        # Private, not public. A sandbox is excluded from Discover by an
        # explicit filter, but visibility is the second lock on that door and
        # costs nothing.
        visibility="private",
        is_featured=False,
        is_sandbox=sandbox,
        sandbox_expires_at=sandbox_expires_at,
        created_by_id=owner.id,
    )
    db.add(event)
    await db.flush()

    # The role is the whole configuration of the demo. ``member`` hides every
    # management screen behind the router's requiresEventManager guard, which
    # is exactly what the helper track wants to show; ``owner`` opens them.
    db.add(
        EventMembership(
            user_id=owner.id,
            event_id=event.id,
            role="owner" if role == "manager" else "member",
        )
    )

    teammates = _build_teammates(lang=lang, count=_TEAMMATE_COUNT, sandbox=sandbox)
    for teammate in teammates:
        db.add(teammate)
    await db.flush()

    for teammate in teammates:
        db.add(EventMembership(user_id=teammate.id, event_id=event.id, role="member"))

    tasks, shifts = await _seed_tasks_and_shifts(
        db, event=event, owner=owner, lang=lang, today=today, sandbox=sandbox
    )
    guest_bookings = await _seed_bookings(
        db,
        tasks=tasks,
        shifts=shifts,
        owner=owner,
        teammates=teammates,
        today=today,
        rng=rng,
    )
    await _seed_availabilities(db, event=event, teammates=teammates, rng=rng)

    requester: User | None = None
    if role == "manager":
        requester = await _seed_pending_decisions(
            db, event=event, owner=owner, lang=lang, now=now, sandbox=sandbox
        )

    await _seed_teams(
        db,
        event=event,
        owner=owner,
        role=role,
        teammates=teammates,
        tasks=tasks,
        lang=lang,
        now=now,
        sandbox=sandbox,
    )

    _seed_notifications(
        db,
        event=event,
        owner=owner,
        tasks=tasks,
        guest_bookings=guest_bookings,
        requester=requester,
        lang=lang,
        now=now,
    )

    await db.flush()
    return event


async def _seed_tasks_and_shifts(
    db: AsyncSession,
    *,
    event: Event,
    owner: User,
    lang: str,
    today: dt.date,
    sandbox: bool,
) -> tuple[list[Task], list[Shift]]:
    """Create each task with a real batch, so the regenerate screen works.

    Each distinct location becomes a ``Location`` row first, and every task,
    batch and shift points at it, exactly as the task forms would leave them.
    The venue plan is seeded from the same specs afterwards.
    """
    locations: dict[str, Location] = {}
    for spec in _TASK_SPECS:
        name = spec.location(lang)
        if name not in locations:
            locations[name] = Location(
                event_id=event.id,
                name=name,
                description=spec.location_desc(lang),
            )
            db.add(locations[name])
    await db.flush()

    tasks: list[Task] = []
    for spec in _TASK_SPECS:
        dates = [today + dt.timedelta(days=offset) for offset in spec.day_offsets]
        task = Task(
            name=spec.name(lang),
            description=spec.description(lang),
            start_date=min(dates),
            end_date=max(dates),
            status="published",
            created_by_id=owner.id,
            event_id=event.id,
            is_sandbox=sandbox,
            location=spec.location(lang),
            location_id=locations[spec.location(lang)].id,
            category=spec.category(lang),
            shift_duration_minutes=spec.duration_minutes,
            default_start_time=dt.time(hour=spec.start_hour),
            default_end_time=dt.time(hour=spec.end_hour),
            people_per_shift=spec.people_per_shift,
            schedule_overrides=None,
        )
        db.add(task)
        tasks.append(task)
    await db.flush()

    shifts: list[Shift] = []
    for spec, task in zip(_TASK_SPECS, tasks, strict=True):
        dates = [today + dt.timedelta(days=offset) for offset in spec.day_offsets]
        location = locations[spec.location(lang)]
        batch = ShiftBatch(
            task_id=task.id,
            label=None,
            start_date=min(dates),
            end_date=max(dates),
            location=location.name,
            location_id=location.id,
            category=spec.category(lang),
            default_start_time=dt.time(hour=spec.start_hour),
            default_end_time=dt.time(hour=spec.end_hour),
            shift_duration_minutes=spec.duration_minutes,
            people_per_shift=spec.people_per_shift,
            remainder_mode="drop",
            schedule_overrides=None,
        )
        db.add(batch)
        await db.flush()

        generated = generate_shifts(
            task_id=task.id,
            task_name=task.name,
            start_date=min(dates),
            end_date=max(dates),
            default_start_time=dt.time(hour=spec.start_hour),
            default_end_time=dt.time(hour=spec.end_hour),
            shift_duration_minutes=spec.duration_minutes,
            people_per_shift=spec.people_per_shift,
            remainder_mode="drop",
            location=location.name,
            location_id=location.id,
            category=spec.category(lang),
            specific_dates=dates,
        )
        for shift_in in generated:
            shift = Shift(
                task_id=task.id,
                batch_id=batch.id,
                title=shift_in.title,
                description=shift_in.description,
                date=shift_in.date,
                start_time=shift_in.start_time,
                end_time=shift_in.end_time,
                location=shift_in.location,
                location_id=location.id,
                category=shift_in.category,
                max_bookings=shift_in.max_bookings,
            )
            db.add(shift)
            shifts.append(shift)
    await db.flush()

    await _seed_venue_plan(db, event=event, locations=locations, lang=lang)
    return tasks, shifts


async def _seed_venue_plan(
    db: AsyncSession,
    *,
    event: Event,
    locations: dict[str, Location],
    lang: str,
) -> None:
    """The drawn plans, with every placeable location and the generic pins.

    Both plans are blank canvases drawn with shapes, exactly what an organiser
    would make in the editor, so they follow the light and dark theme. Every
    pin is placed from ``SPOTS``, the table the shapes are built from, and the
    rooms that stand for a place are linked to it through the same spots.
    """
    plans: dict[PlanKey, VenuePlan] = {}
    for order, key in enumerate(PLAN_KEYS):
        plans[key] = VenuePlan(
            event_id=event.id,
            name=_PLAN_NAMES[key][lang],
            sort_order=order,
            canvas_width=WIDTH,
            canvas_height=HEIGHT,
            # As if the drawing had been saved in one batch.
            shapes_revision=1,
        )
        db.add(plans[key])
    # No ORM relationship ties the children to the plan, so the plan rows go
    # in first rather than relying on the flush to order the inserts.
    await db.flush()

    spot_location: dict[tuple[PlanKey, str], uuid.UUID] = {}
    for spec in _TASK_SPECS:
        if spec.marker is not None:
            spot_location.setdefault(spec.marker, locations[spec.location(lang)].id)
    for key, plan in plans.items():
        for order, shape in enumerate(demo_shapes(key)):
            db.add(
                VenueShape(
                    plan_id=plan.id,
                    location_id=(
                        spot_location.get((key, shape.link_spot))
                        if shape.link_spot
                        else None
                    ),
                    kind=shape.kind,
                    style=shape.style,
                    points=[round_point(p) for p in shape.points],
                    label=label_text(shape.label_key, lang)
                    if shape.label_key
                    else None,
                    label_size=shape.label_size,
                    label_x=shape.label_at[0] if shape.label_at else None,
                    label_y=shape.label_at[1] if shape.label_at else None,
                    stroke_width=shape.stroke_width,
                    prop=shape.prop,
                    rotation=shape.rotation if shape.prop else None,
                    scale=shape.scale if shape.prop else None,
                    sort_order=order,
                )
            )
    placed: set[str] = set()
    for spec in _TASK_SPECS:
        name = spec.location(lang)
        if spec.marker is None or name in placed:
            continue
        placed.add(name)
        plan_key, spot = spec.marker
        x, y = SPOTS[plan_key][spot]
        db.add(
            VenueMarker(
                plan_id=plans[plan_key].id,
                location_id=locations[name].id,
                kind="location",
                x=x,
                y=y,
            )
        )
    for plan_key, kind, spot, labels in _GENERIC_MARKERS:
        x, y = SPOTS[plan_key][spot]
        db.add(
            VenueMarker(
                plan_id=plans[plan_key].id,
                kind=kind,
                label=labels[lang] if labels else None,
                x=x,
                y=y,
            )
        )
    await db.flush()


async def _seed_bookings(
    db: AsyncSession,
    *,
    tasks: list[Task],
    shifts: list[Shift],
    owner: User,
    teammates: list[User],
    today: dt.date,
    rng: "_DeterministicRng",
) -> list[_GuestBooking]:
    """Fill the rota unevenly, put the visitor on it, and say where they landed.

    Uneven on purpose: a board where every shift is full says nothing about
    what the app is for. Past shifts are filled harder than future ones,
    because that is what a real rota looks like and it makes the reporting
    charts show a trend rather than a flat line.

    The roster is kept per shift rather than a count, because ``_seed_notifications``
    needs to name a colleague who is genuinely on the same shift.

    One upcoming shift is exempted from both halves of that and left half
    staffed on purpose — the guided tour needs a chip it can actually book. See
    the block at the bottom of this function.
    """
    roster: dict[uuid.UUID, list[tuple[User, Booking]]] = {}

    def _book(shift: Shift, user: User) -> Booking | None:
        on_it = roster.setdefault(shift.id, [])
        if len(on_it) >= shift.max_bookings:
            return None
        booking = Booking(shift_id=shift.id, user_id=user.id, status="confirmed")
        on_it.append((user, booking))
        db.add(booking)
        return booking

    for shift in shifts:
        past = shift.date < today
        # Roughly 85% of past capacity filled, 45% of what is still to come.
        fill_chance = 85 if past else 45
        for teammate in teammates:
            if rng.percent() < fill_chance:
                _book(shift, teammate)

    def _set_headcount(shift: Shift, wanted: int) -> None:
        # Trimming expunges the pending row, as for the guest below, so its
        # INSERT never happens; topping up takes teammates in order.
        on_it = roster.setdefault(shift.id, [])
        while len(on_it) > wanted:
            db.expunge(on_it.pop()[1])
        for teammate in teammates:
            if len(on_it) >= wanted:
                break
            if all(user.id != teammate.id for user, _ in on_it):
                _book(shift, teammate)

    # Today's staffing per place is what the map colours its pins by, so it is
    # set rather than rolled: full here, half there, short somewhere else. No
    # ``rng`` draws, so nothing below reshuffles.
    fill_by_task = {
        task.id: spec.today_fill
        for spec, task in zip(_TASK_SPECS, tasks, strict=True)
        if spec.today_fill is not None
    }
    for task_id, fill in fill_by_task.items():
        todays = [s for s in shifts if s.task_id == task_id and s.date == today]
        # The day's places are filled from the morning on, so the side panel's
        # list of the day's shifts reads full, part, empty rather than the
        # same count on every line. Rounded half up, not to even.
        remaining = math.floor(fill * sum(s.max_bookings for s in todays) + 0.5)
        for shift in todays:
            wanted = min(shift.max_bookings, remaining)
            remaining -= wanted
            _set_headcount(shift, wanted)

    # The visitor's own bookings — one already behind them and two ahead, so
    # "My bookings" has both a history and something to look forward to, and
    # the dashboard counter is never zero.
    upcoming = [s for s in shifts if s.date >= today]
    past_shifts = [s for s in shifts if s.date < today]

    # …minus one shift, held back from everything below because the guided tour
    # has to have something to press.
    #
    # The tour's book step opens the first *bookable* chip on the board, where
    # bookable means: still to come, a place free on it, and not one the visitor
    # already holds. Both halves of this function used to destroy precisely that
    # chip. ``_pick_spread`` starts at index 0 and ``shifts`` is built task by
    # task in ``_TASK_SPECS`` order, so ``upcoming[0]`` *is* the first upcoming
    # shift of the first task — the guest was booked onto it every single time,
    # and where they were not, the teammate loop above had usually filled it.
    # The step that says "press Book" then pointed at a button
    # ``ShiftDetailDialog`` had not rendered.
    #
    # A shift a whole day out is preferred to one starting today, because a chip
    # whose start time has already gone by reads as a demo built last week.
    first_task_id = shifts[0].task_id if shifts else None
    on_first_task = [s for s in upcoming if s.task_id == first_task_id]
    tour_shift = next(
        (s for s in on_first_task if s.date > today),
        on_first_task[0] if on_first_task else None,
    )

    # Today's shifts with a set fill stay as set above: the guest landing on
    # the one short place would turn its pin from short to half staffed. A
    # task only a team may book is left alone too — the helper is not in that
    # team, and the Teams tour shows them the lock rather than a booking they
    # could not have made.
    locked_tasks = {
        task.id
        for spec, task in zip(_TASK_SPECS, tasks, strict=True)
        if spec.team is not None
    }
    guest_choices = [
        s
        for s in upcoming
        if s is not tour_shift
        and s.task_id not in locked_tasks
        and not (s.date == today and s.task_id in fill_by_task)
    ]
    held: list[_GuestBooking] = []
    past_choices = [s for s in past_shifts if s.task_id not in locked_tasks]
    for shift in _pick_spread(guest_choices, 2) + _pick_spread(past_choices, 1):
        # Make room for the guest on a shift the loop above already filled — by
        # dropping a teammate rather than by lowering a counter. Nothing has
        # been flushed yet, so expunging the pending row means its INSERT never
        # happens; counting the guest as an extra head instead would put a
        # three-of-two fill badge on the staffing board.
        on_it = roster.setdefault(shift.id, [])
        while len(on_it) >= shift.max_bookings:
            db.expunge(on_it.pop()[1])
        booking = _book(shift, owner)
        if booking is not None:
            held.append(
                _GuestBooking(
                    booking=booking,
                    shift=shift,
                    co_workers=tuple(user for user, _ in on_it if user.id != owner.id),
                )
            )

    # And now leave that one shift genuinely half staffed: a place free, and —
    # wherever the shift wants more than one pair of hands — a name already on
    # it. The free place is what makes *Book shift* render at all; the name is
    # what makes the step before it ("you would be the third of four rather than
    # the only one") describe something the visitor can see on the roster.
    #
    # Trimming uses the same expunge trick as the loop above, for the same
    # reason. Topping up, when the teammate loop happened to leave the shift
    # empty, is deterministic rather than another ``rng`` draw — this runs after
    # every generator call, so nothing upstream reshuffles.
    if tour_shift is not None:
        on_it = roster.setdefault(tour_shift.id, [])
        while len(on_it) >= tour_shift.max_bookings:
            db.expunge(on_it.pop()[1])
        if not on_it and tour_shift.max_bookings > 1 and teammates:
            _book(tour_shift, teammates[0])

    return held


async def _seed_availabilities(
    db: AsyncSession,
    *,
    event: Event,
    teammates: list[User],
    rng: "_DeterministicRng",
) -> None:
    """Give the staffing heatmap a spread of greens rather than one flat block."""
    event_days = [
        event.start_date + dt.timedelta(days=offset)
        for offset in range((event.end_date - event.start_date).days + 1)
    ]
    windows = ((9, 17), (10, 18), (8, 16), (14, 22))

    for index, teammate in enumerate(teammates):
        kind = index % 3
        dates: list[dt.date | UserAvailabilityDateInput] = []
        start_time: dt.time | None = None
        end_time: dt.time | None = None

        if kind == 0:
            availability_type = "fully_available"
        elif kind == 1:
            availability_type = "time_range"
            window = windows[index % len(windows)]
            start_time = dt.time(hour=window[0])
            end_time = dt.time(hour=window[1])
        else:
            availability_type = "specific_dates"
            for day in event_days:
                if rng.percent() < 60:
                    continue
                if rng.percent() < 50:
                    dates.append(day)
                else:
                    first = 8 + (rng.percent() % 5)
                    dates.append(
                        UserAvailabilityDateInput(
                            date=day,
                            start_time=dt.time(hour=first),
                            end_time=dt.time(hour=min(21, first + 6)),
                        )
                    )
            if not dates:
                dates.append(event_days[0])

        await crud_user_availability.upsert_for_user(
            db,
            user_id=teammate.id,
            event_id=event.id,
            obj_in=UserAvailabilityCreate(
                availability_type=availability_type,  # type: ignore[arg-type]
                default_start_time=start_time,
                default_end_time=end_time,
                dates=dates,
            ),
        )


async def _seed_pending_decisions(
    db: AsyncSession,
    *,
    event: Event,
    owner: User,
    lang: str,
    now: dt.datetime,
    sandbox: bool,
) -> User:
    """One invitation and one join request, both still waiting. Returns the applicant.

    Manager-only. These are the two decisions running an event actually
    consists of, and both screens read as broken when empty. The applicant is
    returned because the organiser's inbox carries a notification about them,
    and the two have to name the same person.

    The invitation address is on ``example.invalid`` — reserved by RFC 2606 and
    guaranteed never to resolve. Nothing in the demo may send mail, and the
    route-level guard is the thing that enforces that; this is the second lock,
    for the case where someone adds a new send path and forgets.
    """
    db.add(
        EventInvitation(
            event_id=event.id,
            email="sam.rivera@example.invalid",
            role="member",
            token=secrets.token_urlsafe(32),
            invited_by_id=owner.id,
            expires_at=now + dt.timedelta(days=14),
        )
    )
    requester = _stand_in(
        "Ellis Vaughan" if lang == "en" else "Elli Vaughan",
        lang=lang,
        sandbox=sandbox,
    )
    db.add(requester)
    # Flushed before the two rows that point at it. Neither EventJoinRequest nor
    # EventMembership declares an ORM ``Relationship`` to User — both carry a
    # bare ``sa.ForeignKey`` — so SQLAlchemy's unit of work has no dependency
    # edge to order the INSERTs by and falls back to the mapper sort key, which
    # is the qualified class name. ``event_join_request`` sorts before ``user``,
    # so without this the join request is inserted first, every time, and the
    # request dies on a foreign-key violation. Deterministic, not a race.
    await db.flush()
    db.add(
        EventJoinRequest(
            user_id=requester.id,
            event_id=event.id,
            status="pending",
            message=(
                "I helped at the café last year and would like to again."
                if lang == "en"
                else "Ich habe letztes Jahr im Café geholfen und würde gern wieder."
            ),
        )
    )
    # The requester is a guest of this event too, so the purge finds and
    # removes them — membership is how ``cleanup`` enumerates the guests.
    db.add(EventMembership(user_id=requester.id, event_id=event.id, role="member"))
    return requester


@dataclass(frozen=True, slots=True)
class _RequirementSpec:
    label_en: str
    label_de: str
    description_en: str | None
    description_de: str | None
    ask_issue_date: bool
    valid_for_years: int | None
    accepts_document: bool


_POLICE_CERTIFICATE = _RequirementSpec(
    label_en="Extended police certificate",
    label_de="Erweitertes Führungszeugnis",
    description_en=(
        "§72a SGB VIII. Don't keep a copy: WirkSam only saves that you saw it, "
        "when, and the issue date."
    ),
    description_de=(
        "§72a SGB VIII. Bitte keine Kopie aufbewahren: WirkSam speichert nur, "
        "dass du es gesehen hast, wann, und das Ausstellungsdatum."
    ),
    ask_issue_date=True,
    valid_for_years=5,
    accepts_document=False,
)
_FIRST_AID_COURSE = _RequirementSpec(
    label_en="First-aid course",
    label_de="Erste-Hilfe-Kurs",
    description_en="At least 9 units, no older than two years.",
    description_de="Mindestens 9 Unterrichtseinheiten, nicht älter als zwei Jahre.",
    ask_issue_date=True,
    valid_for_years=2,
    accepts_document=True,
)
_DRIVING_LICENCE_B = _RequirementSpec(
    label_en="Driving licence class B",
    label_de="Führerschein Klasse B",
    description_en=None,
    description_de=None,
    ask_issue_date=False,
    valid_for_years=None,
    accepts_document=False,
)


@dataclass(frozen=True, slots=True)
class _TeamSpec:
    """One seeded team. ``lead`` and ``members`` index ``_TEAMMATE_NAMES``."""

    key: str
    name_en: str
    name_de: str
    description_en: str
    description_de: str
    requires_approval: bool
    requirement: _RequirementSpec | None
    lead: int | None
    members: tuple[int, ...]
    #: A member whose check ran out last year ("needs a new check").
    expired: int | None = None
    #: The visitor is in it, so the helper track sees "You're in" somewhere.
    with_guest: bool = False
    #: The visitor leads it — manager variant only, so the organiser decides
    #: its requests as a team lead as well as an event owner.
    owner_leads: bool = False


# Five teams, one of each kind the Teams page shows: an open one the visitor is
# already in; the cash desk, which needs approval and locks the wristband check
# (the manager leads it); the shuttle drivers, behind a driving licence that
# takes neither a date nor a file; childcare, behind an extended police
# certificate that locks the kids' games; and first aid, whose requirement
# takes a file.
_TEAMS: tuple[_TeamSpec, ...] = (
    _TeamSpec(
        key="setup",
        name_en="Setup crew",
        name_de="Aufbau",
        description_en="Set up tents, benches and the stage on the first morning.",
        description_de="Zelte, Bänke und die Bühne am ersten Morgen aufbauen.",
        requires_approval=False,
        requirement=None,
        lead=1,
        members=(4,),
        with_guest=True,
    ),
    _TeamSpec(
        key="cash_desk",
        name_en="Cash desk",
        name_de="Kasse",
        description_en=(
            "Cash desk at the meadow gate. You handle money, so we need to know you."
        ),
        description_de=(
            "Kasse am Wiesentor. Du hast mit Geld zu tun, deshalb müssen wir dich "
            "kennen."
        ),
        requires_approval=True,
        requirement=None,
        lead=4,
        members=(0,),
        owner_leads=True,
    ),
    _TeamSpec(
        key="shuttle",
        name_en="Shuttle drivers",
        name_de="Fahrdienst",
        description_en="Drive guests between the station and the meadow.",
        description_de="Gäste zwischen Bahnhof und Festwiese hin- und herfahren.",
        requires_approval=True,
        requirement=_DRIVING_LICENCE_B,
        lead=3,
        members=(1,),
    ),
    _TeamSpec(
        key="childcare",
        name_en="Childcare",
        name_de="Kinderbetreuung",
        description_en=(
            "Look after children aged 3 to 10 at the kids' corner. Needs an "
            "extended police certificate."
        ),
        description_de=(
            "Kinder von 3 bis 10 in der Kinderecke betreuen. Braucht ein "
            "erweitertes Führungszeugnis."
        ),
        requires_approval=True,
        requirement=_POLICE_CERTIFICATE,
        lead=0,
        members=(),
    ),
    _TeamSpec(
        key="first_aid",
        name_en="First aid",
        name_de="Sanitätsdienst",
        description_en=(
            "First aid at the tent on the meadow. You need a first-aid course "
            "from the last two years."
        ),
        description_de=(
            "Erste Hilfe im Zelt auf der Festwiese. Du brauchst einen "
            "Erste-Hilfe-Kurs aus den letzten zwei Jahren."
        ),
        requires_approval=True,
        requirement=_FIRST_AID_COURSE,
        lead=2,
        members=(3,),
        expired=3,
    ),
)

# The requests a manager reviews: (team key, name, note by language or
# ``None``, attaches the sample certificate). A name that asks twice is one
# person with two requests, as Vera is.
_TEAM_REQUESTS: tuple[tuple[str, str, dict[str, str] | None, bool], ...] = (
    (
        "cash_desk",
        "Vera Volunteer",
        {
            "en": "I did the cash desk at last year's festival.",
            "de": "Ich habe letztes Jahr beim Fest an der Kasse gestanden.",
        },
        False,
    ),
    ("cash_desk", "Jordan Schmidt", None, False),
    (
        "shuttle",
        "Vera Volunteer",
        {
            "en": "I can take the minibus on Saturday morning.",
            "de": "Ich kann am Samstagmorgen den Kleinbus fahren.",
        },
        False,
    ),
    (
        "childcare",
        "Carla Meier",
        {
            "en": (
                "I'm a primary school teacher and ran the kids' corner at the "
                "parish fair two years in a row. I can bring my police "
                "certificate to the briefing on Thursday."
            ),
            "de": (
                "Ich bin Grundschullehrerin und habe zwei Jahre lang die "
                "Kinderecke beim Gemeindefest gemacht. Mein Führungszeugnis "
                "bringe ich am Donnerstag zur Einweisung mit."
            ),
        },
        False,
    ),
    (
        "first_aid",
        "Sven Becker",
        {
            "en": "I did my first-aid course this spring, the certificate is attached.",
            "de": (
                "Meinen Erste-Hilfe-Kurs habe ich im Frühjahr gemacht, die "
                "Bescheinigung hängt an."
            ),
        },
        True,
    ),
)


async def _seed_teams(
    db: AsyncSession,
    *,
    event: Event,
    owner: User,
    role: SandboxRole,
    teammates: list[User],
    tasks: list[Task],
    lang: str,
    now: dt.datetime,
    sandbox: bool,
) -> None:
    """Five teams, two locked tasks, and — for a manager — requests to review.

    The helper sees tasks they cannot book and teams they can ask to join in
    place, and has nothing to decide. The manager leads the cash desk and sees
    the review flow: Vera and Jordan asking for the cash desk, Vera for the
    shuttle drivers, Carla's request behind a police certificate (no file, by
    design) and Sven's with a sample first-aid certificate attached, drawn by
    ``logic.sample_document`` because a sandbox may not upload one. Everyone
    the rota put on a locked task is an approved member of its team, so no one
    holds a shift they could not have booked.

    Rows are flushed stage by stage: none of these tables declares an ORM
    relationship, so the unit of work cannot order their INSERTs (see
    ``_seed_pending_decisions``).
    """
    today = now.date()
    joined = now - dt.timedelta(days=21)

    teams: dict[str, EventTeam] = {}
    for spec in _TEAMS:
        teams[spec.key] = EventTeam(
            event_id=event.id,
            name=spec.name_de if lang == "de" else spec.name_en,
            description=spec.description_de if lang == "de" else spec.description_en,
            requires_approval=spec.requires_approval,
        )
        db.add(teams[spec.key])
    await db.flush()

    requirements: dict[str, EventTeamRequirement] = {}
    for spec in _TEAMS:
        req = spec.requirement
        if req is None:
            continue
        requirements[spec.key] = EventTeamRequirement(
            team_id=teams[spec.key].id,
            label=req.label_de if lang == "de" else req.label_en,
            description=req.description_de if lang == "de" else req.description_en,
            ask_issue_date=req.ask_issue_date,
            valid_for_years=req.valid_for_years,
            accepts_document=req.accepts_document,
            position=0,
        )
        db.add(requirements[spec.key])
    # Also writes the bookings, which the query below reads back.
    await db.flush()

    # Whoever the rota put on a locked task joins its team.
    on_locked: dict[str, set[uuid.UUID]] = {}
    for spec, task in zip(_TASK_SPECS, tasks, strict=True):
        if spec.team is None:
            continue
        rows = await db.execute(
            select(col(Booking.user_id))
            .join(Shift, col(Shift.id) == col(Booking.shift_id))
            .where(col(Shift.task_id) == task.id)
        )
        on_locked.setdefault(spec.team, set()).update(rows.scalars())

    approved: list[tuple[_TeamSpec, EventTeamMember, User]] = []
    by_id = {teammate.id: teammate for teammate in teammates}
    by_id[owner.id] = owner
    for spec in _TEAMS:
        lead = teammates[spec.lead] if spec.lead is not None else None
        decider = lead or owner
        people: list[tuple[User, str]] = []
        if spec.owner_leads and role == "manager":
            people.append((owner, "lead"))
            decider = owner
        if lead is not None:
            people.append((lead, "lead"))
        people += [(teammates[i], "member") for i in spec.members]
        if spec.with_guest:
            people.append((owner, "member"))
        for user_id in sorted(on_locked.get(spec.key, set()), key=str):
            if user_id in by_id and all(u.id != user_id for u, _ in people):
                people.append((by_id[user_id], "member"))
        for user, team_role in people:
            member = EventTeamMember(
                team_id=teams[spec.key].id,
                user_id=user.id,
                status="approved",
                role=team_role,
                decided_by_id=decider.id,
                decided_by_name=decider.name,
                decided_at=joined,
                created_at=joined,
                updated_at=joined,
            )
            db.add(member)
            approved.append((spec, member, decider))

    pending: list[tuple[str, EventTeamMember, str, bool]] = []
    if role == "manager":
        # One account per name: Vera asks two teams, and two requests from
        # two different Veras would read as a duplicate rather than as keen.
        requesters: dict[str, User] = {}
        for _, name, _, _ in _TEAM_REQUESTS:
            if name not in requesters:
                requesters[name] = _stand_in(name, lang=lang, sandbox=sandbox)
        db.add_all(requesters.values())
        await db.flush()
        for requester in requesters.values():
            # A guest of this demo, so the purge finds them by membership.
            db.add(
                EventMembership(user_id=requester.id, event_id=event.id, role="member")
            )
        asked = now - dt.timedelta(days=2)
        for team_key, name, note, with_file in _TEAM_REQUESTS:
            member = EventTeamMember(
                team_id=teams[team_key].id,
                user_id=requesters[name].id,
                status="pending",
                message=note[lang] if note is not None else None,
                created_at=asked,
                updated_at=asked,
            )
            db.add(member)
            pending.append((team_key, member, name, with_file))
    await db.flush()

    # A check for every approved member of a team with a requirement; the
    # ``expired`` one's ran out last year, which flags "needs a new check".
    for position, (spec, member, decider) in enumerate(approved):
        req = requirements.get(spec.key)
        if req is None:
            continue
        if spec.expired is not None and member.user_id == teammates[spec.expired].id:
            issued = add_years(today, -3)
        else:
            issued = today - dt.timedelta(days=50 + 41 * (position % 8))
        db.add(
            EventTeamCheck(
                member_id=member.id,
                requirement_id=req.id,
                checked_by_id=decider.id,
                checked_by_name=decider.name,
                checked_at=joined,
                issued_on=issued if req.ask_issue_date else None,
                expires_on=(
                    add_years(issued, req.valid_for_years)
                    if req.valid_for_years is not None
                    else None
                ),
            )
        )

    for team_key, member, name, with_file in pending:
        req = requirements.get(team_key)
        if not with_file or req is None or not req.accepts_document:
            continue
        data = render_first_aid_sample(
            holder=name, course_date=today - dt.timedelta(days=60)
        )
        db.add(
            EventTeamDocument(
                member_id=member.id,
                requirement_id=req.id,
                filename=SAMPLE_FILENAME,
                content_type=SAMPLE_CONTENT_TYPE,
                size=len(data),
                storage_key=await crud_team.store_document_file(
                    db, data=data, content_type=SAMPLE_CONTENT_TYPE
                ),
            )
        )

    for spec, task in zip(_TASK_SPECS, tasks, strict=True):
        if spec.team is not None:
            task.team_id = teams[spec.team].id
            db.add(task)
    await db.flush()


def _seed_notifications(
    db: AsyncSession,
    *,
    event: Event,
    owner: User,
    tasks: list[Task],
    guest_bookings: list[_GuestBooking],
    requester: User | None,
    lang: str,
    now: dt.datetime,
) -> None:
    """Write the visitor an inbox — rows only, no dispatch.

    Deliberately not through ``NotificationService``. That service drops a
    sandbox recipient *before* it writes anything, so that a demo can never
    cause a send attempt on any channel and never leaves rows for the purge to
    chase. The consequence is that nothing the visitor does during the tour
    produces a notification: without this function the bell has no badge and
    the inbox has four empty tabs behind it, on a screen the app otherwise
    makes a point of.

    So the rows are written here directly, and ``channels_sent`` stays empty on
    every one of them, because nothing was sent and a demo may not claim
    otherwise. What the shape has to satisfy:

    * every classification the notifications screen offers a tab for —
      reminder, change, match, announcement — has at least one entry behind it;
    * some are unread, so the bell carries a badge on arrival, and some are
      read, so the list is not a wall of bold;
    * ``created_at`` spans minutes, hours and days, which is the whole range
      the relative timestamps can render before they fall back to a date;
    * every ``data`` payload carries the keys ``logic/notifications/triggers.py``
      writes for that type and points at a row seeded into *this* demo, so
      opening an entry lands on the task or the booking it is about.

    Nothing here needs the rows to be flushed: ``Base.id`` is a client-side
    ``uuid4``, so a booking can be pointed at before it exists.
    """
    entries: list[Notification] = []
    tasks_by_id = {task.id: task for task in tasks}

    def _add(
        code: str,
        *,
        created_at: dt.datetime,
        is_read: bool,
        data: dict[str, str | int | None],
        **fields: str,
    ) -> None:
        title, body = get_message(code, lang, **fields)
        entries.append(
            Notification(
                recipient_id=owner.id,
                notification_type_code=code,
                title=title,
                body=body,
                data=data,
                is_read=is_read,
                # Read half an hour after it arrived, or now for anything that
                # arrived inside that window — never a read_at in the future.
                read_at=min(created_at + dt.timedelta(minutes=30), now)
                if is_read
                else None,
                channels_sent=[],
                channels_failed=[],
                created_at=created_at,
                updated_at=created_at,
            )
        )

    # ── match: a task went up, which is how a helper hears about work ──
    if tasks:
        published = tasks[-1]
        _add(
            "task.published",
            created_at=now - dt.timedelta(days=3, hours=2),
            is_read=True,
            data={"task_id": str(published.id)},
            task_name=published.name,
        )

    # ── announcement: the organiser's half of the inbox ──
    if requester is not None:
        _add(
            "event.join_requested",
            created_at=now - dt.timedelta(minutes=50),
            is_read=False,
            data={"event_id": str(event.id), "user_id": str(requester.id)},
            name=requester.name or "",
            event_name=event.name,
        )

    if not guest_bookings:
        db.add_all(entries)
        return

    ahead = sorted(
        (held for held in guest_bookings if held.starts_at() > now),
        key=lambda held: held.starts_at(),
    )

    def _slot_fields(held: _GuestBooking) -> dict[str, str]:
        shift = held.shift
        task = tasks_by_id.get(shift.task_id)
        return {
            "slot_title": shift.title,
            "task_name": task.name if task else "",
            "date": shift.date.strftime("%d.%m.%Y"),
            "start_time": shift.start_time.strftime("%H:%M")
            if shift.start_time
            else "",
            "end_time": shift.end_time.strftime("%H:%M") if shift.end_time else "",
            "location": shift.location or "",
        }

    def _slot_data(held: _GuestBooking) -> dict[str, str | int | None]:
        return {
            "booking_id": str(held.booking.id),
            "slot_id": str(held.shift.id),
            "task_id": str(held.shift.task_id),
        }

    # Which booking each entry is about is not free choice. Several
    # notifications about one shift read as a single incident rather than as an
    # inbox, so each entry takes the first shift in its own order of preference
    # that no earlier entry has claimed, and doubles up only when the visitor
    # holds too few to go round.
    spoken_for: set[uuid.UUID] = set()

    def _claim(*preferences: list[_GuestBooking]) -> _GuestBooking:
        for bucket in preferences:
            for held in bucket:
                if held.shift.id not in spoken_for:
                    spoken_for.add(held.shift.id)
                    return held
        fallback = next(bucket[0] for bucket in preferences if bucket)
        spoken_for.add(fallback.shift.id)
        return fallback

    # ── change: something moved under them, which is the whole point of an
    # inbox — and unread, because it is the one entry worth opening.
    #
    # Claimed first, and skipped outright when the visitor holds nothing that
    # has not already run: a shift cannot be rescheduled after the fact, and
    # the "changes" tab has the confirmation below in it either way. Taken from
    # the far end of what is ahead, so the nearer shift stays free for that
    # confirmation. ──
    if ahead:
        moved = _claim(list(reversed(ahead)))
        _add(
            "shift.time_changed",
            created_at=now - dt.timedelta(hours=4),
            is_read=False,
            data={
                "slot_id": str(moved.shift.id),
                "task_id": str(moved.shift.task_id),
            },
            slot_title=moved.shift.title,
        )

    # ── change: a booking they hold, confirmed back when they took it ──
    confirmed = _claim(ahead, guest_bookings)
    _add(
        "booking.confirmed",
        created_at=now - dt.timedelta(days=2, hours=3),
        is_read=True,
        data=_slot_data(confirmed),
        **_slot_fields(confirmed),
    )

    # ── announcement: someone joined them on a shift. Named from the roster,
    # so the colleague really is on it — the staffing board is one click away
    # and it would show them missing. ──
    with_company = [held for held in [*ahead, *guest_bookings] if held.co_workers]
    if with_company:
        shared = _claim(with_company)
        _add(
            "booking.shift_cobooked",
            created_at=now - dt.timedelta(hours=9),
            is_read=False,
            data={
                "slot_id": str(shared.shift.id),
                "task_id": str(shared.shift.task_id),
            },
            name=shared.co_workers[0].name or "",
            slot_title=shared.shift.title,
        )

    # ── reminder: sent the configured day ahead of a shift they hold.
    #
    # Which shift is not a free choice. The body says "in 1 day", so the row
    # has to be stamped a day before that shift starts, and a row stamped in
    # the future renders as "just now" and reads as broken. Hence: of every
    # shift the visitor holds, the one whose send moment already passed and
    # passed most recently — the shift starting today wins when there is one,
    # the shift they already worked when there is not. ──
    offset = dt.timedelta(minutes=_REMINDER_OFFSET_MINUTES)
    due = [
        (held.starts_at() - offset, held)
        for held in guest_bookings
        if held.starts_at() - offset <= now - dt.timedelta(minutes=5)
    ]
    if due:
        sent_at, reminded = max(due, key=lambda pair: pair[0])
        fields = _slot_fields(reminded)
        fields.pop("task_name")  # the reminder body names the shift, not the task
        _add(
            "booking.reminder",
            created_at=sent_at,
            is_read=False,
            data=_slot_data(reminded),
            time_until=format_time_until(_REMINDER_OFFSET_MINUTES, lang),
            **fields,
        )

    db.add_all(entries)


def _build_teammates(*, lang: str, count: int, sandbox: bool) -> list[User]:
    """Fake colleagues."""
    return [
        _stand_in(name, lang=lang, sandbox=sandbox)
        for name, _ in _TEAMMATE_NAMES[:count]
    ]


def _stand_in(name: str, *, lang: str, sandbox: bool) -> User:
    """One made-up person: a teammate, the join requester or a team requester.

    ``email`` is None on every one of them, which is not laziness — it is what
    makes them unmailable by construction. ``send_verify_email`` and
    ``request_password_reset`` both short-circuit on a missing address, so even
    a future code path that forgets the subject-prefix check cannot reach them.
    The prefix is ``sandbox|`` in a sandbox and ``demo|`` in the dev event;
    both are undeliverable, only the first also marks a row for the purge.
    """
    prefix = _SANDBOX_SUBJECT_PREFIX if sandbox else _DEV_SUBJECT_PREFIX
    return User(
        subject=f"{prefix}{uuid.uuid4().hex}",
        email=None,
        name=name,
        is_sandbox=sandbox,
        is_active=True,
        email_verified=False,
        preferred_language=lang,
        roles=[],
    )


def _pick_spread(items: list[Shift], wanted: int) -> list[Shift]:
    """Take up to ``wanted`` items spread across the list rather than clumped."""
    if not items or wanted <= 0:
        return []
    if len(items) <= wanted:
        return list(items)
    step = len(items) // wanted
    return [items[i * step] for i in range(wanted)]


class _DeterministicRng:
    """A tiny reproducible generator, seeded from the guest's id.

    Not ``random.Random``: two visitors clicking the button in the same second
    should get differently shaped rotas, and the same visitor reloading should
    not see the rota reshuffle. Seeding from the account id gives both, and it
    makes a failing seed reproducible from the row alone.
    """

    __slots__ = ("_state",)

    def __init__(self, *, seed: int) -> None:
        self._state = seed & 0xFFFFFFFF or 0x9E3779B9

    def percent(self) -> int:
        """Next value in [0, 100)."""
        # xorshift32 — enough randomness for deciding who takes which shift.
        x = self._state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        self._state = x
        return x % 100
