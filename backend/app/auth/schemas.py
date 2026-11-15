import uuid
from datetime import datetime
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
    two_factor_enabled: bool = False
    is_platform_admin: bool = False


class TwoFactorChallengeOut(BaseModel):
    """Password accepted; the sign-in completes with POST /auth/2fa/verify."""

    two_factor_required: Literal[True] = True


class TwoFactorCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class TwoFactorSetupOut(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg: str


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


class TwoFactorStatusOut(BaseModel):
    enabled: bool
    enabled_at: datetime | None
    recovery_codes_left: int


class DisableTwoFactorIn(BaseModel):
    password: str = AnyPassword
    code: str = Field(min_length=6, max_length=20)


class InvitationInfoOut(BaseModel):
    organization_name: str
    email: str
    role: Literal["org_admin", "member", "client"]
    account_exists: bool


class AcceptInvitationIn(BaseModel):
    """New accounts send full_name and a new password; existing accounts their password."""

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    password: str = AnyPassword
