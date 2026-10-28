from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StoredObject(SQLModel, table=True):
    """The bytes of one uploaded file, for ``STORAGE_BACKEND=postgres``.

    Addressed by the same key an S3 object would have, so the rows that own a
    file (``user_avatars``, ``venue_plan_images``, ``venue_template_images``,
    ``event_team_documents``) only ever hold a ``storage_key`` and do not care
    where the bytes are. With the S3 backend this table is empty, except for
    files the copy script has not moved yet.
    """

    __tablename__ = "stored_objects"  # type: ignore[assignment]

    key: str = Field(sa_column=sa.Column(sa.String(255), primary_key=True))
    data: bytes = Field(sa_column=sa.Column(sa.LargeBinary, nullable=False))
    content_type: str = Field(sa_column=sa.Column(sa.String(64), nullable=False))
    created_at: datetime = Field(
        default_factory=_now, sa_column=sa.Column(sa.DateTime, nullable=False)
    )


class StorageDeletion(SQLModel, table=True):
    """A storage key whose owner row is gone; the object is still to be deleted.

    Filled by database triggers on the four file tables (on DELETE, and on
    UPDATE when the key changes), so a file is queued however its row goes:
    an ORM delete, a bulk ``DELETE``, or an ``ON DELETE CASCADE`` from a user
    or an event. ``app/logic/storage_gc.py`` deletes the objects and the rows.
    The same triggers delete a ``stored_objects`` row straight away, so with
    the Postgres backend the bytes go in the same transaction as their owner.
    """

    __tablename__ = "storage_deletions"  # type: ignore[assignment]

    id: int | None = Field(
        default=None,
        sa_column=sa.Column(sa.BigInteger, sa.Identity(), primary_key=True),
    )
    key: str = Field(sa_column=sa.Column(sa.String(255), nullable=False))
    created_at: datetime = Field(
        default_factory=_now,
        sa_column=sa.Column(
            sa.DateTime,
            nullable=False,
            # Set by the trigger's INSERT, which names only the key.
            server_default=sa.text("timezone('utc', now())"),
        ),
    )
