"""Data protection tools (GDPR): exports, erasure, account deletion and consents.

- Client export (Art. 15/20): everything the organization holds about a client, as a ZIP with
  `data.json` and the original document files.
- Client erasure (Art. 17): the client, all their weddings, files and couple access, for good.
  The audit log keeps that it happened, not the content.
- Personal export: what the platform holds about the signed-in person.
- Account deletion: the person's login is anonymized and removed from all organizations.
"""

import io
import json
import uuid
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.audit.models import AuditLog
from app.auth.models import RecoveryCode, User, UserSession
from app.authz.deps import OrgContext, ProjectContext, not_found
from app.budget.models import Budget, BudgetCategory, BudgetItem, Payment
from app.clients.models import Client, ClientContact
from app.core.errors import ProblemError
from app.db.base import Base
from app.db.tenant import set_tenant_context
from app.documents.models import Document, DocumentVersion
from app.documents.storage import get_storage
from app.events.models import CalendarFeed, Event
from app.notifications.models import NotificationPreference
from app.organizations.models import Membership, MembershipStatus, Organization, OrgRole
from app.privacy.models import CONSENT_TEXT_VERSION, Consent, ConsentKind
from app.privacy.schemas import ConsentOut, CoupleConsentsOut
from app.projects.models import Project, ProjectMember, ProjectRole, ProjectVendor
from app.tasks.models import ActivityEvent, Comment, Milestone, Task, TaskChecklistItem

EXPORT_FORMAT = 1
SKIP_COLUMNS = frozenset({"organization_id", "storage_key"})


def _now() -> datetime:
    return datetime.now(UTC)


def _value(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _row(obj: Base, skip: frozenset[str] = SKIP_COLUMNS) -> dict[str, Any]:
    return {c.key: _value(getattr(obj, c.key)) for c in obj.__table__.columns if c.key not in skip}


async def _rows(db: AsyncSession, model: type[Base], *where: Any) -> list[dict[str, Any]]:
    return [_row(o) for o in (await db.execute(select(model).where(*where))).scalars()]


async def _client(db: AsyncSession, client_id: uuid.UUID) -> Client:
    client = await db.get(Client, client_id)
    if client is None:
        raise not_found()
    return client


async def _couple_users(
    db: AsyncSession, project_ids: list[uuid.UUID]
) -> list[tuple[Membership, User]]:
    if not project_ids:
        return []
    rows = await db.execute(
        select(Membership, User)
        .join(ProjectMember, ProjectMember.membership_id == Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(
            ProjectMember.project_id.in_(project_ids),
            ProjectMember.project_role == ProjectRole.CLIENT,
        )
        .distinct()
    )
    return [(m, u) for m, u in rows.all()]


# --- Client export ------------------------------------------------------------------------


async def export_client(
    db: AsyncSession, ctx: OrgContext, client_id: uuid.UUID
) -> tuple[str, bytes]:
    """ZIP with data.json and the current files of all the client's documents."""
    client = await _client(db, client_id)
    projects = list(
        (await db.execute(select(Project).where(Project.client_id == client.id))).scalars()
    )
    ids = [p.id for p in projects]
    weddings: list[dict[str, Any]] = []
    for project in projects:
        weddings.append(
            {
                **_row(project),
                "milestones": await _rows(db, Milestone, Milestone.project_id == project.id),
                "tasks": await _rows(db, Task, Task.project_id == project.id),
                "checklists": await _rows(
                    db,
                    TaskChecklistItem,
                    TaskChecklistItem.task_id.in_(
                        select(Task.id).where(Task.project_id == project.id)
                    ),
                ),
                "comments": await _rows(db, Comment, Comment.project_id == project.id),
                "activity": await _rows(db, ActivityEvent, ActivityEvent.project_id == project.id),
                "vendors": await _rows(db, ProjectVendor, ProjectVendor.project_id == project.id),
                "budget": await _rows(db, Budget, Budget.project_id == project.id),
                "budget_categories": await _rows(
                    db, BudgetCategory, BudgetCategory.project_id == project.id
                ),
                "budget_items": await _rows(db, BudgetItem, BudgetItem.project_id == project.id),
                "payments": await _rows(db, Payment, Payment.project_id == project.id),
                "appointments": await _rows(db, Event, Event.project_id == project.id),
                "documents": await _rows(db, Document, Document.project_id == project.id),
                "document_versions": await _rows(
                    db, DocumentVersion, DocumentVersion.project_id == project.id
                ),
            }
        )
    couples = await _couple_users(db, ids)
    consents = (
        await _rows(
            db,
            Consent,
            Consent.organization_id == ctx.organization_id,
            Consent.user_id.in_([u.id for _, u in couples]),
        )
        if couples
        else []
    )
    data = {
        "format": EXPORT_FORMAT,
        "exported_at": _now().isoformat(),
        "exported_by": ctx.user.full_name,
        "client": _row(client),
        "contacts": await _rows(db, ClientContact, ClientContact.client_id == client.id),
        "portal_accounts": [
            {"email": u.email, "full_name": u.full_name, "status": m.status} for m, u in couples
        ],
        "consents": consents,
        "weddings": weddings,
    }

    buffer = io.BytesIO()
    storage = get_storage()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.json", json.dumps(data, ensure_ascii=False, indent=2))
        if ids:
            versions = (
                await db.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.project_id.in_(ids),
                        DocumentVersion.scan_status.in_(["clean", "not_scanned"]),
                    )
                )
            ).scalars()
            for v in versions:
                try:
                    content = await storage.get(v.storage_key)
                except Exception:  # noqa: S112 - a missing object must not stop the export
                    continue
                archive.writestr(f"files/{v.document_id}/v{v.number}-{v.filename}", content)
    await audit.record(
        db,
        action="privacy.client_exported",
        resource_type="client",
        resource_id=client.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
    safe = "".join(c if c.isalnum() else "-" for c in client.display_name).strip("-")[:40]
    return f"client-export-{safe or 'client'}-{_now():%Y%m%d}.zip", buffer.getvalue()


# --- Client erasure -----------------------------------------------------------------------


async def erase_client(
    db: AsyncSession, ctx: OrgContext, client_id: uuid.UUID, confirm: str
) -> dict[str, int]:
    client = await _client(db, client_id)
    if confirm.strip() != client.display_name.strip():
        raise ProblemError(
            422,
            "confirmation_mismatch",
            "Name does not match",
            "Type the client's name exactly to confirm.",
        )
    projects = list(
        (await db.execute(select(Project).where(Project.client_id == client.id))).scalars()
    )
    ids = [p.id for p in projects]
    keys: list[str] = []
    if ids:
        keys = list(
            (
                await db.execute(
                    select(DocumentVersion.storage_key).where(DocumentVersion.project_id.in_(ids))
                )
            ).scalars()
        )
    couples = await _couple_users(db, ids)

    # Documents point at their current version; clear that before the cascade.
    if ids:
        await db.execute(
            update(Document).where(Document.project_id.in_(ids)).values(current_version_id=None)
        )
        await db.execute(delete(Project).where(Project.id.in_(ids)))
    await db.execute(delete(Client).where(Client.id == client.id))

    # Couple logins that only existed for these weddings lose their access to the organization.
    removed_accounts = 0
    for membership, user in couples:
        other = (
            await db.execute(
                select(func.count())
                .select_from(ProjectMember)
                .where(ProjectMember.membership_id == membership.id)
            )
        ).scalar_one()
        if other == 0 and membership.role == OrgRole.CLIENT:
            await db.execute(
                delete(Consent).where(
                    Consent.organization_id == ctx.organization_id, Consent.user_id == user.id
                )
            )
            await db.execute(
                delete(NotificationPreference).where(
                    NotificationPreference.organization_id == ctx.organization_id,
                    NotificationPreference.user_id == user.id,
                )
            )
            await db.execute(
                delete(CalendarFeed).where(CalendarFeed.membership_id == membership.id)
            )
            await db.execute(delete(Membership).where(Membership.id == membership.id))
            removed_accounts += 1
    await db.flush()

    storage = get_storage()
    for key in keys:
        await storage.delete(key)
    summary = {"weddings": len(ids), "files": len(keys), "portal_accounts": removed_accounts}
    await audit.record(
        db,
        action="privacy.client_erased",
        resource_type="client",
        resource_id=client_id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={k: {"old": v} for k, v in summary.items()},
    )
    return summary


# --- Personal data ------------------------------------------------------------------------


async def export_me(db: AsyncSession, user: User) -> dict[str, Any]:
    memberships = list(
        (await db.execute(select(Membership).where(Membership.user_id == user.id))).scalars()
    )
    organizations: list[dict[str, Any]] = []
    for m in memberships:
        await set_tenant_context(
            db,
            organization_id=m.organization_id,
            user_id=user.id,
            role=m.role,  # type: ignore[arg-type]
        )
        org = await db.get(Organization, m.organization_id)
        organizations.append(
            {
                "organization": org.name if org else None,
                "role": m.role,
                "status": m.status,
                "member_since": _value(m.created_at),
                "notification_preferences": await _rows(
                    db,
                    NotificationPreference,
                    NotificationPreference.organization_id == m.organization_id,
                    NotificationPreference.user_id == user.id,
                ),
                "consents": await _rows(
                    db,
                    Consent,
                    Consent.organization_id == m.organization_id,
                    Consent.user_id == user.id,
                ),
                "comments_written": await _rows(db, Comment, Comment.author_user_id == user.id),
                "calendar_subscriptions": [
                    {"created_at": _value(f.created_at), "revoked_at": _value(f.revoked_at)}
                    for f in (
                        await db.execute(
                            select(CalendarFeed).where(CalendarFeed.user_id == user.id)
                        )
                    ).scalars()
                ],
            }
        )
    # Leave the last organization's context: the rest is about the person, not a tenant.
    await db.execute(
        text("SELECT set_config('app.org_id', '', true), set_config('app.role', '', true)")
    )
    sessions = [
        {
            "created_at": _value(s.created_at),
            "last_seen_at": _value(s.last_seen_at),
            "ip": s.ip,
            "user_agent": s.user_agent,
            "revoked_at": _value(s.revoked_at),
        }
        for s in (
            await db.execute(
                select(UserSession)
                .where(UserSession.user_id == user.id)
                .order_by(UserSession.created_at.desc())
            )
        ).scalars()
    ]
    activity = [
        {
            "at": _value(a.created_at),
            "action": a.action,
            "resource_type": a.resource_type,
            "ip": a.ip,
        }
        for a in (
            await db.execute(
                select(AuditLog)
                .where(AuditLog.actor_user_id == user.id)
                .order_by(AuditLog.created_at.desc())
                .limit(5000)
            )
        ).scalars()
    ]
    await audit.record(
        db,
        action="privacy.personal_data_exported",
        resource_type="user",
        resource_id=user.id,
        actor_user_id=user.id,
    )
    return {
        "format": EXPORT_FORMAT,
        "exported_at": _now().isoformat(),
        "account": {
            "email": user.email,
            "full_name": user.full_name,
            "locale": user.locale,
            "created_at": _value(user.created_at),
            "last_login_at": _value(user.last_login_at),
            "two_factor_enabled": user.two_factor_enabled,
        },
        "organizations": organizations,
        "sessions": sessions,
        "activity": activity,
    }


async def delete_account(db: AsyncSession, user: User) -> None:
    """Anonymizes the login and removes it from every organization.

    Refused while the person is the last active admin of an organization, which would otherwise
    be left without anyone who can manage it.
    """
    memberships = list(
        (
            await db.execute(
                select(Membership).where(
                    Membership.user_id == user.id, Membership.status == MembershipStatus.ACTIVE
                )
            )
        ).scalars()
    )
    for m in memberships:
        await set_tenant_context(
            db,
            organization_id=m.organization_id,
            user_id=user.id,
            role=m.role,  # type: ignore[arg-type]
        )
        if m.role == OrgRole.ORG_ADMIN:
            admins = (
                await db.execute(
                    select(func.count())
                    .select_from(Membership)
                    .where(
                        Membership.organization_id == m.organization_id,
                        Membership.role == OrgRole.ORG_ADMIN,
                        Membership.status == MembershipStatus.ACTIVE,
                    )
                )
            ).scalar_one()
            if admins <= 1:
                raise ProblemError(
                    409,
                    "last_admin",
                    "You are the last admin",
                    "Make someone else an admin of your organization first.",
                )
        for model in (NotificationPreference, Consent):
            await db.execute(
                delete(model).where(
                    model.organization_id == m.organization_id,
                    model.user_id == user.id,
                )
            )
        await db.execute(delete(CalendarFeed).where(CalendarFeed.membership_id == m.id))
        await audit.record(
            db,
            action="user.account_deleted",
            resource_type="user",
            resource_id=user.id,
            organization_id=m.organization_id,
            actor_user_id=user.id,
        )
        await db.execute(delete(Membership).where(Membership.id == m.id))

    await db.execute(
        update(ClientContact).where(ClientContact.user_id == user.id).values(user_id=None)
    )
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    user.email = f"deleted-{user.id}@deleted.invalid"
    user.full_name = "Deleted user"
    user.password_hash = "!deleted"  # noqa: S105 - matches no password
    user.totp_secret_enc = None
    user.totp_enabled_at = None
    user.is_platform_admin = False
    user.deleted_at = _now()
    await db.flush()


# --- Consents -----------------------------------------------------------------------------


async def my_consents(db: AsyncSession, ctx: ProjectContext) -> list[ConsentOut]:
    rows = {
        c.kind: c
        for c in (
            await db.execute(
                select(Consent).where(
                    Consent.organization_id == ctx.organization_id,
                    Consent.user_id == ctx.user.id,
                )
            )
        ).scalars()
    }
    return [
        ConsentOut(
            kind=kind,
            granted=rows[kind].granted if kind in rows else None,
            decided_at=rows[kind].decided_at if kind in rows else None,
            outdated=kind in rows and rows[kind].text_version < CONSENT_TEXT_VERSION,
        )
        for kind in ConsentKind
    ]


async def decide(
    db: AsyncSession, ctx: ProjectContext, kind: str, granted: bool
) -> list[ConsentOut]:
    row = (
        await db.execute(
            select(Consent).where(
                Consent.organization_id == ctx.organization_id,
                Consent.user_id == ctx.user.id,
                Consent.kind == kind,
            )
        )
    ).scalar_one_or_none()
    old = row.granted if row else None
    if row is None:
        row = Consent(
            organization_id=ctx.organization_id, user_id=ctx.user.id, kind=kind, granted=granted
        )
        db.add(row)
    row.granted = granted
    row.text_version = CONSENT_TEXT_VERSION
    row.decided_at = _now()
    await db.flush()
    await audit.record(
        db,
        action="consent.granted" if granted else "consent.withdrawn",
        resource_type="consent",
        resource_id=row.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"kind": {"new": kind}, "granted": {"old": old, "new": granted}},
    )
    return await my_consents(db, ctx)


async def couple_consents(db: AsyncSession, ctx: ProjectContext) -> list[CoupleConsentsOut]:
    couples = await _couple_users(db, [ctx.project.id])
    result: list[CoupleConsentsOut] = []
    for _, user in couples:
        rows = {
            c.kind: c
            for c in (
                await db.execute(
                    select(Consent).where(
                        Consent.organization_id == ctx.organization_id, Consent.user_id == user.id
                    )
                )
            ).scalars()
        }
        result.append(
            CoupleConsentsOut(
                full_name=user.full_name,
                consents=[
                    ConsentOut(
                        kind=kind,
                        granted=rows[kind].granted if kind in rows else None,
                        decided_at=rows[kind].decided_at if kind in rows else None,
                        outdated=kind in rows and rows[kind].text_version < CONSENT_TEXT_VERSION,
                    )
                    for kind in ConsentKind
                ],
            )
        )
    return result
