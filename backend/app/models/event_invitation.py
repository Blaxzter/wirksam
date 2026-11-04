import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import Base


class EventInvitation(Base, table=True):
    """An outstanding invitation into an event.

    Two flavours share this table:

    * **Targeted** (``email`` set) — addressed at one person, single use. The
      invitee may not have an account yet; it is matched on email at accept
      time, which is why it is keyed on the address rather than a user id.
    * **Link** (``email`` NULL) — a shareable token anyone signed in may
      redeem, reusable until it is revoked or expires.

    A targeted invitation can also ask the invitee to be in charge of tasks
    (``event_invitation_tasks``), applied when they accept. One that was
    created only for that (``for_tasks_only``) is revoked when its last task
    link goes; an invitation from the event settings just loses the link.

    Deleting a user cascades to the events they own. Postgres applies that
    CASCADE and any ``SET NULL`` on the *same* user in one statement, and the
    SET NULL re-checks this row's ``event_id`` — which may already be gone,
    raising a foreign-key violation. Both user references therefore cascade:
    an invitation is a short-lived workflow record, so removing it along with
    the person it belongs to is the right outcome anyway.
    """

    __tablename__ = "event_invitations"  # type: ignore[assignment]

    __table_args__ = (
        sa.Index("ix_event_invitations_event_email", "event_id", "email"),
    )

    event_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    email: str | None = Field(
        default=None,
        sa_column=sa.Column(sa.String, nullable=True, index=True),
        description="Target address for a targeted invite; NULL for a share link",
    )
    role: str = Field(
        default="member",
        sa_column=sa.Column(sa.String(16), nullable=False, server_default="member"),
        description="Role granted on acceptance: admin or member",
    )
    token: str = Field(
        sa_column=sa.Column(sa.String(64), nullable=False, unique=True, index=True),
        description="Opaque secret carried in the invite URL",
    )
    # Both user references CASCADE rather than SET NULL — see the class
    # docstring for why SET NULL breaks when the inviter owns the event.
    invited_by_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    expires_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime, nullable=True),
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime, nullable=True),
    )
    accepted_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime, nullable=True),
        description="Set on a targeted invite once redeemed; link invites stay open",
    )
    accepted_by_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    use_count: int = Field(
        default=0,
        sa_column=sa.Column(sa.Integer, nullable=False, server_default="0"),
        description="How many times a link invite has been redeemed",
    )
    for_tasks_only: bool = Field(
        default=False,
        sa_column=sa.Column(
            sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        description=(
            "Created by inviting someone to be in charge of a task; revoked "
            "when its last task link goes"
        ),
    )
    last_sent_at: datetime | None = Field(
        default=None,
        sa_column=sa.Column(sa.DateTime, nullable=True),
        description=(
            "When the last mail or notification for it was queued; throttles "
            "sending it again"
        ),
    )
