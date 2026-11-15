import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.audit.models import AuditLog
from app.auth.models import User
from app.authz.deps import DbSession, OrgContext, require, require_recent_auth
from app.authz.permissions import Perm
from app.organizations import service
from app.organizations.schemas import (
    AuditEntryOut,
    AuditPageOut,
    InvitationIn,
    InvitationOut,
    MemberOut,
    MemberUpdateIn,
    OrganizationOut,
    OrganizationUpdateIn,
)

router = APIRouter(prefix="/orgs/{org_id}", tags=["organizations"])


def _org_out(org: object) -> OrganizationOut:
    return OrganizationOut.model_validate(org, from_attributes=True)


@router.get("", response_model=OrganizationOut)
async def get_organization(
    db: DbSession, ctx: OrgContext = require(Perm.ORG_READ)
) -> OrganizationOut:
    return _org_out(await service.get_organization(db, ctx))


@router.patch("", response_model=OrganizationOut)
async def update_organization(
    body: OrganizationUpdateIn, db: DbSession, ctx: OrgContext = require(Perm.ORG_UPDATE)
) -> OrganizationOut:
    return _org_out(await service.update_organization(db, ctx, body))


@router.get("/members", response_model=list[MemberOut])
async def list_members(
    db: DbSession, ctx: OrgContext = require(Perm.MEMBERS_READ)
) -> list[MemberOut]:
    return await service.list_members(db, ctx)


@router.patch("/members/{membership_id}", response_model=MemberOut)
async def update_member(
    membership_id: uuid.UUID,
    body: MemberUpdateIn,
    db: DbSession,
    ctx: OrgContext = require(Perm.MEMBERS_MANAGE),
) -> MemberOut:
    require_recent_auth(ctx)
    return await service.update_member(db, ctx, membership_id, body)


@router.get("/invitations", response_model=list[InvitationOut])
async def list_invitations(
    db: DbSession, ctx: OrgContext = require(Perm.INVITATIONS_MANAGE)
) -> list[InvitationOut]:
    return await service.list_invitations(db, ctx)


@router.post("/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    body: InvitationIn, db: DbSession, ctx: OrgContext = require(Perm.INVITATIONS_MANAGE)
) -> InvitationOut:
    return await service.invite(db, ctx, body)


@router.post("/invitations/{invitation_id}/resend", response_model=InvitationOut)
async def resend_invitation(
    invitation_id: uuid.UUID, db: DbSession, ctx: OrgContext = require(Perm.INVITATIONS_MANAGE)
) -> InvitationOut:
    return await service.resend_invitation(db, ctx, invitation_id)


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    invitation_id: uuid.UUID, db: DbSession, ctx: OrgContext = require(Perm.INVITATIONS_MANAGE)
) -> None:
    await service.revoke_invitation(db, ctx, invitation_id)


@router.get("/audit-log", response_model=AuditPageOut)
async def audit_log(
    db: DbSession,
    ctx: OrgContext = require(Perm.AUDIT_READ),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=80)] = None,
) -> AuditPageOut:
    # UUIDv7 ids are time-ordered, so the id doubles as a stable pagination cursor.
    stmt = (
        select(AuditLog, User.full_name)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(AuditLog.organization_id == ctx.organization_id)
        .order_by(AuditLog.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        stmt = stmt.where(AuditLog.id < cursor)
    if action:
        stmt = stmt.where(AuditLog.action.startswith(action, autoescape=True))
    rows = (await db.execute(stmt)).all()
    items = [
        AuditEntryOut(
            id=entry.id,
            created_at=entry.created_at,
            action=entry.action,
            actor_type=entry.actor_type,
            actor_name=name,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            changes=entry.changes,
            ip=entry.ip,
        )
        for entry, name in rows[:limit]
    ]
    return AuditPageOut(items=items, next_cursor=items[-1].id if len(rows) > limit else None)
