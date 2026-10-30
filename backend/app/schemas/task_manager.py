import uuid

from pydantic import BaseModel


class TaskManagerAdd(BaseModel):
    """Put an event member in charge of a task."""

    user_id: uuid.UUID


class TaskManagerBrief(BaseModel):
    """A person in charge of a task, as every viewer of the task sees them."""

    user_id: uuid.UUID
    name: str | None = None
    avatar_etag: str | None = None
