import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class AdminOrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: Literal["active", "suspended"]
    created_at: datetime
    require_2fa: bool
    members: int
    clients: int
    support_until: datetime | None


class AdminOrganizationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    admin_email: EmailStr


class AdminOrganizationCreatedOut(BaseModel):
    organization: AdminOrganizationOut
    invitation_link: str


class SupportMemberOut(BaseModel):
    full_name: str
    email: str
    role: str
    status: str
    two_factor_enabled: bool
    last_login_at: datetime | None


class SupportWeddingOut(BaseModel):
    id: uuid.UUID
    title: str
    wedding_date: date | None
    status: str
    team: int


class SupportAuditOut(BaseModel):
    created_at: datetime
    action: str
    resource_type: str
    actor_name: str | None
    actor_type: str


class SupportViewOut(BaseModel):
    """What platform support sees during an active grant: structure, not content."""

    organization: AdminOrganizationOut
    grant_expires_at: datetime
    members: list[SupportMemberOut]
    weddings: list[SupportWeddingOut]
    audit: list[SupportAuditOut]


class ResetTwoFactorIn(BaseModel):
    email: EmailStr
    reason: str = Field(min_length=5, max_length=300)


class SupportGrantIn(BaseModel):
    days: int = Field(default=3, ge=1, le=14)
    reason: str | None = Field(default=None, max_length=300)


class SupportGrantOut(BaseModel):
    id: uuid.UUID
    granted_by_name: str | None
    reason: str | None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    active: bool
