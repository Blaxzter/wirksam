import uuid
from abc import ABC
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Base(SQLModel, ABC):
    """Abstract base model for all SQLModel models in the application.

    This class provides common fields and functionality that should be inherited
    by all database models. It includes automatic timestamping and sensible
    defaults for primary keys.

    All datetime fields are stored as UTC without timezone info (TIMESTAMP WITHOUT TIME ZONE).
    The application treats all datetimes as UTC.

    Attributes:
        id: Primary key field with auto-increment
        created_at: Timestamp when the record was created (auto-set on insert, UTC)
        updated_at: Timestamp when the record was last updated (auto-set on insert/update, UTC)
    """

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the record",
        index=True,
    )

    # sa_type pins the naive column. Left to sqlmodel, a bare ``datetime`` maps
    # to its UTCDateTime (timezone-aware), which refuses the naive values the
    # whole application stores.
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_type=sa.DateTime,
        description="When this record was created (UTC)",
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_type=sa.DateTime,
        description="When this record was last updated (UTC)",
    )

    def __repr__(self) -> str:
        """String representation of the model."""
        class_name = self.__class__.__name__
        if self.id:
            return f"<{class_name}(id={self.id})>"
        return f"<{class_name}(new)>"


# Alternative base class with soft delete functionality
class SoftDeleteBase(Base):
    """Base model with soft delete functionality."""

    deleted_at: datetime | None = Field(
        default=None,
        sa_type=sa.DateTime,
        description="When this record was deleted (null if not deleted, UTC)",
    )

    is_deleted: bool = Field(
        default=False, description="Whether this record has been soft deleted"
    )

    def soft_delete(self) -> None:
        """Mark this record as deleted."""
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
