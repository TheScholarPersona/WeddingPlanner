"""Appointments, the combined calendar (events, task due dates, payments, wedding days) and
private iCal subscription feeds.

Everything is read under row-level security with the user's own role, so a calendar never
shows more than the user could open in the app; couples only see what is shared with them.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.models import User
from app.authz.deps import OrgContext, ProjectContext, not_found
from app.budget.models import BudgetItem, Payment
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.security import hash_token, new_token
from app.core.versioning import check_version
from app.db.tenant import set_tenant_context
from app.events import ics
from app.events.models import CalendarFeed, Event
from app.events.schemas import CalendarItemOut, EventIn, EventOut, FeedCreatedOut, FeedOut
from app.organizations.models import Organization
from app.projects.models import Project
from app.tasks.models import Task, TaskStatus
from app.tasks.service import record_activity

MAX_RANGE_DAYS = 120


def _now() -> datetime:
    return datetime.now(UTC)


async def org_timezone(db: AsyncSession, organization_id: uuid.UUID) -> ZoneInfo:
    org = await db.get(Organization, organization_id)
    try:
        return ZoneInfo(org.timezone if org else "Europe/Berlin")
    except (KeyError, ValueError):
        return ZoneInfo("Europe/Berlin")


# --- Events of a wedding ------------------------------------------------------------------


def _dates(event: Event, tz: ZoneInfo) -> tuple[date, date]:
    start = event.starts_at.astimezone(tz).date()
    if event.ends_at is None:
        return start, start
    end_local = event.ends_at.astimezone(tz)
    if event.all_day:
        return start, (end_local - timedelta(days=1)).date()  # stored end is exclusive
    return start, end_local.date()


def _event_out(event: Event, tz: ZoneInfo, creator: str | None) -> EventOut:
    start, end = _dates(event, tz)
    return EventOut(
        id=event.id,
        project_id=event.project_id,
        title=event.title,
        all_day=event.all_day,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        start_date=start,
        end_date=end,
        location=event.location,
        description=event.description,
        visibility=event.visibility,
        created_by_name=creator,
        version=event.version,
    )


def _apply(event: Event, body: EventIn, tz: ZoneInfo) -> None:
    event.title = body.title.strip()
    event.all_day = body.all_day
    if body.all_day:
        assert body.start_date is not None
        last = body.end_date or body.start_date
        event.starts_at = datetime.combine(body.start_date, time(), tz)
        event.ends_at = datetime.combine(last + timedelta(days=1), time(), tz)
    else:
        assert body.starts_at is not None
        event.starts_at = body.starts_at
        event.ends_at = body.ends_at
    event.location = (body.location or "").strip() or None
    event.description = (body.description or "").strip() or None
    event.visibility = body.visibility


async def list_events(db: AsyncSession, ctx: ProjectContext) -> list[EventOut]:
    tz = await org_timezone(db, ctx.organization_id)
    rows = await db.execute(
        select(Event, User.full_name)
        .outerjoin(User, User.id == Event.created_by)
        .where(Event.project_id == ctx.project.id)
        .order_by(Event.starts_at)
    )
    return [_event_out(e, tz, name) for e, name in rows.all()]


async def _event(db: AsyncSession, ctx: ProjectContext, event_id: uuid.UUID) -> Event:
    event = (
        await db.execute(
            select(Event).where(Event.id == event_id, Event.project_id == ctx.project.id)
        )
    ).scalar_one_or_none()
    if event is None:
        raise not_found()
    return event


async def _audit_visibility(
    db: AsyncSession, ctx: ProjectContext, event: Event, old: str | None
) -> None:
    if old == event.visibility or (old is None and event.visibility == "internal"):
        return
    await audit.record(
        db,
        action="event.shared_with_client" if event.visibility == "client" else "event.unshared",
        resource_type="event",
        resource_id=event.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"visibility": {"old": old, "new": event.visibility}},
    )


async def create_event(db: AsyncSession, ctx: ProjectContext, body: EventIn) -> EventOut:
    tz = await org_timezone(db, ctx.organization_id)
    event = Event(
        organization_id=ctx.organization_id, project_id=ctx.project.id, created_by=ctx.user.id
    )
    _apply(event, body, tz)
    db.add(event)
    await db.flush()
    await record_activity(
        db,
        ctx,
        verb="event.created",
        target_type="event",
        target_id=event.id,
        summary=event.title,
        visibility=event.visibility,
    )
    await _audit_visibility(db, ctx, event, None)
    return _event_out(event, tz, ctx.user.full_name)


async def update_event(
    db: AsyncSession, ctx: ProjectContext, event_id: uuid.UUID, body: EventIn, if_match: str | None
) -> EventOut:
    tz = await org_timezone(db, ctx.organization_id)
    event = await _event(db, ctx, event_id)
    check_version(event.version, if_match, "appointment")
    old_visibility = event.visibility
    _apply(event, body, tz)
    event.version += 1
    await db.flush()
    await _audit_visibility(db, ctx, event, old_visibility)
    creator = (await db.get(User, event.created_by)) if event.created_by else None
    return _event_out(event, tz, creator.full_name if creator else None)


async def delete_event(db: AsyncSession, ctx: ProjectContext, event_id: uuid.UUID) -> None:
    event = await _event(db, ctx, event_id)
    await db.delete(event)
    await db.flush()


# --- Combined calendar --------------------------------------------------------------------


@dataclass
class Viewer:
    organization_id: uuid.UUID
    membership_id: uuid.UUID
    is_client: bool


def check_range(start: date, end: date, limit: int = MAX_RANGE_DAYS) -> None:
    if end < start or (end - start).days > limit:
        raise ProblemError(
            422,
            "invalid_range",
            "Invalid date range",
            f"Choose a range of at most {limit} days.",
        )


async def collect(
    db: AsyncSession,
    viewer: Viewer,
    start: date,
    end: date,
    *,
    project_id: uuid.UUID | None = None,
    mine: bool = False,
    payments: bool = True,
) -> list[CalendarItemOut]:
    """Calendar items between start and end (inclusive), in the organization's time zone.

    `mine` limits tasks to the viewer's own (team: assigned to them; couple: tasks for the
    couple). Events, wedding days and payments are always included.
    """
    tz = await org_timezone(db, viewer.organization_id)
    projects_q = select(Project.id, Project.title, Project.wedding_date).where(
        Project.deleted_at.is_(None)
    )
    if project_id is not None:
        projects_q = projects_q.where(Project.id == project_id)
    projects = {pid: (title, wd) for pid, title, wd in (await db.execute(projects_q)).all()}
    if not projects:
        return []
    ids = list(projects)
    items: list[CalendarItemOut] = []

    for pid, (title, wedding_date) in projects.items():
        if wedding_date and start <= wedding_date <= end:
            items.append(
                CalendarItemOut(
                    kind="wedding",
                    id=pid,
                    title=title,
                    project_id=pid,
                    project_title=title,
                    date=wedding_date,
                    end_date=wedding_date,
                    all_day=True,
                    visibility="client",
                )
            )

    window_start = datetime.combine(start, time(), tz)
    window_end = datetime.combine(end + timedelta(days=1), time(), tz)
    events = await db.execute(
        select(Event).where(
            Event.project_id.in_(ids),
            Event.starts_at < window_end,
            Event.starts_at >= window_start - timedelta(days=31),
        )
    )
    for event in events.scalars():
        first, last = _dates(event, tz)
        if last < start:
            continue
        items.append(
            CalendarItemOut(
                kind="event",
                id=event.id,
                title=event.title,
                project_id=event.project_id,
                project_title=projects[event.project_id][0],
                date=first,
                end_date=last,
                all_day=event.all_day,
                starts_at=event.starts_at,
                ends_at=event.ends_at,
                location=event.location,
                visibility=event.visibility,
            )
        )

    tasks_q = select(Task).where(
        Task.project_id.in_(ids),
        Task.deleted_at.is_(None),
        Task.status != TaskStatus.CANCELLED,
        Task.due_date >= start,
        Task.due_date <= end,
    )
    if viewer.is_client:
        tasks_q = tasks_q.where(Task.assignee_type == "client")
    elif mine:
        tasks_q = tasks_q.where(Task.assignee_membership_id == viewer.membership_id)
    for task in (await db.execute(tasks_q)).scalars():
        assert task.due_date is not None
        items.append(
            CalendarItemOut(
                kind="task",
                id=task.id,
                title=task.title,
                project_id=task.project_id,
                project_title=projects[task.project_id][0],
                date=task.due_date,
                end_date=task.due_date,
                all_day=True,
                visibility=task.visibility,
                status=task.status,
                assigned_to_me=viewer.is_client
                or task.assignee_membership_id == viewer.membership_id,
            )
        )

    if payments:
        rows = await db.execute(
            select(Payment, BudgetItem.visibility)
            .join(BudgetItem, BudgetItem.id == Payment.budget_item_id)
            .where(
                Payment.project_id.in_(ids),
                Payment.paid_at.is_(None),
                Payment.due_date >= start,
                Payment.due_date <= end,
            )
        )
        for payment, visibility in rows.all():
            assert payment.due_date is not None
            items.append(
                CalendarItemOut(
                    kind="payment",
                    id=payment.id,
                    title=payment.label,
                    project_id=payment.project_id,
                    project_title=projects[payment.project_id][0],
                    date=payment.due_date,
                    end_date=payment.due_date,
                    all_day=True,
                    visibility=visibility,
                    amount_cents=payment.amount_cents,
                )
            )

    order = {"wedding": 0, "event": 1, "payment": 2, "task": 3}
    items.sort(
        key=lambda i: (
            i.date,
            not i.all_day if i.kind == "event" else False,
            i.starts_at or datetime.min.replace(tzinfo=UTC),
            order[i.kind],
            i.title,
        )
    )
    return items


# --- Subscription feeds -------------------------------------------------------------------


def feed_url(token: str) -> str:
    return f"{get_settings().app_base_url}/api/v1/calendar-feeds/{token}.ics"


async def _active_feed(db: AsyncSession, ctx: OrgContext) -> CalendarFeed | None:
    return (
        await db.execute(
            select(CalendarFeed).where(
                CalendarFeed.membership_id == ctx.membership.id,
                CalendarFeed.user_id == ctx.user.id,
                CalendarFeed.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def get_feed(db: AsyncSession, ctx: OrgContext) -> FeedOut:
    feed = await _active_feed(db, ctx)
    if feed is None:
        return FeedOut(active=False)
    return FeedOut(active=True, created_at=feed.created_at, last_used_at=feed.last_used_at)


async def revoke_feed(db: AsyncSession, ctx: OrgContext) -> None:
    await db.execute(
        update(CalendarFeed)
        .where(
            CalendarFeed.membership_id == ctx.membership.id,
            CalendarFeed.user_id == ctx.user.id,
            CalendarFeed.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
    await audit.record(
        db,
        action="calendar_feed.revoked",
        resource_type="calendar_feed",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )


async def create_feed(db: AsyncSession, ctx: OrgContext) -> FeedCreatedOut:
    """Creates a new secret feed URL; an older one stops working. The URL is shown once."""
    await revoke_feed(db, ctx)
    token = new_token()
    feed = CalendarFeed(
        organization_id=ctx.organization_id,
        membership_id=ctx.membership.id,
        user_id=ctx.user.id,
        token_hash=hash_token(token),
    )
    db.add(feed)
    await db.flush()
    await audit.record(
        db,
        action="calendar_feed.created",
        resource_type="calendar_feed",
        resource_id=feed.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
    return FeedCreatedOut(active=True, created_at=feed.created_at, url=feed_url(token))


FEED_PAST_DAYS = 60
FEED_FUTURE_DAYS = 550


async def render_feed(db: AsyncSession, token: str) -> str | None:
    """The iCal text for a feed token, or None if the token is unknown or revoked.

    Feeds leave the platform (they are read by calendar apps and their sync servers), so they
    carry titles, times and locations only: no descriptions, notes or amounts.
    """
    row = (
        (
            await db.execute(
                text("SELECT * FROM app_calendar_feed_by_token(:h)"), {"h": hash_token(token)}
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    is_client = row["role"] == "client"
    await set_tenant_context(
        db, organization_id=row["organization_id"], user_id=row["user_id"], role=row["role"]
    )
    today = _now().date()
    items = await collect(
        db,
        Viewer(row["organization_id"], row["membership_id"], is_client),
        today - timedelta(days=FEED_PAST_DAYS),
        today + timedelta(days=FEED_FUTURE_DAYS),
        mine=True,
        payments=False,
    )
    await db.execute(
        update(CalendarFeed).where(CalendarFeed.id == row["id"]).values(last_used_at=_now())
    )
    base = get_settings().app_base_url
    entries: list[ics.IcsEntry] = []
    for item in items:
        if item.kind == "event" and not item.all_day and item.starts_at:
            start: datetime | date = item.starts_at
            end: datetime | date = item.ends_at or item.starts_at + timedelta(hours=1)
        else:
            start, end = item.date, ics.all_day_end(item.end_date)
        prefix = {"wedding": "Wedding: ", "task": "Due: ", "event": "", "payment": ""}[item.kind]
        summary = f"{prefix}{item.title}"
        if not is_client and item.kind != "wedding":
            summary += f" · {item.project_title}"
        url = (
            f"{base}/portal"
            if is_client
            else f"{base}/app/weddings/{item.project_id}"
            + {"task": "/tasks", "event": "/calendar"}.get(item.kind, "")
        )
        entries.append(
            ics.IcsEntry(
                uid=f"{item.kind}-{item.id}@wedding-platform",
                summary=summary,
                start=start,
                end=end,
                location=item.location,
                url=url,
                status="CONFIRMED",
            )
        )
    return ics.build(f"Weddings · {row['organization_name']}", entries)
