"""Shared lists ("Geteilte Listen"): a public link that lets people without an
account sign up for shifts of one event.

A list bundles tasks (``shared_list_tasks``) minus the shifts its organisers left
out (``shared_list_excluded_shifts``); which shifts it offers right now is worked
out in ``app/logic/shared_lists/offer.py``, never stored. Everyone who signs up
through a list is a password-less guest ``users`` row (``is_list_guest``) with one
``shared_list_guests`` row holding the contact address, so capacity, rosters,
reminders and reporting work on guest bookings unchanged.

``guest_activity_log`` and ``guest_mail_suppressions`` have no foreign key at all:
the daily ceilings count the log, and erasing a guest, rotating a list or deleting
the event must not reset them. Neither holds an address in clear text, only a
keyed hash.

Two more references have no foreign key on purpose. ``shared_lists.created_by_id``:
a CASCADE would delete the list with its creator's account, and SET NULL next to
``event_id`` is the trap in ``app/models/CLAUDE.md``. ``shared_list_guests.
shared_list_id``, the list a sign-up chain started on, like ``bookings.
shared_list_id``: the guest row goes with the event just as the list does, so a
key would only add another cascade path.

No ORM relationship from ``Event``, ``Task`` or ``Shift``: deleting those goes
through the ORM, and a relationship without ``passive_deletes`` would load these
rows first. Every CASCADE lives in the database.
"""

import datetime as dt
import uuid
from typing import Literal

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import Base

#: The stored status. "Expired" is derived on the event's clock, never stored
#: (``logic/shared_lists/offer.effective_status``), so moving shifts or changing
#: the event's zone cannot leave it stale. ``ended`` is final.
ListStatus = Literal["live", "paused", "ended"]
#: When a list closes: once its last shift has started, after a day, or never.
EndsMode = Literal["last_shift", "date", "manual"]
#: Whether the public form asks for an email address or a phone number.
AskMode = Literal["required", "optional", "off"]
#: Whether the public page shows the first names of guests who agreed to it.
ShowNames = Literal["none", "first"]
#: The mails a guest gets, by the ``kind`` of the ``guest_activity_log`` rows
#: they count as. The only other kind is ``signup``.
GuestMailKind = Literal["confirmation", "reminder", "cancelled", "moved", "removed"]


class SharedList(Base, table=True):
    """One public sign-up link for shifts of one event.

    ``code`` is the link: twelve random characters (``crud.shared_list.
    generate_code``), stored in plain text like ``event_invitations.token``,
    because organisers copy the link again later. Rotating it replaces the code
    on this row, and the old link stops working.
    """

    __tablename__ = "shared_lists"  # type: ignore[assignment]
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('live', 'paused', 'ended')", name="ck_shared_lists_status"
        ),
        sa.CheckConstraint(
            "ends_mode IN ('last_shift', 'date', 'manual')",
            name="ck_shared_lists_ends_mode",
        ),
        sa.CheckConstraint(
            "(ends_mode = 'date') = (ends_on IS NOT NULL)",
            name="ck_shared_lists_ends_on",
        ),
        sa.CheckConstraint(
            "ask_email IN ('required', 'optional', 'off')",
            name="ck_shared_lists_ask_email",
        ),
        sa.CheckConstraint(
            "ask_phone IN ('required', 'optional', 'off')",
            name="ck_shared_lists_ask_phone",
        ),
        sa.CheckConstraint(
            "show_names IN ('none', 'first')", name="ck_shared_lists_show_names"
        ),
        sa.CheckConstraint(
            "max_per_person IS NULL OR max_per_person BETWEEN 1 AND 50",
            name="ck_shared_lists_max_per_person",
        ),
        # Also serves every lookup by event alone.
        sa.Index("ix_shared_lists_event_id_status", "event_id", "status"),
    )

    event_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid, sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False
        ),
    )
    code: str = Field(
        sa_column=sa.Column(sa.String(16), nullable=False, unique=True, index=True),
        description="The public link /l/<code>",
    )
    title: str = Field(sa_column=sa.Column(sa.String(120), nullable=False))
    intro: str | None = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))
    share_note: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(120), nullable=True),
        description="Where the organisers share the link; never shown publicly",
    )
    status: str = Field(
        default="live",
        sa_column=sa.Column(sa.String(16), nullable=False, server_default="live"),
        description="live | paused | ended; 'expired' is derived, never stored",
    )
    paused_at: dt.datetime | None = Field(
        default=None, sa_column=sa.Column(sa.DateTime, nullable=True)
    )
    ended_at: dt.datetime | None = Field(
        default=None, sa_column=sa.Column(sa.DateTime, nullable=True)
    )
    rotated_at: dt.datetime | None = Field(
        default=None, sa_column=sa.Column(sa.DateTime, nullable=True)
    )
    ends_mode: str = Field(
        default="last_shift",
        sa_column=sa.Column(sa.String(16), nullable=False, server_default="last_shift"),
    )
    ends_on: dt.date | None = Field(
        default=None,
        sa_column=sa.Column(sa.Date, nullable=True),
        description="ends_mode 'date': open through this day, on the event's clock",
    )
    ask_email: str = Field(
        default="required",
        sa_column=sa.Column(sa.String(16), nullable=False, server_default="required"),
    )
    ask_phone: str = Field(
        default="off",
        sa_column=sa.Column(sa.String(16), nullable=False, server_default="off"),
    )
    show_names: str = Field(
        default="none",
        sa_column=sa.Column(sa.String(16), nullable=False, server_default="none"),
        description="For new sign-ups; each guest keeps what they were told",
    )
    max_per_person: int | None = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, nullable=True),
        description="Shifts one person may take through this list; NULL = unlimited",
    )
    view_count: int = Field(
        default=0,
        sa_column=sa.Column(sa.Integer, nullable=False, server_default="0"),
        description="Approximate: every open of the public page while live",
    )
    # No foreign key: see the module docstring. The name stays readable.
    created_by_id: uuid.UUID | None = Field(
        default=None, sa_column=sa.Column(sa.Uuid, nullable=True)
    )
    created_by_name: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )


class SharedListTask(Base, table=True):
    """A task on a list. Its shifts are offered unless excluded."""

    __tablename__ = "shared_list_tasks"  # type: ignore[assignment]
    # The unique index also serves the lookups by list.
    __table_args__ = (
        sa.UniqueConstraint("shared_list_id", "task_id", name="uq_shared_list_task"),
    )

    shared_list_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("shared_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    task_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    position: int = Field(
        default=0,
        sa_column=sa.Column(sa.Integer, nullable=False, server_default="0"),
        description="Order of the tasks in the share message",
    )


class SharedListExcludedShift(Base, table=True):
    """A shift of a listed task that the list leaves out.

    Exclusions rather than a list of included shifts, so a shift added to a
    listed task later is offered without anyone editing the list.
    """

    __tablename__ = "shared_list_excluded_shifts"  # type: ignore[assignment]
    __table_args__ = (
        sa.UniqueConstraint(
            "shared_list_id", "shift_id", name="uq_shared_list_excluded_shift"
        ),
    )

    shared_list_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("shared_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    shift_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("shifts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )


class SharedListGuest(Base, table=True):
    """The contact side of one guest user: a sign-up chain, or a guest account.

    A chain is everything signed up from one visit to one list. Its identity is
    the guest user, never a typed email address: anyone can type anyone's
    address. The address lives here and never in ``users.email``, which keeps
    guests out of login, password reset and every lookup by address.

    An account is a chain whose address was confirmed through the link in a
    mail to it (``confirmed_at``): at most one per event and address. Later
    chains of the same address are merged into it when they are confirmed
    (``logic/shared_lists/guest_account.py``). An account is only ever reached
    through mail tokens.

    Deleting the event removes this row, and with it the address and the manage
    link, at once. The guest user and its bookings stay, since tasks outlive
    their event, until the retention sweep finds them over.
    """

    __tablename__ = "shared_list_guests"  # type: ignore[assignment]
    # Case-insensitive lookups by address (deduplication per shift, the
    # per-person limit). Not unique: the same address may start several chains.
    # Declared here, not only in the migration, as ix_users_email_lower is.
    __table_args__ = (
        sa.Index(
            "ix_shared_list_guests_email_lower",
            sa.text("lower(email)"),
            postgresql_where=sa.text("email IS NOT NULL"),
        ),
        # One account per event and address. Erasing nulls the address, and
        # NULLs are distinct, so an erased account frees the slot.
        sa.Index(
            "uq_shared_list_guests_account",
            "event_id",
            sa.text("lower(email)"),
            unique=True,
            postgresql_where=sa.text("confirmed_at IS NOT NULL"),
        ),
    )

    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
    )
    event_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        description=(
            "The list's event at the first sign-up. Not what retention goes by: "
            "a moved task takes the guest's bookings to another event."
        ),
    )
    # No foreign key: see the module docstring.
    shared_list_id: uuid.UUID = Field(
        sa_column=sa.Column(sa.Uuid, nullable=False, index=True),
        description="The list this chain started on; a chain never leaves it",
    )
    email: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(254), nullable=True),
        description="Normalised (logic/shared_lists/normalize.py); never in users.email",
    )
    manage_nonce: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(32), nullable=True),
        description=(
            "Input to the HMAC behind the guest's manage link, which is never "
            "stored. NULL revokes every manage link."
        ),
    )
    last_signup_at: dt.datetime = Field(
        sa_column=sa.Column(sa.DateTime, nullable=False)
    )
    erased_at: dt.datetime | None = Field(
        default=None, sa_column=sa.Column(sa.DateTime, nullable=True)
    )
    confirmed_at: dt.datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime, nullable=True),
        description=(
            "Set when this row is the guest account of (event_id, email): the "
            "address was confirmed through a mail link. The first confirmed chain "
            "of an address becomes the account in place; later ones are merged "
            "into it (logic/shared_lists/guest_account.py)."
        ),
    )


class SharedListGuestAlias(Base, table=True):
    """A chain merged into a guest account, so its old mail links still open
    the account (``guest_tokens.resolve``).

    ``user_id`` is the merged chain's former user id and has no foreign key,
    because the merge deletes that user. ``manage_nonce`` is the chain's nonce
    at the merge; it verifies the chain's old tokens. Like the nonce on the
    contact row, an alias is a credential, not data about a person, so the
    Art. 15 export leaves it out. Aliases die with their account: by CASCADE,
    and in ``erase.anonymise``.
    """

    __tablename__ = "shared_list_guest_aliases"  # type: ignore[assignment]

    user_id: uuid.UUID = Field(
        sa_column=sa.Column(sa.Uuid, nullable=False, unique=True, index=True),
    )
    manage_nonce: str = Field(sa_column=sa.Column(sa.String(32), nullable=False))
    account_user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )


class GuestActivityLog(Base, table=True):
    """Append-only: one row per guest sign-up and per guest mail sent, however
    many shifts the mail names, since the ceilings count mails.

    The daily ceilings per address, list, event and organiser count these rows,
    so nothing a guest or an organiser deletes can reset them: there are no
    foreign keys. Rows older than seven days are pruned. ``address_hash`` is a
    keyed hash of the normalised address, NULL when none was given.
    """

    __tablename__ = "guest_activity_log"  # type: ignore[assignment]
    __table_args__ = (
        sa.CheckConstraint(
            "kind IN ('signup', 'confirmation', 'reminder', 'cancelled', "
            "'moved', 'removed')",
            name="ck_guest_activity_log_kind",
        ),
        sa.Index(
            "ix_guest_activity_log_address_created",
            "address_hash",
            "created_at",
            postgresql_where=sa.text("address_hash IS NOT NULL"),
        ),
        sa.Index("ix_guest_activity_log_event_created", "event_id", "created_at"),
        sa.Index("ix_guest_activity_log_list_created", "shared_list_id", "created_at"),
        sa.Index(
            "ix_guest_activity_log_organiser_created", "organiser_id", "created_at"
        ),
    )

    kind: str = Field(sa_column=sa.Column(sa.String(16), nullable=False))
    address_hash: str | None = Field(
        default=None, sa_column=sa.Column(sa.String(64), nullable=True)
    )
    event_id: uuid.UUID | None = Field(
        default=None, sa_column=sa.Column(sa.Uuid, nullable=True)
    )
    shared_list_id: uuid.UUID | None = Field(
        default=None, sa_column=sa.Column(sa.Uuid, nullable=True)
    )
    booking_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(sa.Uuid, nullable=True),
        description="The sign-up's booking, or the first one a mail names",
    )
    organiser_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(sa.Uuid, nullable=True),
        description="events.created_by_id when the mail was sent",
    )


class GuestMailSuppression(Base, table=True):
    """An address that asked never to be mailed again ("Das war ich nicht").

    Never pruned: it records a person's wish. Keyed hash only, like the log.
    """

    __tablename__ = "guest_mail_suppressions"  # type: ignore[assignment]

    address_hash: str = Field(
        sa_column=sa.Column(sa.String(64), nullable=False, unique=True, index=True),
    )
