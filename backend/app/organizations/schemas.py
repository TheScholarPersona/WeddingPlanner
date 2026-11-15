import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

TeamRole = Literal["org_admin", "member"]


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    accent_color: str | None
    locale: str
    timezone: str
    client_access_days_after_archive: int


class OrganizationUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    accent_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    locale: Literal["de-DE", "de-AT", "de-CH", "en-GB", "en-US"] | None = None
    timezone: Literal["Europe/Berlin", "Europe/Vienna", "Europe/Zurich", "Europe/London"] | None = (
        None
    )
    client_access_days_after_archive: int | None = Field(default=None, ge=0, le=3650)


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str
    role: Literal["org_admin", "member", "client"]
    status: Literal["active", "disabled"]
    is_you: bool
    created_at: datetime


class MemberUpdateIn(BaseModel):
    role: TeamRole | None = None
    status: Literal["active", "disabled"] | None = None


class InvitationIn(BaseModel):
    email: EmailStr
    role: TeamRole = "member"

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: Literal["org_admin", "member", "client"]
    status: Literal["pending", "expired"]
    invited_by_name: str | None
    created_at: datetime
    expires_at: datetime


class AuditEntryOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    action: str
    actor_type: str
    actor_name: str | None
    resource_type: str
    resource_id: uuid.UUID | None
    changes: dict[str, object] | None
    ip: str | None


class AuditPageOut(BaseModel):
    items: list[AuditEntryOut]
    next_cursor: uuid.UUID | None
