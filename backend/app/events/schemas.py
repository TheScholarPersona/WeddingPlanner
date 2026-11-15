import datetime as dt
import uuid
from datetime import date, datetime
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, model_validator

VisibilityT = Literal["internal", "client"]


class EventIn(BaseModel):
    """Timed events use starts_at/ends_at; all-day events use start_date/end_date (inclusive)."""

    title: str = Field(min_length=1, max_length=200)
    all_day: bool = False
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    start_date: date | None = None
    end_date: date | None = None
    location: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    visibility: VisibilityT = "internal"

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.all_day:
            if self.start_date is None:
                raise ValueError("start_date is required for all-day events")
            if self.end_date is not None and self.end_date < self.start_date:
                raise ValueError("end_date must not be before start_date")
            if self.end_date is not None and (self.end_date - self.start_date).days > 30:
                raise ValueError("All-day events can span at most 31 days")
        else:
            if self.starts_at is None:
                raise ValueError("starts_at is required")
            if self.ends_at is not None and self.ends_at < self.starts_at:
                raise ValueError("ends_at must not be before starts_at")
        return self


class EventUpdateIn(EventIn):
    """Events are always saved as a whole (the form shows every field)."""


class EventOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    all_day: bool
    starts_at: datetime
    ends_at: datetime | None
    start_date: date
    end_date: date
    location: str | None
    description: str | None
    visibility: VisibilityT
    created_by_name: str | None
    version: int


ItemKind = Literal["event", "task", "payment", "wedding"]


class CalendarItemOut(BaseModel):
    kind: ItemKind
    id: uuid.UUID
    title: str
    project_id: uuid.UUID
    project_title: str
    date: dt.date
    end_date: dt.date
    all_day: bool
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = None
    visibility: VisibilityT = "internal"
    status: str | None = None
    assigned_to_me: bool = False
    amount_cents: int | None = None


class FeedOut(BaseModel):
    active: bool
    created_at: datetime | None = None
    last_used_at: datetime | None = None


class FeedCreatedOut(FeedOut):
    url: str
