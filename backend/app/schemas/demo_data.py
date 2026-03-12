from pydantic import BaseModel, Field

DEMO_PREFIX = "[DEMO]"


class DemoDataParams(BaseModel):
    num_events: int = Field(default=10, ge=1, le=50)
    num_event_groups: int = Field(default=3, ge=0, le=10)
    num_users: int = Field(default=5, ge=0, le=20)
    num_slots_per_event: int = Field(default=4, ge=1, le=20)
    publish_events: bool = Field(default=True)


class DemoDataCreatedResponse(BaseModel):
    event_groups_created: int
    events_created: int
    users_created: int
    duty_slots_created: int
    bookings_created: int


class DemoDataDeletedResponse(BaseModel):
    events_deleted: int
    event_groups_deleted: int
    users_deleted: int
    duty_slots_deleted: int
    bookings_deleted: int
