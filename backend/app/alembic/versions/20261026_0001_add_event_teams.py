"""Event teams: groups within an event that can gate booking a task's shifts

``event_teams`` belongs to one event; ``event_team_members`` holds both the
approved members and the pending requests. ``tasks.team_id`` names the team
whose approved members may book that task.

A team can list requirements (``event_team_requirements``) a decider has to
tick off before approving someone. Ticking one stores an ``event_team_checks``
row (who, when, the document's issue date and the resulting expiry), never
the document. A requester may attach a file per requirement while the request
is pending (``event_team_documents``); it is deleted once the request is
decided.

``tasks.team_id`` gets a ``DEFERRABLE INITIALLY DEFERRED`` check, like
``tasks.location_id``: a user delete cascades to the event, the events->tasks
SET NULL rewrites the task row and re-checks team_id against a team the same
statement has already removed.

``decided_by_id`` and ``checked_by_id`` are plain columns without a foreign
key: a CASCADE would revoke a membership when its approver deletes their
account, and SET NULL is the trap in app/models/CLAUDE.md. The names next to
them are kept for display.

Revision ID: 20261026_0001
Revises: 20261016_0002
Create Date: 2026-10-26 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "20261026_0001"
down_revision = "20261016_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "event_teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("contact", sa.String(length=255), nullable=True),
        sa.Column(
            "requires_approval",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_teams_id", "event_teams", ["id"])
    op.create_index("ix_event_teams_event_id", "event_teams", ["event_id"])
    op.create_index(
        "uq_event_teams_event_id_lower_name",
        "event_teams",
        ["event_id", sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "event_team_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "ask_issue_date",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("valid_for_years", sa.Integer(), nullable=True),
        sa.Column(
            "accepts_document",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["event_teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_team_requirements_id", "event_team_requirements", ["id"]
    )
    op.create_index(
        "ix_event_team_requirements_team_id", "event_team_requirements", ["team_id"]
    )

    op.create_table(
        "event_team_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column(
            "role", sa.String(length=16), server_default="member", nullable=False
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by_name", sa.String(length=255), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["event_teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_event_team_member"),
    )
    op.create_index("ix_event_team_members_id", "event_team_members", ["id"])
    op.create_index(
        "ix_event_team_members_team_id", "event_team_members", ["team_id"]
    )
    op.create_index(
        "ix_event_team_members_user_id", "event_team_members", ["user_id"]
    )
    op.create_index(
        "ix_event_team_members_status", "event_team_members", ["status"]
    )

    op.create_table(
        "event_team_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("checked_by_id", sa.Uuid(), nullable=True),
        sa.Column("checked_by_name", sa.String(length=255), nullable=True),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(
            ["member_id"], ["event_team_members.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["event_team_requirements.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "member_id", "requirement_id", name="uq_event_team_check"
        ),
    )
    op.create_index("ix_event_team_checks_id", "event_team_checks", ["id"])
    op.create_index(
        "ix_event_team_checks_member_id", "event_team_checks", ["member_id"]
    )
    op.create_index(
        "ix_event_team_checks_requirement_id", "event_team_checks", ["requirement_id"]
    )

    op.create_table(
        "event_team_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(
            ["member_id"], ["event_team_members.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["event_team_requirements.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "member_id", "requirement_id", name="uq_event_team_document"
        ),
    )
    op.create_index("ix_event_team_documents_id", "event_team_documents", ["id"])
    op.create_index(
        "ix_event_team_documents_member_id", "event_team_documents", ["member_id"]
    )
    op.create_index(
        "ix_event_team_documents_requirement_id",
        "event_team_documents",
        ["requirement_id"],
    )

    op.add_column("tasks", sa.Column("team_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "tasks_team_id_fkey",
        "tasks",
        "event_teams",
        ["team_id"],
        ["id"],
        ondelete="SET NULL",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_index("ix_tasks_team_id", "tasks", ["team_id"])


def downgrade():
    op.drop_index("ix_tasks_team_id", table_name="tasks")
    op.drop_constraint("tasks_team_id_fkey", "tasks", type_="foreignkey")
    op.drop_column("tasks", "team_id")

    op.drop_index(
        "ix_event_team_documents_requirement_id", table_name="event_team_documents"
    )
    op.drop_index(
        "ix_event_team_documents_member_id", table_name="event_team_documents"
    )
    op.drop_index("ix_event_team_documents_id", table_name="event_team_documents")
    op.drop_table("event_team_documents")

    op.drop_index(
        "ix_event_team_checks_requirement_id", table_name="event_team_checks"
    )
    op.drop_index("ix_event_team_checks_member_id", table_name="event_team_checks")
    op.drop_index("ix_event_team_checks_id", table_name="event_team_checks")
    op.drop_table("event_team_checks")

    op.drop_index("ix_event_team_members_status", table_name="event_team_members")
    op.drop_index("ix_event_team_members_user_id", table_name="event_team_members")
    op.drop_index("ix_event_team_members_team_id", table_name="event_team_members")
    op.drop_index("ix_event_team_members_id", table_name="event_team_members")
    op.drop_table("event_team_members")

    op.drop_index(
        "ix_event_team_requirements_team_id", table_name="event_team_requirements"
    )
    op.drop_index(
        "ix_event_team_requirements_id", table_name="event_team_requirements"
    )
    op.drop_table("event_team_requirements")

    op.drop_index("uq_event_teams_event_id_lower_name", table_name="event_teams")
    op.drop_index("ix_event_teams_event_id", table_name="event_teams")
    op.drop_index("ix_event_teams_id", table_name="event_teams")
    op.drop_table("event_teams")
