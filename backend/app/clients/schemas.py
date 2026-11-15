import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

ClientStatusT = Literal["inquiry", "proposal", "booked", "completed", "lost"]


class ContactIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    role: Literal["partner", "family", "other"] = "partner"
    is_primary: bool = False


class ContactUpdateIn(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    role: Literal["partner", "family", "other"] | None = None
    is_primary: bool | None = None


class ContactOut(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str | None
    email: str | None
    phone: str | None
    role: str
    is_primary: bool
    has_portal_access: bool


class ClientIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    status: ClientStatusT = "inquiry"
    source: str | None = Field(default=None, max_length=100)
    notes_internal: str | None = Field(default=None, max_length=10_000)
    contacts: list[ContactIn] = Field(default_factory=list, max_length=10)


class ClientUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    status: ClientStatusT | None = None
    source: str | None = Field(default=None, max_length=100)
    notes_internal: str | None = Field(default=None, max_length=10_000)


class ClientProjectOut(BaseModel):
    id: uuid.UUID
    title: str
    wedding_date: date | None
    status: str


class ClientOut(BaseModel):
    id: uuid.UUID
    display_name: str
    status: ClientStatusT
    source: str | None
    primary_contact: str | None
    primary_email: str | None
    next_wedding_date: date | None
    project_count: int
    created_at: datetime


class ClientDetailOut(ClientOut):
    notes_internal: str | None
    contacts: list[ContactOut]
    projects: list[ClientProjectOut]
