import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import Base

# Ordered weakest → strongest, like EVENT_ROLES.
TEAM_ROLES = ("member", "lead")


class EventTeam(Base, table=True):
    """A group of people within one event, which tasks can require.

    A team that ``requires_approval`` is a *restricted* team: joining it opens a
    request a team lead or event admin has to approve, and only then may the
    person book the shifts of tasks that require it. A team without approval is
    effectively a self-declared skill tag — joining is immediate.

    A restricted team can list *requirements* (``EventTeamRequirement``), each
    of which the decider has to tick off before approving someone.
    """

    __tablename__ = "event_teams"  # type: ignore[assignment]

    # Unique per event ignoring case, so "Kasse" and "kasse" cannot both exist.
    # The routes check first for a friendly 409; this index settles the race.
    # Declared here as well as in the migration because ``alembic check``
    # reflects expression indexes (see users.ix_users_email_lower).
    __table_args__ = (
        sa.Index(
            "uq_event_teams_event_id_lower_name",
            "event_id",
            sa.text("lower(name)"),
            unique=True,
        ),
    )

    event_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    name: str = Field(sa_column=sa.Column(sa.String(100), nullable=False))
    description: str | None = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )
    contact: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String(255), nullable=True),
        description="Free text shown to volunteers: who to ask about this team",
    )
    requires_approval: bool = Field(
        default=True,
        sa_column=sa.Column(sa.Boolean, nullable=False, server_default=sa.text("true")),
    )


class EventTeamRequirement(Base, table=True):
    """Something a decider must have checked before approving a team request.

    "Extended police certificate", "First-aid course", "Driving licence B".
    The requirement only describes the check; whether a given member passed it
    is an ``EventTeamCheck``. Nothing here stores the evidence itself.
    """

    __tablename__ = "event_team_requirements"  # type: ignore[assignment]

    team_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("event_teams.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    label: str = Field(sa_column=sa.Column(sa.String(200), nullable=False))
    description: str | None = Field(
        default=None, sa_column=sa.Column(sa.Text, nullable=True)
    )
    ask_issue_date: bool = Field(
        default=False,
        sa_column=sa.Column(
            sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        description="The decider records when the document was issued",
    )
    valid_for_years: int | None = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, nullable=True),
        description="A check expires this many years after the issue date",
    )
    accepts_document: bool = Field(
        default=False,
        sa_column=sa.Column(
            sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        description=(
            "The requester may attach one file to their request. It is deleted "
            "as soon as the request is decided"
        ),
    )
    position: int = Field(
        default=0,
        sa_column=sa.Column(sa.Integer, nullable=False, server_default="0"),
    )


class EventTeamMember(Base, table=True):
    """A user's place in a team — or their request for one.

    Unlike event membership, the request and the membership share a row: a
    team is always inside an event the user already belongs to, so a pending
    row grants nothing beyond what event membership already does. Every
    access decision still goes through ``app.logic.teams`` (which filters on
    ``status == "approved"``) rather than reading this table directly.
    """

    __tablename__ = "event_team_members"  # type: ignore[assignment]

    __table_args__ = (
        sa.UniqueConstraint("team_id", "user_id", name="uq_event_team_member"),
    )

    team_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("event_teams.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    status: str = Field(
        default="pending",
        sa_column=sa.Column(
            sa.String(16), nullable=False, server_default="pending", index=True
        ),
        description="One of: pending, approved, declined",
    )
    role: str = Field(
        default="member",
        sa_column=sa.Column(sa.String(16), nullable=False, server_default="member"),
        description="One of: member, lead",
    )
    message: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.Text, nullable=True),
        description="Optional note from the requester to the team leads",
    )
    # Deliberately no foreign key. A CASCADE would delete this membership when
    # the person who approved it deletes their account, and SET NULL is the
    # trap app/models/CLAUDE.md describes. The name is kept for display; the
    # id is only ever compared, never joined, and may point at nobody.
    decided_by_id: uuid.UUID | None = Field(
        default=None, sa_column=sa.Column(sa.Uuid, nullable=True)
    )
    decided_by_name: str | None = Field(
        default=None, sa_column=sa.Column(sa.String(255), nullable=True)
    )
    decided_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime, nullable=True),
    )


class EventTeamCheck(Base, table=True):
    """That a decider saw proof of one requirement for one member.

    Only the fact is stored — who checked, when, and the document's issue
    date — never the document. Deleting the member row (leaving the team,
    removal from the event, account deletion) takes the check with it.
    """

    __tablename__ = "event_team_checks"  # type: ignore[assignment]

    __table_args__ = (
        sa.UniqueConstraint("member_id", "requirement_id", name="uq_event_team_check"),
    )

    member_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("event_team_members.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    requirement_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("event_team_requirements.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    # Denormalised like decided_by_* above: no user FK, so deleting the
    # checker's account leaves the record intact.
    checked_by_id: uuid.UUID | None = Field(
        default=None, sa_column=sa.Column(sa.Uuid, nullable=True)
    )
    checked_by_name: str | None = Field(
        default=None, sa_column=sa.Column(sa.String(255), nullable=True)
    )
    checked_at: datetime = Field(sa_column=sa.Column(sa.DateTime, nullable=False))
    issued_on: date | None = Field(
        default=None, sa_column=sa.Column(sa.Date, nullable=True)
    )
    #: Worked out when the check is recorded, from ``valid_for_years``.
    expires_on: date | None = Field(
        default=None, sa_column=sa.Column(sa.Date, nullable=True)
    )


class EventTeamDocument(Base, table=True):
    """A file a requester attached to a pending request, for one requirement.

    Short-lived by design: deleted the moment the request is decided, withdrawn
    or the member row goes away, so the database never becomes an archive of
    certificates. What remains afterwards is the ``EventTeamCheck``.
    """

    __tablename__ = "event_team_documents"  # type: ignore[assignment]

    __table_args__ = (
        sa.UniqueConstraint(
            "member_id", "requirement_id", name="uq_event_team_document"
        ),
    )

    member_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("event_team_members.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    requirement_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("event_team_requirements.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    filename: str = Field(sa_column=sa.Column(sa.String(255), nullable=False))
    content_type: str = Field(sa_column=sa.Column(sa.String(64), nullable=False))
    size: int = Field(sa_column=sa.Column(sa.Integer, nullable=False))
    storage_key: str = Field(
        sa_column=sa.Column(sa.String(255), nullable=False, unique=True, index=True),
        description="Key of the file in app.core.storage",
    )
