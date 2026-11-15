from datetime import UTC, datetime

from fastapi import APIRouter, Response, status

from app.audit import service as audit
from app.auth import service
from app.auth.schemas import (
    AcceptInvitationIn,
    ChangePasswordIn,
    ForgotPasswordIn,
    InvitationInfoOut,
    LoginIn,
    MeOut,
    ReauthIn,
    ResetPasswordIn,
    UpdateMeIn,
)
from app.authz.deps import CurrentUser, DbSession
from app.core import ratelimit
from app.core.config import get_settings
from app.core.context import current_request
from app.core.errors import ProblemError
from app.core.security import hash_password, verify_password

router = APIRouter(tags=["auth"])

# Invitation tokens carry 256 bits of entropy; the limit only dampens scripted probing.
INVITATION_LIMIT = 30


def _client_key() -> str:
    info = current_request()
    return (info.ip if info and info.ip else "unknown")[:64]


async def _limit(scope: str, *extra: str, limit: int | None = None) -> None:
    limit = limit or get_settings().login_rate_limit_per_minute
    keys = [f"{scope}:ip:{_client_key()}", *(f"{scope}:{e}" for e in extra)]
    await ratelimit.enforce(keys, limit)


@router.post("/auth/login", response_model=MeOut)
async def login(body: LoginIn, response: Response, db: DbSession) -> MeOut:
    await _limit("login", f"email:{body.email}")
    user = await service.authenticate(db, body.email, body.password)
    await service.start_session(db, user, response)
    return await service.build_me(db, user)


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


@router.post("/auth/invitations/{token}/accept", response_model=MeOut)
async def accept_invitation(
    token: str, body: AcceptInvitationIn, response: Response, db: DbSession
) -> MeOut:
    await _limit("invitation", limit=INVITATION_LIMIT)
    user = await service.accept_invitation(db, token, body.full_name, body.password)
    await service.start_session(db, user, response)
    return await service.build_me(db, user)


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
