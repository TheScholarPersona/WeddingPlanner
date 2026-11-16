"""Organizations, team members and invitations. All queries run inside the tenant context."""

import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.models import User
from app.authz.deps import OrgContext, not_found
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.ids import uuid7
from app.core.security import hash_token, new_token
from app.db.tenant import set_tenant_context
from app.notifications.mailer import invitation_email, queue_email
from app.organizations.models import (
    Invitation,
    Membership,
    MembershipStatus,
    Organization,
    OrgRole,
)
from app.organizations.schemas import (
    InvitationIn,
    InvitationOut,
    MemberOut,
    MemberUpdateIn,
    OrganizationUpdateIn,
)
from app.templates.service import create_default_template


def _now() -> datetime:
    return datetime.now(UTC)


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return (slug or "organization")[:60]


# --- Organization -----------------------------------------------------------------------


async def get_organization(db: AsyncSession, ctx: OrgContext) -> Organization:
    org = await db.get(Organization, ctx.organization_id)
    if org is None:
        raise not_found()
    return org


async def update_organization(
    db: AsyncSession, ctx: OrgContext, body: OrganizationUpdateIn
) -> Organization:
    org = await get_organization(db, ctx)
    fields = body.model_dump(exclude_unset=True)
    if fields.get("require_2fa") and not ctx.user.two_factor_enabled:
        raise ProblemError(
            409,
            "enable_own_2fa_first",
            "Turn on your own two-factor authentication first",
            "Otherwise you would lock yourself out.",
        )
    before = {k: getattr(org, k) for k in fields}
    for key, value in fields.items():
        if value is not None:
            setattr(org, key, value)
    if changes := audit.diff(before, {k: getattr(org, k) for k in fields}):
        await audit.record(
            db,
            action="organization.updated",
            resource_type="organization",
            resource_id=org.id,
            organization_id=org.id,
            actor_user_id=ctx.user.id,
            changes=changes,
        )
    await db.flush()
    return org


async def create_organization(
    db: AsyncSession, *, name: str, admin_email: str
) -> tuple[Organization, str]:
    """Create an organization and invite its first admin. Returns (org, invitation link).

    Used by the CLI; organizations are activated manually during the pilot.
    """
    org_id = uuid7()
    system_user = uuid.UUID(int=0)
    await set_tenant_context(db, organization_id=org_id, user_id=system_user, role="org_admin")
    # Other tenants' slugs are invisible under RLS, so make the slug unique by construction.
    slug = f"{slugify(name)[:53]}-{org_id.hex[-6:]}"

    org = Organization(id=org_id, name=name, slug=slug)
    db.add(org)
    await db.flush()
    await audit.record(
        db,
        action="organization.created",
        resource_type="organization",
        resource_id=org.id,
        organization_id=org.id,
        actor_type="system",
        changes={"name": {"new": name}},
    )
    await create_default_template(db, org.id)
    _, link = await _create_invitation(db, org, admin_email.lower(), OrgRole.ORG_ADMIN, None)
    return org, link


# --- Members ----------------------------------------------------------------------------


def _member_out(m: Membership, u: User, ctx: OrgContext) -> MemberOut:
    return MemberOut(
        id=m.id,
        user_id=u.id,
        full_name=u.full_name,
        email=u.email,
        role=m.role,
        status=m.status,
        is_you=u.id == ctx.user.id,
        created_at=m.created_at,
    )


async def list_members(db: AsyncSession, ctx: OrgContext) -> list[MemberOut]:
    stmt = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.organization_id)
        .order_by(User.full_name)
    )
    if ctx.role != OrgRole.ORG_ADMIN:
        # Team members see the team, not the client logins.
        stmt = stmt.where(
            Membership.role.in_([OrgRole.ORG_ADMIN, OrgRole.MEMBER]),
            Membership.status == MembershipStatus.ACTIVE,
        )
    return [_member_out(m, u, ctx) for m, u in (await db.execute(stmt)).all()]


async def update_member(
    db: AsyncSession, ctx: OrgContext, membership_id: uuid.UUID, body: MemberUpdateIn
) -> MemberOut:
    row = (
        await db.execute(
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.id == membership_id)
            .with_for_update(of=Membership)
        )
    ).one_or_none()
    if row is None:
        raise not_found()
    membership, user = row

    if membership.user_id == ctx.user.id:
        raise ProblemError(
            403,
            "cannot_change_self",
            "Not allowed",
            "Ask another organization admin to change your own role or status.",
        )
    if membership.role == OrgRole.CLIENT and body.role is not None:
        raise ProblemError(
            422, "client_role_fixed", "Not allowed", "Client logins are managed per wedding."
        )

    new_role = body.role or membership.role
    new_status = body.status or membership.status
    removes_admin = membership.role == OrgRole.ORG_ADMIN and (
        new_role != OrgRole.ORG_ADMIN or new_status != MembershipStatus.ACTIVE
    )
    if removes_admin:
        other_admins = (
            await db.execute(
                select(func.count())
                .select_from(Membership)
                .where(
                    Membership.organization_id == ctx.organization_id,
                    Membership.role == OrgRole.ORG_ADMIN,
                    Membership.status == MembershipStatus.ACTIVE,
                    Membership.id != membership.id,
                )
            )
        ).scalar_one()
        if other_admins == 0:
            raise ProblemError(
                409,
                "last_admin",
                "Not allowed",
                "An organization needs at least one active admin.",
            )

    before = {"role": membership.role, "status": membership.status}
    membership.role = new_role
    membership.status = new_status
    if changes := audit.diff(before, {"role": new_role, "status": new_status}):
        await audit.record(
            db,
            action="membership.updated",
            resource_type="membership",
            resource_id=membership.id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.user.id,
            changes=changes,
        )
    await db.flush()
    return _member_out(membership, user, ctx)


# --- Invitations ------------------------------------------------------------------------


async def _create_invitation(
    db: AsyncSession, org: Organization, email: str, role: OrgRole, inviter: User | None
) -> tuple[Invitation, str]:
    settings = get_settings()
    token = new_token()
    invitation = Invitation(
        organization_id=org.id,
        email=email,
        role=role,
        token_hash=hash_token(token),
        invited_by=inviter.id if inviter else None,
        expires_at=_now() + timedelta(days=settings.invitation_lifetime_days),
    )
    db.add(invitation)
    await db.flush()
    link = f"{settings.app_base_url}/invite/{token}"
    await queue_email(
        invitation_email(email, org.name, inviter.full_name if inviter else None, link)
    )
    await audit.record(
        db,
        action="invitation.created",
        resource_type="invitation",
        resource_id=invitation.id,
        organization_id=org.id,
        actor_user_id=inviter.id if inviter else None,
        actor_type="user" if inviter else "system",
        changes={"role": {"new": str(role)}},
    )
    return invitation, link


def _invitation_out(inv: Invitation, inviter_name: str | None) -> InvitationOut:
    return InvitationOut(
        id=inv.id,
        email=inv.email,
        role=inv.role,
        status="expired" if inv.expires_at <= _now() else "pending",
        invited_by_name=inviter_name,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
    )


async def list_invitations(db: AsyncSession, ctx: OrgContext) -> list[InvitationOut]:
    rows = (
        await db.execute(
            select(Invitation, User.full_name)
            .outerjoin(User, User.id == Invitation.invited_by)
            .where(
                Invitation.organization_id == ctx.organization_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.role != OrgRole.CLIENT,
            )
            .order_by(Invitation.created_at.desc())
        )
    ).all()
    return [_invitation_out(inv, name) for inv, name in rows]


async def invite(db: AsyncSession, ctx: OrgContext, body: InvitationIn) -> InvitationOut:
    already_member = (
        await db.execute(
            select(func.count())
            .select_from(Membership)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.organization_id == ctx.organization_id,
                Membership.status == MembershipStatus.ACTIVE,
                User.email == body.email,
            )
        )
    ).scalar_one()
    if already_member:
        raise ProblemError(
            409, "already_member", "Already a member", "This person is already on your team."
        )

    # A new invitation replaces any pending one for the same address.
    pending = (
        await db.execute(
            select(Invitation).where(
                Invitation.organization_id == ctx.organization_id,
                Invitation.email == body.email,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
        )
    ).scalars()
    for old in pending:
        old.revoked_at = _now()

    org = await get_organization(db, ctx)
    invitation, _ = await _create_invitation(db, org, body.email, OrgRole(body.role), ctx.user)
    return _invitation_out(invitation, ctx.user.full_name)


async def _pending_invitation(
    db: AsyncSession, ctx: OrgContext, invitation_id: uuid.UUID
) -> Invitation:
    invitation = await db.get(Invitation, invitation_id, with_for_update=True)
    if (
        invitation is None
        or invitation.organization_id != ctx.organization_id
        or invitation.accepted_at is not None
        or invitation.revoked_at is not None
    ):
        raise not_found()
    return invitation


async def resend_invitation(
    db: AsyncSession, ctx: OrgContext, invitation_id: uuid.UUID
) -> InvitationOut:
    old = await _pending_invitation(db, ctx, invitation_id)
    old.revoked_at = _now()
    org = await get_organization(db, ctx)
    invitation, _ = await _create_invitation(db, org, old.email, OrgRole(old.role), ctx.user)
    return _invitation_out(invitation, ctx.user.full_name)


async def revoke_invitation(db: AsyncSession, ctx: OrgContext, invitation_id: uuid.UUID) -> None:
    invitation = await _pending_invitation(db, ctx, invitation_id)
    invitation.revoked_at = _now()
    await audit.record(
        db,
        action="invitation.revoked",
        resource_type="invitation",
        resource_id=invitation.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
