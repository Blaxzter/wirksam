"""Volunteer vouchers: the stored half of a balance, and the codes that spend it.

What a volunteer has *earned* is never stored. It is derived from their
confirmed bookings on shifts that have ended (``app/logic/vouchers.py``), the
same way worked hours are, so correcting a shift corrects both. This file holds
what cannot be derived:

* :class:`VoucherEntry`, the ledger: redemptions (debits) and the corrections
  event admins make by hand.
* :class:`VoucherPass`, the short-lived code a volunteer shows at a stand.

None of the ``task_id`` / ``actor_id`` / ``pass_id`` references carries a
foreign key. A CASCADE would delete the debits along with a deleted point task
or redeemer, which refunds them, and SET NULL next to ``event_id`` is the trap
described in ``app/models/CLAUDE.md`` (reached here through
``tasks.created_by_id`` as well as through a user). Name snapshots keep the
rows readable instead, as on ``WorkLog``.
"""

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import Base


class VoucherEntry(Base, table=True):
    """One redemption or one correction in a volunteer's balance for an event.

    Redemptions are append-only; corrections (``kind="adjustment"``) may be
    edited or deleted by event admins.
    """

    __tablename__ = "voucher_entries"  # type: ignore[assignment]
    __table_args__ = (
        sa.Index("ix_voucher_entries_event_id_user_id", "event_id", "user_id"),
        sa.Index("ix_voucher_entries_event_id_task_id", "event_id", "task_id"),
        sa.CheckConstraint(
            "kind IN ('redemption', 'adjustment')", name="ck_voucher_entries_kind"
        ),
        sa.CheckConstraint("amount <> 0", name="ck_voucher_entries_amount_nonzero"),
        sa.CheckConstraint(
            "kind <> 'redemption' OR amount < 0",
            name="ck_voucher_entries_redemption_negative",
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
    #: The volunteer whose balance this changes.
    user_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    #: ``redemption`` or ``adjustment``.
    kind: str = Field(sa_column=sa.Column(sa.String(16), nullable=False))
    #: Signed: a redemption is negative, a correction anything but zero.
    amount: int = Field(sa_column=sa.Column(sa.Integer, nullable=False))
    #: Redemptions only: ``code`` (the volunteer showed it) or ``manual``.
    method: str | None = Field(
        default=None, sa_column=sa.Column(sa.String(16), nullable=True)
    )
    #: Corrections: the reason, required.
    note: str | None = Field(default=None, sa_column=sa.Column(sa.Text, nullable=True))

    # The redemption point. No foreign key (see the module docstring); the
    # name stays readable after the task is deleted.
    task_id: uuid.UUID | None = Field(
        default=None, sa_column=sa.Column(sa.Uuid, nullable=True)
    )
    task_name: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    # Who redeemed or corrected. No foreign key, like WorkLog.created_by_id.
    actor_id: uuid.UUID | None = Field(
        default=None, sa_column=sa.Column(sa.Uuid, nullable=True)
    )
    actor_name: str | None = Field(
        default=None, sa_column=sa.Column(sa.String, nullable=True)
    )
    # The pass a code redemption used. Unique, as the last backstop for
    # single use (NULLs are distinct, so corrections and manual redemptions
    # are not affected). No foreign key: passes are deleted with their user or
    # event, and the entry outlives neither anyway.
    pass_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(sa.Uuid, nullable=True, unique=True, index=True),
    )
    #: Redemptions: the client's idempotency key. A retried redemption whose
    #: response was lost returns the first result instead of debiting twice.
    request_id: uuid.UUID | None = Field(
        default=None,
        sa_column=sa.Column(sa.Uuid, nullable=True, unique=True, index=True),
    )


class VoucherPass(Base, table=True):
    """A code a volunteer shows to have vouchers redeemed: short, single use.

    Six characters, valid for two minutes (``logic/vouchers.PASS_TTL``), and
    unique across the installation, so a code shown in the wrong event is
    recognised as such rather than reported as invalid. Stored in plain text:
    it lives two minutes, works once, and only someone allowed to redeem at a
    point can try it; a hash would add nothing to a 6-character code.

    There is deliberately no unique constraint on ``(event_id, user_id)``.
    Issuing a pass inserts a row and then deletes the user's other unused,
    unheld passes in the event, so two tabs issuing at once briefly leave two
    live codes, which is harmless; a constraint would turn that race into a
    500. Used passes are kept so the volunteer's screen can still say
    "redeemed" after a new code was issued.
    """

    __tablename__ = "voucher_passes"  # type: ignore[assignment]
    __table_args__ = (
        sa.UniqueConstraint("code", name="uq_voucher_passes_code"),
        sa.Index("ix_voucher_passes_event_id_user_id", "event_id", "user_id"),
    )

    event_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid,
            sa.ForeignKey("events.id", ondelete="CASCADE"),
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
    code: str = Field(sa_column=sa.Column(sa.String(6), nullable=False))
    expires_at: dt.datetime = Field(sa_column=sa.Column(sa.DateTime, nullable=False))
    #: Set by a successful check: the pass then stays redeemable for
    #: ``PASS_HOLD`` even if it expires meanwhile.
    checked_at: dt.datetime | None = Field(
        default=None, sa_column=sa.Column(sa.DateTime, nullable=True)
    )
    used_at: dt.datetime | None = Field(
        default=None, sa_column=sa.Column(sa.DateTime, nullable=True)
    )
