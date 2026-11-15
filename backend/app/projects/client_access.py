"""Couple logins for a wedding: invite, list and revoke portal access."""

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.models import User
from app.authz.deps import ProjectContext, not_found
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.security import hash_token, new_token
from app.notifications.mailer import couple_invitation_email, queue_email
from app.organizations.models import (
    Invitation,
    Membership,
    MembershipStatus,
    Organization,
    OrgRole,
)
from app.projects.models import ProjectMember, ProjectRole


class CoupleInvitationIn(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()


class CoupleLoginOut(BaseModel):
    project_member_id: uuid.UUID
    full_name: str
    email: str
    last_login_at: datetime | None


class CoupleInvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    expires_at: datetime
    expired: bool


class ClientAccessOut(BaseModel):
    logins: list[CoupleLoginOut]
    invitations: list[CoupleInvitationOut]


def _now() -> datetime:
    return datetime.now(UTC)


async def get_access(db: AsyncSession, ctx: ProjectContext) -> ClientAccessOut:
    logins = await db.execute(
        select(ProjectMember.id, User.full_name, User.email, User.last_login_at)
        .join(Membership, Membership.id == ProjectMember.membership_id)
        .join(User, User.id == Membership.user_id)
        .where(
            ProjectMember.project_id == ctx.project.id,
            ProjectMember.project_role == ProjectRole.CLIENT,
            Membership.status == MembershipStatus.ACTIVE,
        )
        .order_by(User.full_name)
    )
    invitations = (
        await db.execute(
            select(Invitation)
            .where(
                Invitation.project_id == ctx.project.id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
            .order_by(Invitation.created_at.desc())
        )
    ).scalars()
    now = _now()
    return ClientAccessOut(
        logins=[
            CoupleLoginOut(project_member_id=pm, full_name=n, email=e, last_login_at=last)
            for pm, n, e, last in logins.all()
        ],
        invitations=[
            CoupleInvitationOut(
                id=i.id, email=i.email, expires_at=i.expires_at, expired=i.expires_at <= now
            )
            for i in invitations
        ],
    )


async def invite_couple(db: AsyncSession, ctx: ProjectContext, body: CoupleInvitationIn) -> None:
    team_member = (
        await db.execute(
            select(func.count())
            .select_from(Membership)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.organization_id == ctx.organization_id,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.role != OrgRole.CLIENT,
                User.email == body.email,
            )
        )
    ).scalar_one()
    if team_member:
        raise ProblemError(
            409,
            "team_member",
            "Already on your team",
            "Team members cannot be invited as the couple.",
        )
    for old in (
        await db.execute(
            select(Invitation).where(
                Invitation.project_id == ctx.project.id,
                Invitation.email == body.email,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
        )
    ).scalars():
        old.revoked_at = _now()

    settings = get_settings()
    token = new_token()
    invitation = Invitation(
        organization_id=ctx.organization_id,
        email=body.email,
        role=OrgRole.CLIENT,
        project_id=ctx.project.id,
        token_hash=hash_token(token),
        invited_by=ctx.user.id,
        expires_at=_now() + timedelta(days=settings.invitation_lifetime_days),
    )
    db.add(invitation)
    await db.flush()
    org = await db.get(Organization, ctx.organization_id)
    assert org is not None
    await queue_email(
        couple_invitation_email(
            body.email, org.name, ctx.project.title, f"{settings.app_base_url}/invite/{token}"
        )
    )
    await audit.record(
        db,
        action="couple.invited",
        resource_type="invitation",
        resource_id=invitation.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"project_id": {"new": str(ctx.project.id)}},
    )


async def revoke_invitation(
    db: AsyncSession, ctx: ProjectContext, invitation_id: uuid.UUID
) -> None:
    invitation = await db.get(Invitation, invitation_id)
    if (
        invitation is None
        or invitation.project_id != ctx.project.id
        or invitation.accepted_at is not None
        or invitation.revoked_at is not None
    ):
        raise not_found()
    invitation.revoked_at = _now()
    await audit.record(
        db,
        action="invitation.revoked",
        resource_type="invitation",
        resource_id=invitation.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )


async def revoke_login(db: AsyncSession, ctx: ProjectContext, project_member_id: uuid.UUID) -> None:
    member = await db.get(ProjectMember, project_member_id)
    if (
        member is None
        or member.project_id != ctx.project.id
        or member.project_role != ProjectRole.CLIENT
    ):
        raise not_found()
    membership_id = member.membership_id
    await db.delete(member)
    await db.flush()
    remaining = (
        await db.execute(
            select(func.count())
            .select_from(ProjectMember)
            .where(ProjectMember.membership_id == membership_id)
        )
    ).scalar_one()
    if remaining == 0:
        membership = await db.get(Membership, membership_id)
        if membership is not None:
            membership.status = MembershipStatus.DISABLED
    await audit.record(
        db,
        action="couple.access_revoked",
        resource_type="project_member",
        resource_id=project_member_id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
