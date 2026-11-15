import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH

NewPassword = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
AnyPassword = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class _EmailIn(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()


class LoginIn(_EmailIn):
    password: str = AnyPassword


class ForgotPasswordIn(_EmailIn):
    pass


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = NewPassword


class ReauthIn(BaseModel):
    password: str = AnyPassword


class ChangePasswordIn(BaseModel):
    current_password: str = AnyPassword
    new_password: str = NewPassword


class UpdateMeIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    locale: Literal["en"] | None = None


class MembershipOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    role: Literal["org_admin", "member", "client"]
    accent_color: str | None


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    locale: str
    memberships: list[MembershipOut]


class InvitationInfoOut(BaseModel):
    organization_name: str
    email: str
    role: Literal["org_admin", "member", "client"]
    account_exists: bool


class AcceptInvitationIn(BaseModel):
    """New accounts send full_name and a new password; existing accounts their password."""

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str = AnyPassword
