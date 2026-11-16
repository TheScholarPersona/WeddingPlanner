from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Response, status

from app.audit import service as audit
from app.auth import service, two_factor
from app.auth.models import User
from app.auth.schemas import (
    AcceptInvitationIn,
    ChangePasswordIn,
    DisableTwoFactorIn,
    ForgotPasswordIn,
    InvitationInfoOut,
    LoginIn,
    MeOut,
    ReauthIn,
    RecoveryCodesOut,
    ResetPasswordIn,
    TwoFactorChallengeOut,
    TwoFactorCodeIn,
    TwoFactorSetupOut,
    TwoFactorStatusOut,
    UpdateMeIn,
)
from app.authz.deps import Authenticated, CurrentUser, DbSession, PendingTwoFactor
from app.core import ratelimit
from app.core.config import get_settings
from app.core.context import current_request
from app.core.errors import ProblemError
from app.core.security import hash_password, verify_password

router = APIRouter(tags=["auth"])

# Invitation tokens carry 256 bits of entropy; the limit only dampens scripted probing.
INVITATION_LIMIT = 30


def require_recent_session_auth(auth: Authenticated) -> None:
    """Security settings need a password confirmation from the last few minutes."""
    window = timedelta(minutes=get_settings().reauth_window_minutes)
    reauth_at = auth.session.reauth_at
    if reauth_at is None or datetime.now(UTC) - reauth_at > window:
        raise ProblemError(
            403,
            "reauth_required",
            "Please confirm your password",
            "For your security, confirm your password to continue.",
        )


def _client_key() -> str:
    info = current_request()
    return (info.ip if info and info.ip else "unknown")[:64]


async def _limit(scope: str, *extra: str, limit: int | None = None) -> None:
    limit = limit or get_settings().login_rate_limit_per_minute
    keys = [f"{scope}:ip:{_client_key()}", *(f"{scope}:{e}" for e in extra)]
    await ratelimit.enforce(keys, limit)


async def _sign_in(db: DbSession, user: User, response: Response) -> MeOut | TwoFactorChallengeOut:
    """Starts a session; with 2FA on it only allows entering the code until that is done."""
    if user.two_factor_enabled:
        await service.start_session(db, user, response, mfa_pending=True)
        return TwoFactorChallengeOut()
    await service.start_session(db, user, response)
    return await service.build_me(db, user)


@router.post("/auth/login", response_model=MeOut | TwoFactorChallengeOut)
async def login(body: LoginIn, response: Response, db: DbSession) -> MeOut | TwoFactorChallengeOut:
    await _limit("login", f"email:{body.email}")
    user = await service.authenticate(db, body.email, body.password)
    return await _sign_in(db, user, response)


MAX_CODE_FAILURES = 5
# Above MAX_CODE_FAILURES, so the attempt is ended (not just slowed down) after five wrong codes.
TWO_FACTOR_LIMIT = 10


@router.post("/auth/2fa/verify", response_model=MeOut)
async def verify_two_factor(
    body: TwoFactorCodeIn, auth: PendingTwoFactor, response: Response, db: DbSession
) -> MeOut:
    await _limit("2fa", f"user:{auth.user.id}", limit=TWO_FACTOR_LIMIT)
    if not await two_factor.verify(db, auth.user, body.code):
        auth.session.mfa_failures += 1
        await audit.record(
            db,
            action="auth.two_factor_failed",
            resource_type="user",
            resource_id=auth.user.id,
            actor_user_id=auth.user.id,
        )
        if auth.session.mfa_failures >= MAX_CODE_FAILURES:
            auth.session.revoked_at = datetime.now(UTC)
            service.clear_session_cookies(response)
            await db.commit()
            raise ProblemError(
                401, "not_authenticated", "Please sign in again", "Too many wrong codes."
            )
        await db.commit()
        raise two_factor.INVALID_CODE
    auth.session.mfa_pending = False
    auth.session.reauth_at = datetime.now(UTC)
    await audit.record(
        db,
        action="auth.login_succeeded",
        resource_type="user",
        resource_id=auth.user.id,
        actor_user_id=auth.user.id,
        changes={"two_factor": {"new": True}},
    )
    return await service.build_me(db, auth.user)


@router.post("/auth/2fa/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_two_factor(auth: PendingTwoFactor, response: Response) -> None:
    auth.session.revoked_at = datetime.now(UTC)
    service.clear_session_cookies(response)


# --- Two-factor settings (signed-in user) ---------------------------------------------------


@router.get("/me/2fa", response_model=TwoFactorStatusOut)
async def two_factor_status(auth: CurrentUser, db: DbSession) -> TwoFactorStatusOut:
    return TwoFactorStatusOut(
        enabled=auth.user.two_factor_enabled,
        enabled_at=auth.user.totp_enabled_at,
        recovery_codes_left=await two_factor.remaining_codes(db, auth.user),
    )


@router.post("/me/2fa/setup", response_model=TwoFactorSetupOut)
async def two_factor_setup(auth: CurrentUser, db: DbSession) -> TwoFactorSetupOut:
    require_recent_session_auth(auth)
    secret, uri, qr = await two_factor.start_setup(db, auth.user)
    return TwoFactorSetupOut(secret=secret, otpauth_uri=uri, qr_svg=qr)


@router.post("/me/2fa/enable", response_model=RecoveryCodesOut)
async def two_factor_enable(
    body: TwoFactorCodeIn, auth: CurrentUser, db: DbSession
) -> RecoveryCodesOut:
    await _limit("2fa", f"user:{auth.user.id}", limit=TWO_FACTOR_LIMIT)
    require_recent_session_auth(auth)
    codes = await two_factor.enable(db, auth.user, body.code)
    # Other devices signed in with the password alone are signed out.
    await service.revoke_sessions(db, auth.user.id, keep=auth.session.id)
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/me/2fa/recovery-codes", response_model=RecoveryCodesOut)
async def two_factor_new_codes(auth: CurrentUser, db: DbSession) -> RecoveryCodesOut:
    require_recent_session_auth(auth)
    return RecoveryCodesOut(recovery_codes=await two_factor.regenerate_codes(db, auth.user))


@router.post("/me/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def two_factor_disable(body: DisableTwoFactorIn, auth: CurrentUser, db: DbSession) -> None:
    await _limit("2fa", f"user:{auth.user.id}", limit=TWO_FACTOR_LIMIT)
    if not verify_password(auth.user.password_hash, body.password):
        raise ProblemError(
            400,
            "invalid_current_password",
            "Current password incorrect",
            "The current password is incorrect.",
        )
    if not await two_factor.verify(db, auth.user, body.code):
        raise two_factor.INVALID_CODE
    if auth.user.is_platform_admin:
        raise ProblemError(
            409,
            "two_factor_mandatory",
            "Two-factor authentication is required",
            "Platform administrators cannot turn off two-factor authentication.",
        )
    await two_factor.disable(db, auth.user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(auth: CurrentUser, response: Response, db: DbSession) -> None:
    auth.session.revoked_at = datetime.now(UTC)
    await audit.record(
        db,
        action="auth.logout",
        resource_type="user",
        resource_id=auth.user.id,
        actor_user_id=auth.user.id,
    )
    service.clear_session_cookies(response)


@router.post("/auth/reauth", status_code=status.HTTP_204_NO_CONTENT)
async def reauth(body: ReauthIn, auth: CurrentUser, db: DbSession) -> None:
    await _limit("reauth", f"user:{auth.user.id}")
    if not verify_password(auth.user.password_hash, body.password):
        await audit.record(
            db,
            action="auth.reauth_failed",
            resource_type="user",
            resource_id=auth.user.id,
            actor_user_id=auth.user.id,
        )
        await db.commit()
        raise ProblemError(
            401, "invalid_credentials", "Password incorrect", "The password is incorrect."
        )
    auth.session.reauth_at = datetime.now(UTC)


@router.post("/auth/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(body: ForgotPasswordIn, db: DbSession) -> None:
    await _limit("forgot", f"email:{body.email}")
    await service.request_password_reset(db, body.email)


@router.post("/auth/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: ResetPasswordIn, db: DbSession) -> None:
    await _limit("reset")
    await service.reset_password(db, body.token, body.password)


@router.get("/auth/invitations/{token}", response_model=InvitationInfoOut)
async def get_invitation(token: str, db: DbSession) -> InvitationInfoOut:
    await _limit("invitation", limit=INVITATION_LIMIT)
    invitation = await service.lookup_invitation(db, token)
    existing = await service.get_user_by_email(db, invitation.email)
    return InvitationInfoOut(
        organization_name=invitation.organization_name,
        email=invitation.email,
        role=invitation.role,
        account_exists=existing is not None,
    )


@router.post("/auth/invitations/{token}/accept", response_model=MeOut | TwoFactorChallengeOut)
async def accept_invitation(
    token: str, body: AcceptInvitationIn, response: Response, db: DbSession
) -> MeOut | TwoFactorChallengeOut:
    await _limit("invitation", limit=INVITATION_LIMIT)
    user = await service.accept_invitation(db, token, body.full_name, body.password)
    return await _sign_in(db, user, response)


@router.get("/me", response_model=MeOut)
async def me(auth: CurrentUser, db: DbSession) -> MeOut:
    return await service.build_me(db, auth.user)


@router.patch("/me", response_model=MeOut)
async def update_me(body: UpdateMeIn, auth: CurrentUser, db: DbSession) -> MeOut:
    before = {"full_name": auth.user.full_name, "locale": auth.user.locale}
    if body.full_name is not None:
        auth.user.full_name = body.full_name.strip()
    if body.locale is not None:
        auth.user.locale = body.locale
    after = {"full_name": auth.user.full_name, "locale": auth.user.locale}
    if changes := audit.diff(before, after):
        await audit.record(
            db,
            action="user.updated",
            resource_type="user",
            resource_id=auth.user.id,
            actor_user_id=auth.user.id,
            changes=changes,
        )
    return await service.build_me(db, auth.user)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: ChangePasswordIn, auth: CurrentUser, db: DbSession) -> None:
    await _limit("password", f"user:{auth.user.id}")
    if not verify_password(auth.user.password_hash, body.current_password):
        raise ProblemError(
            400,
            "invalid_current_password",
            "Current password incorrect",
            "The current password is incorrect.",
        )
    auth.user.password_hash = hash_password(body.new_password)
    auth.session.reauth_at = datetime.now(UTC)
    await service.revoke_sessions(db, auth.user.id, keep=auth.session.id)
    await audit.record(
        db,
        action="user.password_changed",
        resource_type="user",
        resource_id=auth.user.id,
        actor_user_id=auth.user.id,
        changes={"password": {"changed": True}},
    )
