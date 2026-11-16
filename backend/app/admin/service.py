"""Platform administration and support access.

Platform admins manage organizations (create, suspend) and see only names and member counts
across tenants. Looking into an organization needs a support grant from one of its admins:
time-limited, revocable, read-only (the transaction is switched to READ ONLY) and recorded in
the organization's own audit log.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import SupportAccessGrant
from app.admin.schemas import (
    AdminOrganizationCreatedOut,
    AdminOrganizationIn,
    AdminOrganizationOut,
    ResetTwoFactorIn,
    SupportAuditOut,
    SupportGrantIn,
    SupportGrantOut,
    SupportMemberOut,
    SupportViewOut,
    SupportWeddingOut,
)
from app.audit import service as audit
from app.audit.models import AuditLog
from app.auth import two_factor
from app.auth.models import User
from app.authz.deps import Authenticated, OrgContext, not_found
from app.core.errors import ProblemError
from app.db.tenant import set_tenant_context
from app.organizations.models import Membership
from app.organizations.service import create_organization
from app.projects.models import Project, ProjectMember


def _now() -> datetime:
    return datetime.now(UTC)


# --- Organizations ------------------------------------------------------------------------


async def list_organizations(db: AsyncSession) -> list[AdminOrganizationOut]:
    rows = (await db.execute(text("SELECT * FROM app_admin_organizations()"))).mappings()
    return [AdminOrganizationOut(**dict(r)) for r in rows]


async def _organization(db: AsyncSession, org_id: uuid.UUID) -> AdminOrganizationOut:
    for org in await list_organizations(db):
        if org.id == org_id:
            return org
    raise not_found()


async def _record(
    db: AsyncSession,
    admin: Authenticated,
    org_id: uuid.UUID,
    action: str,
    changes: dict[str, object] | None = None,
) -> None:
    """Writes to the organization's audit log, so its admins see what support did."""
    await set_tenant_context(db, organization_id=org_id, user_id=admin.user.id, role="support")
    await audit.record(
        db,
        action=action,
        resource_type="organization",
        resource_id=org_id,
        organization_id=org_id,
        actor_user_id=admin.user.id,
        actor_type="platform_admin",
        changes=changes,
    )


async def create(
    db: AsyncSession, admin: Authenticated, body: AdminOrganizationIn
) -> AdminOrganizationCreatedOut:
    org, link = await create_organization(db, name=body.name.strip(), admin_email=body.admin_email)
    await _record(db, admin, org.id, "admin.organization_created")
    await db.flush()
    return AdminOrganizationCreatedOut(
        organization=await _organization(db, org.id), invitation_link=link
    )


async def set_status(
    db: AsyncSession, admin: Authenticated, org_id: uuid.UUID, status: str
) -> AdminOrganizationOut:
    found = (
        await db.execute(
            text("SELECT app_admin_set_organization_status(:o, :s)"), {"o": org_id, "s": status}
        )
    ).scalar_one()
    if not found:
        raise not_found()
    await _record(
        db,
        admin,
        org_id,
        f"admin.organization_{'suspended' if status == 'suspended' else 'reactivated'}",
    )
    return await _organization(db, org_id)


# --- Support view -------------------------------------------------------------------------


async def _active_grant(db: AsyncSession, org_id: uuid.UUID) -> SupportAccessGrant | None:
    return (
        await db.execute(
            select(SupportAccessGrant)
            .where(
                SupportAccessGrant.organization_id == org_id,
                SupportAccessGrant.revoked_at.is_(None),
                SupportAccessGrant.expires_at > _now(),
            )
            .order_by(SupportAccessGrant.expires_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def support_view(db: AsyncSession, admin: Authenticated, org_id: uuid.UUID) -> SupportViewOut:
    organization = await _organization(db, org_id)
    await set_tenant_context(db, organization_id=org_id, user_id=admin.user.id, role="support")
    grant = await _active_grant(db, org_id)
    if grant is None:
        raise ProblemError(
            403,
            "no_support_access",
            "No support access",
            "An admin of this organization has to grant support access first.",
        )
    expires_at = grant.expires_at
    await _record(db, admin, org_id, "support.viewed")
    await db.flush()

    # From here on nothing can be written, whatever happens below.
    await db.execute(text("SET LOCAL transaction_read_only = on"))
    await set_tenant_context(db, organization_id=org_id, user_id=admin.user.id, role="org_admin")
    members = [
        SupportMemberOut(
            full_name=u.full_name,
            email=u.email,
            role=m.role,
            status=m.status,
            two_factor_enabled=u.two_factor_enabled,
            last_login_at=u.last_login_at,
        )
        for m, u in (
            await db.execute(
                select(Membership, User)
                .join(User, User.id == Membership.user_id)
                .where(Membership.organization_id == org_id)
                .order_by(Membership.role, User.full_name)
            )
        ).all()
    ]
    team = (
        select(ProjectMember.project_id, func.count().label("n"))
        .group_by(ProjectMember.project_id)
        .subquery()
    )
    weddings = [
        SupportWeddingOut(
            id=p.id, title=p.title, wedding_date=p.wedding_date, status=p.status, team=n or 0
        )
        for p, n in (
            await db.execute(
                select(Project, team.c.n)
                .outerjoin(team, team.c.project_id == Project.id)
                .where(Project.deleted_at.is_(None))
                .order_by(Project.wedding_date.asc().nulls_last())
            )
        ).all()
    ]
    entries = [
        SupportAuditOut(
            created_at=a.created_at,
            action=a.action,
            resource_type=a.resource_type,
            actor_name=name,
            actor_type=a.actor_type,
        )
        for a, name in (
            await db.execute(
                select(AuditLog, User.full_name)
                .outerjoin(User, User.id == AuditLog.actor_user_id)
                .where(AuditLog.organization_id == org_id)
                .order_by(AuditLog.created_at.desc())
                .limit(50)
            )
        ).all()
    ]
    return SupportViewOut(
        organization=organization,
        grant_expires_at=expires_at,
        members=members,
        weddings=weddings,
        audit=entries,
    )


async def reset_two_factor(db: AsyncSession, admin: Authenticated, body: ResetTwoFactorIn) -> None:
    """For a person who lost their phone and recovery codes; needs a support grant from one of
    their organizations and is recorded there."""
    user = (
        await db.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    if user is None or user.deleted_at is not None:
        raise not_found()
    if user.is_platform_admin:
        raise ProblemError(
            409,
            "not_allowed",
            "Not allowed",
            "Another platform administrator's two-factor setup cannot be reset here.",
        )
    # Memberships are only visible inside each organization's context, so look in each
    # organization that currently grants support access.
    granted = None
    for org in await list_organizations(db):
        await set_tenant_context(db, organization_id=org.id, user_id=admin.user.id, role="support")
        if await _active_grant(db, org.id) is None:
            continue
        member = (
            await db.execute(
                select(Membership.id).where(
                    Membership.organization_id == org.id, Membership.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if member is not None:
            granted = org.id
            break
    if granted is None:
        raise ProblemError(
            403,
            "no_support_access",
            "No support access",
            "An admin of this person's organization has to grant support access first.",
        )
    await two_factor.disable(db, user)
    await _record(
        db,
        admin,
        granted,
        "admin.two_factor_reset",
        {"user": {"new": user.email}, "reason": {"new": body.reason}},
    )


# --- Grants (organization side) -----------------------------------------------------------


def _grant_out(grant: SupportAccessGrant, name: str | None) -> SupportGrantOut:
    return SupportGrantOut(
        id=grant.id,
        granted_by_name=name,
        reason=grant.reason,
        created_at=grant.created_at,
        expires_at=grant.expires_at,
        revoked_at=grant.revoked_at,
        active=grant.revoked_at is None and grant.expires_at > _now(),
    )


async def list_grants(db: AsyncSession, ctx: OrgContext) -> list[SupportGrantOut]:
    rows = await db.execute(
        select(SupportAccessGrant, User.full_name)
        .outerjoin(User, User.id == SupportAccessGrant.granted_by)
        .order_by(SupportAccessGrant.created_at.desc())
        .limit(20)
    )
    return [_grant_out(g, name) for g, name in rows.all()]


async def grant(db: AsyncSession, ctx: OrgContext, body: SupportGrantIn) -> SupportGrantOut:
    await db.execute(
        update(SupportAccessGrant)
        .where(SupportAccessGrant.revoked_at.is_(None), SupportAccessGrant.expires_at > _now())
        .values(revoked_at=_now())
    )
    row = SupportAccessGrant(
        organization_id=ctx.organization_id,
        granted_by=ctx.user.id,
        reason=(body.reason or "").strip() or None,
        expires_at=_now() + timedelta(days=body.days),
    )
    db.add(row)
    await db.flush()
    await audit.record(
        db,
        action="support_access.granted",
        resource_type="support_access",
        resource_id=row.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"days": {"new": body.days}},
    )
    return _grant_out(row, ctx.user.full_name)


async def revoke(db: AsyncSession, ctx: OrgContext, grant_id: uuid.UUID) -> None:
    row = await db.get(SupportAccessGrant, grant_id)
    if row is None:
        raise not_found()
    if row.revoked_at is None:
        row.revoked_at = _now()
        await audit.record(
            db,
            action="support_access.revoked",
            resource_type="support_access",
            resource_id=row.id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.user.id,
        )
