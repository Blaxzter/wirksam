"""Shared lists: a public link to sign up for shifts without an account

Organisers, and people in charge of tasks, publish a list of shifts of one event
as a link. Whoever opens it picks a shift, types their name (and an address or
phone number if the list asks) and is booked.

* ``users.is_list_guest``: everyone signing up through a list becomes a
  password-less guest user (subject ``listguest|<hex>``, ``email`` NULL), so
  capacity, ``uq_booking_shift_user``, rosters, reminders and reporting work on
  their bookings unchanged; a NULL email and password keep them out of login,
  password reset and every lookup by address. Indexed like ``is_sandbox``.
* ``bookings.shared_list_id``: which list a booking came through. No foreign
  key, like ``voucher_earnings.booking_id``: SET NULL next to ``user_id``
  CASCADE is the trap in app/models/CLAUDE.md, and a list only ever goes
  together with its event.
* ``bookings.show_first_name``, ``guest_name`` and ``guest_phone``: a guest
  sign-up's own person, its first-name consent and the name and phone the
  chain stored when it signed up. A guest account pools sign-ups of several
  people (a family sharing an address), so one guest user cannot say whose
  name goes on which shift. Member bookings keep false, NULL and NULL.
* ``events.managers_share_lists``: whether people in charge may share their
  tasks this way. On for every existing event through the server default,
  which is what the product owner asked for.
* ``shared_lists``: one link. ``code`` is twelve random characters stored in
  plain text, like ``event_invitations.token``, because organisers copy the
  link again; rotating replaces it on the row. Only live, paused and ended are
  stored; "expired" is derived on the event's clock, so moving shifts cannot
  leave it stale. ``created_by_id`` has no foreign key: a CASCADE would delete
  the list with its creator's account.
* ``shared_list_tasks`` and ``shared_list_excluded_shifts``: what a list
  offers, as tasks minus left-out shifts, so a shift added to a listed task
  later is offered without editing the list.
* ``shared_list_guests``: the contact side of a guest user (address, the
  nonce behind the manage link). Both foreign keys CASCADE, so deleting the
  event removes the address at once. ``shared_list_id`` records the list the
  guest's sign-ups started on, with no foreign key like
  ``bookings.shared_list_id``. ``confirmed_at`` marks a guest account: a
  chain whose address was confirmed through a mail link, at most one per
  event and address (``uq_shared_list_guests_account``, partial on
  ``confirmed_at IS NOT NULL``). Later chains of the address merge into it.
* ``shared_list_guest_aliases``: a chain merged into an account leaves its
  former user id and nonce here, so the links in its old mails open the
  account. ``user_id`` has no foreign key, because the merge deletes that
  user; ``account_user_id`` CASCADEs, so aliases die with their account.
* ``guest_activity_log`` and ``guest_mail_suppressions``: the daily ceilings on
  guest sign-ups and guest mail, and the addresses that asked never to be
  mailed. No foreign keys at all, so no delete anywhere resets a quota, and
  addresses only as a keyed hash.

CHECK constraints and server defaults are invisible to ``alembic check``, so
they are mirrored by hand in app/models/shared_list.py and app/models/booking.py.

The downgrade drops what later versions of this file added with ``IF
EXISTS``, so it also runs on a database that ran an earlier version of it.

Revision ID: 20261110_0001
Revises: 20261104_0004
Create Date: 2026-11-10 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "20261110_0001"
down_revision = "20261104_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "is_list_guest",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("ix_users_is_list_guest", "users", ["is_list_guest"])

    op.add_column("bookings", sa.Column("shared_list_id", sa.Uuid(), nullable=True))
    op.create_index("ix_bookings_shared_list_id", "bookings", ["shared_list_id"])
    op.add_column(
        "bookings",
        sa.Column(
            "show_first_name",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("bookings", sa.Column("guest_name", sa.String(), nullable=True))
    op.add_column("bookings", sa.Column("guest_phone", sa.String(), nullable=True))

    op.add_column(
        "events",
        sa.Column(
            "managers_share_lists",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    op.create_table(
        "shared_lists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column("share_note", sa.String(length=120), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="live"
        ),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("rotated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "ends_mode",
            sa.String(length=16),
            nullable=False,
            server_default="last_shift",
        ),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column(
            "ask_email", sa.String(length=16), nullable=False, server_default="required"
        ),
        sa.Column(
            "ask_phone", sa.String(length=16), nullable=False, server_default="off"
        ),
        sa.Column(
            "show_names", sa.String(length=16), nullable=False, server_default="none"
        ),
        sa.Column("max_per_person", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_name", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
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
    )
    op.create_index("ix_shared_lists_id", "shared_lists", ["id"])
    op.create_index("ix_shared_lists_code", "shared_lists", ["code"], unique=True)
    op.create_index(
        "ix_shared_lists_event_id_status", "shared_lists", ["event_id", "status"]
    )

    op.create_table(
        "shared_list_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("shared_list_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["shared_list_id"], ["shared_lists.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shared_list_id", "task_id", name="uq_shared_list_task"),
    )
    op.create_index("ix_shared_list_tasks_id", "shared_list_tasks", ["id"])
    op.create_index("ix_shared_list_tasks_task_id", "shared_list_tasks", ["task_id"])

    op.create_table(
        "shared_list_excluded_shifts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("shared_list_id", sa.Uuid(), nullable=False),
        sa.Column("shift_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["shared_list_id"], ["shared_lists.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["shift_id"], ["shifts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "shared_list_id", "shift_id", name="uq_shared_list_excluded_shift"
        ),
    )
    op.create_index(
        "ix_shared_list_excluded_shifts_id", "shared_list_excluded_shifts", ["id"]
    )
    op.create_index(
        "ix_shared_list_excluded_shifts_shift_id",
        "shared_list_excluded_shifts",
        ["shift_id"],
    )

    op.create_table(
        "shared_list_guests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("shared_list_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("manage_nonce", sa.String(length=32), nullable=True),
        sa.Column("last_signup_at", sa.DateTime(), nullable=False),
        sa.Column("erased_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shared_list_guests_id", "shared_list_guests", ["id"])
    op.create_index(
        "ix_shared_list_guests_user_id", "shared_list_guests", ["user_id"], unique=True
    )
    op.create_index(
        "ix_shared_list_guests_event_id", "shared_list_guests", ["event_id"]
    )
    op.create_index(
        "ix_shared_list_guests_shared_list_id", "shared_list_guests", ["shared_list_id"]
    )
    op.create_index(
        "ix_shared_list_guests_email_lower",
        "shared_list_guests",
        [sa.text("lower(email)")],
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_index(
        "uq_shared_list_guests_account",
        "shared_list_guests",
        ["event_id", sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("confirmed_at IS NOT NULL"),
    )

    op.create_table(
        "shared_list_guest_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("manage_nonce", sa.String(length=32), nullable=False),
        sa.Column("account_user_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["account_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_shared_list_guest_aliases_id", "shared_list_guest_aliases", ["id"]
    )
    op.create_index(
        "ix_shared_list_guest_aliases_user_id",
        "shared_list_guest_aliases",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        "ix_shared_list_guest_aliases_account_user_id",
        "shared_list_guest_aliases",
        ["account_user_id"],
    )

    op.create_table(
        "guest_activity_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("address_hash", sa.String(length=64), nullable=True),
        sa.Column("event_id", sa.Uuid(), nullable=True),
        sa.Column("shared_list_id", sa.Uuid(), nullable=True),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("organiser_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "kind IN ('signup', 'confirmation', 'reminder', 'cancelled', "
            "'moved', 'removed')",
            name="ck_guest_activity_log_kind",
        ),
    )
    op.create_index("ix_guest_activity_log_id", "guest_activity_log", ["id"])
    op.create_index(
        "ix_guest_activity_log_address_created",
        "guest_activity_log",
        ["address_hash", "created_at"],
        postgresql_where=sa.text("address_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_guest_activity_log_event_created",
        "guest_activity_log",
        ["event_id", "created_at"],
    )
    op.create_index(
        "ix_guest_activity_log_list_created",
        "guest_activity_log",
        ["shared_list_id", "created_at"],
    )
    op.create_index(
        "ix_guest_activity_log_organiser_created",
        "guest_activity_log",
        ["organiser_id", "created_at"],
    )

    op.create_table(
        "guest_mail_suppressions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("address_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guest_mail_suppressions_id", "guest_mail_suppressions", ["id"])
    op.create_index(
        "ix_guest_mail_suppressions_address_hash",
        "guest_mail_suppressions",
        ["address_hash"],
        unique=True,
    )


def downgrade():
    # Its indexes go with it.
    op.execute("DROP TABLE IF EXISTS shared_list_guest_aliases")

    op.drop_index(
        "ix_guest_mail_suppressions_address_hash", table_name="guest_mail_suppressions"
    )
    op.drop_index("ix_guest_mail_suppressions_id", table_name="guest_mail_suppressions")
    op.drop_table("guest_mail_suppressions")

    op.drop_index(
        "ix_guest_activity_log_organiser_created", table_name="guest_activity_log"
    )
    op.drop_index("ix_guest_activity_log_list_created", table_name="guest_activity_log")
    op.drop_index(
        "ix_guest_activity_log_event_created", table_name="guest_activity_log"
    )
    op.drop_index(
        "ix_guest_activity_log_address_created", table_name="guest_activity_log"
    )
    op.drop_index("ix_guest_activity_log_id", table_name="guest_activity_log")
    op.drop_table("guest_activity_log")

    op.drop_index("ix_shared_list_guests_email_lower", table_name="shared_list_guests")
    op.drop_index(
        "ix_shared_list_guests_shared_list_id", table_name="shared_list_guests"
    )
    op.drop_index("ix_shared_list_guests_event_id", table_name="shared_list_guests")
    op.drop_index("ix_shared_list_guests_user_id", table_name="shared_list_guests")
    op.drop_index("ix_shared_list_guests_id", table_name="shared_list_guests")
    # uq_shared_list_guests_account goes with the table.
    op.drop_table("shared_list_guests")

    op.drop_index(
        "ix_shared_list_excluded_shifts_shift_id",
        table_name="shared_list_excluded_shifts",
    )
    op.drop_index(
        "ix_shared_list_excluded_shifts_id", table_name="shared_list_excluded_shifts"
    )
    op.drop_table("shared_list_excluded_shifts")

    op.drop_index("ix_shared_list_tasks_task_id", table_name="shared_list_tasks")
    op.drop_index("ix_shared_list_tasks_id", table_name="shared_list_tasks")
    op.drop_table("shared_list_tasks")

    op.drop_index("ix_shared_lists_event_id_status", table_name="shared_lists")
    op.drop_index("ix_shared_lists_code", table_name="shared_lists")
    op.drop_index("ix_shared_lists_id", table_name="shared_lists")
    op.drop_table("shared_lists")

    op.drop_column("events", "managers_share_lists")

    op.execute(
        "ALTER TABLE bookings DROP COLUMN IF EXISTS show_first_name, "
        "DROP COLUMN IF EXISTS guest_name, DROP COLUMN IF EXISTS guest_phone"
    )
    op.drop_index("ix_bookings_shared_list_id", table_name="bookings")
    op.drop_column("bookings", "shared_list_id")

    op.drop_index("ix_users_is_list_guest", table_name="users")
    op.drop_column("users", "is_list_guest")
