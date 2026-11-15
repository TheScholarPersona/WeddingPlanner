"""The daily email digest: what is due or scheduled today and tomorrow, per person.

Runs hourly in the worker and sends to organizations where it is now DIGEST_HOUR local time.
Each person's digest is built with their own tenant context, so it only contains what they
could open in the app. notification_log makes sure a digest goes out once per day.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.config import get_settings
from app.core.ids import uuid7
from app.db.session import get_sessionmaker
from app.db.tenant import set_tenant_context
from app.events import service as events
from app.notifications import mailer
from app.notifications.models import NotificationLog
from app.notifications.service import settings_link, wants
from app.organizations.models import Membership, MembershipStatus, Organization, OrgRole
from app.tasks.models import Task, TaskStatus

logger = logging.getLogger(__name__)
NIL = uuid.UUID(int=0)


def _label(day: date, today: date) -> str:
    if day == today:
        return "Today"
    if day == today + timedelta(days=1):
        return "Tomorrow"
    return day.strftime("%a %d %b")


@dataclass(frozen=True)
class _Member:
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    email: str


async def _lines(db: AsyncSession, member: _Member, today: date, tz: ZoneInfo) -> list[str]:
    is_client = member.role == OrgRole.CLIENT
    viewer = events.Viewer(member.organization_id, member.id, is_client)
    items = await events.collect(
        db, viewer, today, today + timedelta(days=1), mine=True, payments=False
    )
    lines: list[str] = []
    for item in items:
        if item.kind == "task" and (not item.assigned_to_me or item.status == TaskStatus.DONE):
            continue
        when = _label(item.date, today)
        if item.kind == "event" and not item.all_day and item.starts_at:
            when += " " + item.starts_at.astimezone(tz).strftime("%H:%M")
        what = {"wedding": "Wedding day: ", "task": "Due: ", "event": ""}.get(item.kind, "")
        where = f" · {item.project_title}" if not is_client and item.kind != "wedding" else ""
        lines.append(f"• {when}: {what}{item.title}{where}")

    overdue_q = select(Task.id).where(
        Task.deleted_at.is_(None),
        Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
        Task.due_date < today,
    )
    overdue_q = (
        overdue_q.where(Task.assignee_type == "client")
        if is_client
        else overdue_q.where(Task.assignee_membership_id == member.id)
    )
    overdue = len((await db.execute(overdue_q)).all())
    if overdue:
        lines.append(f"• {overdue} overdue task{'s' if overdue != 1 else ''} waiting for you")
    return lines


async def digest_for_organization(organization_id: uuid.UUID, today: date) -> int:
    """Send today's digests for one organization; returns how many emails were queued."""
    sent = 0
    async with get_sessionmaker()() as db:
        await set_tenant_context(db, organization_id=organization_id, user_id=NIL, role="org_admin")
        org = await db.get(Organization, organization_id)
        if org is None:
            return 0
        tz = await events.org_timezone(db, organization_id)
        members = [
            _Member(m.id, m.organization_id, m.user_id, m.role, email)
            for m, email in (
                await db.execute(
                    select(Membership, User.email)
                    .join(User, User.id == Membership.user_id)
                    .where(
                        Membership.organization_id == organization_id,
                        Membership.status == MembershipStatus.ACTIVE,
                    )
                )
            ).all()
        ]
        org_name = org.name
        await db.commit()

        for member in members:
            await set_tenant_context(
                db,
                organization_id=organization_id,
                user_id=member.user_id,
                role=member.role,  # type: ignore[arg-type]
            )
            if not await wants(db, organization_id, member.user_id, "daily_digest"):
                await db.rollback()
                continue
            lines = await _lines(db, member, today, tz)
            if not lines:
                await db.rollback()
                continue
            inserted = (
                await db.execute(
                    insert(NotificationLog)
                    .values(
                        id=uuid7(),
                        organization_id=organization_id,
                        user_id=member.user_id,
                        kind="daily_digest",
                        ref=today.isoformat(),
                    )
                    .on_conflict_do_nothing()
                    .returning(NotificationLog.id)
                )
            ).scalar_one_or_none()
            if inserted is None:
                await db.rollback()
                continue  # already sent today
            await mailer.queue_email(
                mailer.digest_email(
                    member.email, org_name, lines, settings_link(member.role == OrgRole.CLIENT)
                )
            )
            await db.commit()
            sent += 1
    return sent


async def send_daily_digests(_: dict[str, Any], now: datetime | None = None) -> int:
    """Worker cron job (hourly)."""
    now = now or datetime.now(UTC)
    hour = get_settings().digest_hour
    async with get_sessionmaker()() as db:
        orgs = (await db.execute(text("SELECT id, timezone FROM app_active_organizations()"))).all()
    total = 0
    for org_id, timezone in orgs:
        try:
            local = now.astimezone(ZoneInfo(timezone))
        except (KeyError, ValueError):
            local = now.astimezone(ZoneInfo("Europe/Berlin"))
        if local.hour != hour:
            continue
        try:
            total += await digest_for_organization(org_id, local.date())
        except Exception:
            logger.exception("daily digest failed", extra={"organization_id": str(org_id)})
    return total
