"""Authentication: login, sessions, password reset and invitation acceptance."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.models import PasswordResetToken, User, UserSession
from app.auth.schemas import MembershipOut, MeOut
from app.core.config import get_settings
from app.core.context import current_request
from app.core.errors import ProblemError
from app.core.security import (
    MIN_PASSWORD_LENGTH,
    hash_password,
    hash_token,
    needs_rehash,
    new_token,
    verify_password,
)
from app.db.tenant import set_tenant_context
from app.notifications.mailer import password_reset_email, queue_email
from app.organizations.models import (
    Invitation,
    Membership,
    MembershipStatus,
    Organization,
    OrganizationStatus,
    OrgRole,
)

INVALID_CREDENTIALS = ProblemError(
    401, "invalid_credentials", "Sign-in failed", "The email or password is incorrect."
)
INVALID_TOKEN = ProblemError(
    400, "invalid_token", "Link not valid", "This link is invalid or has expired."
)
INVITATION_INVALID = ProblemError(
    404,
    "invitation_invalid",
    "Invitation not valid",
    "This invitation is invalid, was already used or has expired.",
)


def _now() -> datetime:
    return datetime.now(UTC)


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return (await db.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()


# --- Sessions ---------------------------------------------------------------------------


async def start_session(
    db: AsyncSession, user: User, response: Response, *, mfa_pending: bool = False
) -> UserSession:
    settings = get_settings()
    token = new_token()
    info = current_request()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        ip=info.ip if info else None,
        user_agent=info.user_agent if info else None,
        expires_at=_now() + timedelta(hours=settings.session_lifetime_hours),
        # Signing in counts as a fresh password confirmation, once it is complete.
        reauth_at=None if mfa_pending else _now(),
        mfa_pending=mfa_pending,
    )
    db.add(session)
    await db.flush()

    max_age = settings.session_lifetime_hours * 3600
    common = {"secure": settings.cookie_secure, "samesite": "lax", "path": "/", "max_age": max_age}
    response.set_cookie(settings.session_cookie_name, token, httponly=True, **common)  # type: ignore[arg-type]
    response.set_cookie(settings.csrf_cookie_name, new_token(), httponly=False, **common)  # type: ignore[arg-type]
    return session


def clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    for name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(name, path="/", secure=settings.cookie_secure, samesite="lax")


async def revoke_sessions(
    db: AsyncSession, user_id: uuid.UUID, *, keep: uuid.UUID | None = None
) -> None:
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    if keep is not None:
        stmt = stmt.where(UserSession.id != keep)
    await db.execute(stmt)


# --- Login ------------------------------------------------------------------------------


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    """Return the user or raise INVALID_CREDENTIALS; failures are audited and committed."""
    settings = get_settings()
    user = await get_user_by_email(db, email)
    now = _now()

    if user is not None and user.deleted_at is not None:
        user = None
    locked = user is not None and user.locked_until is not None and user.locked_until > now
    valid = verify_password(user.password_hash if user else None, password)

    if user is None or locked or not valid:
        if user is not None and not locked:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_login_count = 0
        await audit.record(
            db,
            action="auth.login_blocked" if locked else "auth.login_failed",
            resource_type="user",
            resource_id=user.id if user else None,
            actor_user_id=None,
            actor_type="system",
        )
        await db.commit()  # keep the counter and audit entry although the request fails
        raise INVALID_CREDENTIALS

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    await _set_user_context(db, user.id)
    await audit.record(
        db,
        action="auth.login_succeeded",
        resource_type="user",
        resource_id=user.id,
        actor_user_id=user.id,
    )
    return user


async def _set_user_context(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user_id)})


async def build_me(db: AsyncSession, user: User) -> MeOut:
    await _set_user_context(db, user.id)
    rows = (
        await db.execute(
            select(Membership, Organization)
            .join(Organization, Organization.id == Membership.organization_id)
            .where(
                Membership.user_id == user.id,
                Membership.status == MembershipStatus.ACTIVE,
                Organization.status == OrganizationStatus.ACTIVE,
            )
            .order_by(Organization.name)
        )
    ).all()
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        locale=user.locale,
        two_factor_enabled=user.two_factor_enabled,
        is_platform_admin=user.is_platform_admin,
        memberships=[
            MembershipOut(
                organization_id=org.id,
                organization_name=org.name,
                role=m.role,
                accent_color=org.accent_color,
            )
            for m, org in rows
        ],
    )


# --- Password reset ---------------------------------------------------------------------


async def request_password_reset(db: AsyncSession, email: str) -> None:
    user = await get_user_by_email(db, email)
    if user is None:
        return  # same response either way: never reveal whether an account exists
    settings = get_settings()
    token = new_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=_now() + timedelta(minutes=settings.password_reset_lifetime_minutes),
        )
    )
    await audit.record(
        db,
        action="auth.password_reset_requested",
        resource_type="user",
        resource_id=user.id,
        actor_type="system",
    )
    link = f"{settings.app_base_url}/reset-password?token={token}"
    await queue_email(password_reset_email(user.email, link))


async def reset_password(db: AsyncSession, token: str, password: str) -> None:
    now = _now()
    reset = (
        await db.execute(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == hash_token(token))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if reset is None or reset.used_at is not None or reset.expires_at <= now:
        raise INVALID_TOKEN

    user = await db.get(User, reset.user_id)
    assert user is not None
    user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    reset.used_at = now
    # Invalidate any other outstanding reset links for this user.
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    await revoke_sessions(db, user.id)
    await audit.record(
        db,
        action="auth.password_reset",
        resource_type="user",
        resource_id=user.id,
        actor_user_id=user.id,
    )


# --- Invitations ------------------------------------------------------------------------


@dataclass
class InvitationLookup:
    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    email: str
    role: str
    project_id: uuid.UUID | None


async def lookup_invitation(db: AsyncSession, token: str) -> InvitationLookup:
    row = (
        (
            await db.execute(
                text("SELECT * FROM app_invitation_by_token(:h)"), {"h": hash_token(token)}
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        row is None
        or row["accepted_at"] is not None
        or row["revoked_at"] is not None
        or row["expires_at"] <= _now()
    ):
        raise INVITATION_INVALID
    return InvitationLookup(
        id=row["id"],
        organization_id=row["organization_id"],
        organization_name=row["organization_name"],
        email=row["email"],
        role=row["role"],
        project_id=row["project_id"],
    )


async def accept_invitation(
    db: AsyncSession, token: str, full_name: str | None, password: str
) -> User:
    invitation = await lookup_invitation(db, token)
    user = await get_user_by_email(db, invitation.email)
    now = _now()

    if user is not None:
        if not verify_password(user.password_hash, password):
            raise INVALID_CREDENTIALS
    else:
        if not full_name:
            raise ProblemError(
                422,
                "validation_failed",
                "Some fields are invalid",
                errors=[{"field": "full_name", "code": "missing", "message": "Name is required"}],
            )
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ProblemError(
                422,
                "validation_failed",
                "Some fields are invalid",
                errors=[
                    {
                        "field": "password",
                        "code": "string_too_short",
                        "message": f"Use at least {MIN_PASSWORD_LENGTH} characters",
                    }
                ],
            )
        user = User(
            email=invitation.email,
            password_hash=hash_password(password),
            full_name=full_name.strip(),
            email_verified_at=now,
        )
        db.add(user)
        await db.flush()

    # The invitation token authorizes exactly the writes below (membership, wedding access,
    # contact link), so they run with an administrative tenant context.
    await set_tenant_context(
        db, organization_id=invitation.organization_id, user_id=user.id, role="org_admin"
    )
    row = await db.get(Invitation, invitation.id, with_for_update=True)
    if row is None or row.accepted_at is not None or row.revoked_at is not None:
        raise INVITATION_INVALID

    existing = (
        await db.execute(
            select(Membership).where(
                Membership.organization_id == invitation.organization_id,
                Membership.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    is_couple = invitation.project_id is not None
    if existing is not None and existing.status == MembershipStatus.ACTIVE:
        if not is_couple or existing.role != OrgRole.CLIENT:
            raise ProblemError(
                409,
                "already_member",
                "Already a member",
                "You already belong to this organization.",
            )
        membership = existing
    elif existing is not None:
        existing.status = MembershipStatus.ACTIVE
        existing.role = invitation.role
        membership = existing
    else:
        membership = Membership(
            organization_id=invitation.organization_id,
            user_id=user.id,
            role=invitation.role,
            invited_by=row.invited_by,
        )
        db.add(membership)
    await db.flush()

    if is_couple:
        assert invitation.project_id is not None
        await _grant_wedding_access(db, invitation, membership, user)

    row.accepted_at = now
    user.email_verified_at = user.email_verified_at or now
    await db.flush()

    await audit.record(
        db,
        action="invitation.accepted",
        resource_type="invitation",
        resource_id=row.id,
        organization_id=invitation.organization_id,
        actor_user_id=user.id,
        changes={"role": {"new": invitation.role}},
    )
    return user


async def _grant_wedding_access(
    db: AsyncSession, invitation: InvitationLookup, membership: Membership, user: User
) -> None:
    from app.clients.models import ClientContact
    from app.projects.models import Project, ProjectMember, ProjectRole

    project = await db.get(Project, invitation.project_id)
    if project is None or project.deleted_at is not None:
        raise INVITATION_INVALID
    already = (
        await db.execute(
            select(ProjectMember.id).where(
                ProjectMember.project_id == project.id,
                ProjectMember.membership_id == membership.id,
            )
        )
    ).scalar_one_or_none()
    if already is None:
        db.add(
            ProjectMember(
                organization_id=invitation.organization_id,
                project_id=project.id,
                membership_id=membership.id,
                project_role=ProjectRole.CLIENT,
            )
        )
    contacts = (
        await db.execute(
            select(ClientContact).where(
                ClientContact.client_id == project.client_id,
                func.lower(ClientContact.email) == user.email,
            )
        )
    ).scalars()
    for contact in contacts:
        contact.user_id = user.id
