"""Email notifications: per-user preferences and the messages sent on changes.

Privacy defaults: emails name what happened and link into the platform, but never copy
comment text, amounts or notes into the inbox. Every message type can be switched off.
"""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.authz.deps import OrgContext, ProjectContext
from app.core.config import get_settings
from app.notifications import mailer
from app.notifications.models import NotificationPreference
from app.notifications.schemas import PreferencesIn, PreferencesOut
from app.organizations.models import Membership, MembershipStatus, OrgRole
from app.projects.models import ProjectMember, ProjectRole

Kind = Literal["task_assigned", "comments", "documents", "daily_digest"]
DEFAULTS = PreferencesOut(task_assigned=True, comments=True, documents=True, daily_digest=True)


# --- Preferences --------------------------------------------------------------------------


async def _row(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> NotificationPreference | None:
    return (
        await db.execute(
            select(NotificationPreference).where(
                NotificationPreference.organization_id == org_id,
                NotificationPreference.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


def _out(row: NotificationPreference | None) -> PreferencesOut:
    if row is None:
        return DEFAULTS
    return PreferencesOut(
        task_assigned=row.task_assigned,
        comments=row.comments,
        documents=row.documents,
        daily_digest=row.daily_digest,
    )


async def get_preferences(db: AsyncSession, ctx: OrgContext) -> PreferencesOut:
    return _out(await _row(db, ctx.organization_id, ctx.user.id))


async def update_preferences(
    db: AsyncSession, ctx: OrgContext, body: PreferencesIn
) -> PreferencesOut:
    row = await _row(db, ctx.organization_id, ctx.user.id)
    if row is None:
        row = NotificationPreference(
            organization_id=ctx.organization_id, user_id=ctx.user.id, **DEFAULTS.model_dump()
        )
        db.add(row)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(row, key, value)
    await db.flush()
    return _out(row)


async def wants(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, kind: Kind) -> bool:
    return bool(getattr(_out(await _row(db, org_id, user_id)), kind))


# --- Recipients and links -----------------------------------------------------------------


@dataclass
class Recipient:
    user_id: uuid.UUID
    email: str
    is_client: bool


def settings_link(is_client: bool) -> str:
    base = get_settings().app_base_url
    return f"{base}/portal/notifications" if is_client else f"{base}/app/notifications"


def wedding_link(project_id: uuid.UUID, section: str, is_client: bool, query: str = "") -> str:
    base = get_settings().app_base_url
    portal_section = {"tasks": "tasks", "documents": "files", "calendar": ""}.get(section, "")
    if is_client:
        return f"{base}/portal/{portal_section}".rstrip("/")
    return f"{base}/app/weddings/{project_id}/{section}{query}"


async def _recipients(db: AsyncSession, membership_ids: list[uuid.UUID]) -> list[Recipient]:
    if not membership_ids:
        return []
    rows = await db.execute(
        select(User.id, User.email, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.id.in_(membership_ids), Membership.status == MembershipStatus.ACTIVE)
    )
    return [Recipient(uid, email, role == OrgRole.CLIENT) for uid, email, role in rows.all()]


async def _project_members(
    db: AsyncSession, project_id: uuid.UUID, roles: set[ProjectRole]
) -> list[uuid.UUID]:
    return list(
        (
            await db.execute(
                select(ProjectMember.membership_id).where(
                    ProjectMember.project_id == project_id, ProjectMember.project_role.in_(roles)
                )
            )
        ).scalars()
    )


async def _send(
    db: AsyncSession, ctx: ProjectContext, recipients: list[Recipient], kind: Kind, build: object
) -> None:
    seen: set[uuid.UUID] = set()
    for r in recipients:
        if r.user_id == ctx.user.id or r.user_id in seen:
            continue  # nobody is notified about their own actions
        seen.add(r.user_id)
        if await wants(db, ctx.organization_id, r.user_id, kind):
            await mailer.queue_email(build(r))  # type: ignore[operator]


def _actor(ctx: ProjectContext) -> str:
    return ctx.user.full_name or "Someone"


# --- Events -------------------------------------------------------------------------------


async def task_assigned(
    db: AsyncSession, ctx: ProjectContext, task_id: uuid.UUID, title: str, membership_id: uuid.UUID
) -> None:
    recipients = await _recipients(db, [membership_id])
    await _send(
        db,
        ctx,
        recipients,
        "task_assigned",
        lambda r: mailer.task_assigned_email(
            r.email,
            _actor(ctx),
            title,
            ctx.project.title,
            wedding_link(ctx.project.id, "tasks", r.is_client, f"?task={task_id}"),
            settings_link(r.is_client),
        ),
    )


async def commented(
    db: AsyncSession,
    ctx: ProjectContext,
    *,
    task_id: uuid.UUID,
    title: str,
    assignee_membership_id: uuid.UUID | None,
    assignee_type: str,
    shared: bool,
) -> None:
    """A comment on a task reaches its assignee; couple comments also reach the wedding leads.

    Comments visible to the couple on tasks for the couple also reach the couple.
    """
    ids = [assignee_membership_id] if assignee_membership_id else []
    if ctx.project_role == ProjectRole.CLIENT:
        ids += await _project_members(db, ctx.project.id, {ProjectRole.LEAD})
    elif shared and assignee_type == "client":
        ids += await _project_members(db, ctx.project.id, {ProjectRole.CLIENT})
    await _send(
        db,
        ctx,
        await _recipients(db, ids),
        "comments",
        lambda r: mailer.comment_email(
            r.email,
            _actor(ctx),
            title,
            ctx.project.title,
            wedding_link(ctx.project.id, "tasks", r.is_client, f"?task={task_id}"),
            settings_link(r.is_client),
        ),
    )


async def document_shared(db: AsyncSession, ctx: ProjectContext, title: str) -> None:
    """A document shared with the couple reaches the couple; one from the couple, the leads."""
    if ctx.project_role == ProjectRole.CLIENT:
        roles = {ProjectRole.LEAD}
    else:
        roles = {ProjectRole.CLIENT}
    ids = await _project_members(db, ctx.project.id, roles)
    await _send(
        db,
        ctx,
        await _recipients(db, ids),
        "documents",
        lambda r: mailer.document_email(
            r.email,
            _actor(ctx),
            title,
            ctx.project.title,
            wedding_link(ctx.project.id, "documents", r.is_client),
            settings_link(r.is_client),
        ),
    )
