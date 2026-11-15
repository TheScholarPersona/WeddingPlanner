"""Weddings (projects), their team, vendors and progress. All reads run under RLS."""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.models import User
from app.authz.deps import OrgContext, ProjectContext, not_found
from app.authz.permissions import ProjectPerm
from app.clients.models import Client
from app.clients.schemas import ClientIn
from app.clients.service import create_client
from app.core.errors import ProblemError
from app.organizations.models import Membership, MembershipStatus, OrgRole
from app.projects.models import (
    Project,
    ProjectMember,
    ProjectRole,
    ProjectStatus,
    ProjectVendor,
)
from app.projects.schemas import (
    DashboardOut,
    MilestoneOut,
    Progress,
    ProjectCreateIn,
    ProjectDetailOut,
    ProjectMemberIn,
    ProjectMemberOut,
    ProjectMemberUpdateIn,
    ProjectSummaryOut,
    ProjectUpdateIn,
    ProjectVendorIn,
    ProjectVendorOut,
    ProjectVendorUpdateIn,
)
from app.tasks.models import Milestone, Task, TaskStatus
from app.templates.models import ProjectTemplate
from app.templates.service import apply_template
from app.vendors.models import Vendor

ACTIVE_TASK = and_(Task.deleted_at.is_(None), Task.status != TaskStatus.CANCELLED)


def _today() -> date:
    return datetime.now(UTC).date()


def _progress(done: int, total: int) -> Progress:
    return Progress(done=done, total=total, percent=round(done * 100 / total) if total else 0)


def _summary_query() -> Select[Any]:
    tasks = (
        select(
            Task.project_id,
            func.count().label("total"),
            func.count().filter(Task.status == TaskStatus.DONE).label("done"),
        )
        .where(ACTIVE_TASK)
        .group_by(Task.project_id)
        .subquery()
    )
    lead = (
        select(ProjectMember.project_id, func.min(User.full_name).label("lead_name"))
        .join(Membership, Membership.id == ProjectMember.membership_id)
        .join(User, User.id == Membership.user_id)
        .where(ProjectMember.project_role == ProjectRole.LEAD)
        .group_by(ProjectMember.project_id)
        .subquery()
    )
    return (
        select(
            Project,
            Client.display_name,
            func.coalesce(tasks.c.done, 0),
            func.coalesce(tasks.c.total, 0),
            lead.c.lead_name,
        )
        .join(Client, Client.id == Project.client_id)
        .outerjoin(tasks, tasks.c.project_id == Project.id)
        .outerjoin(lead, lead.c.project_id == Project.id)
        .where(Project.deleted_at.is_(None))
    )


async def _my_roles(db: AsyncSession, ctx: OrgContext) -> dict[uuid.UUID, str]:
    rows = await db.execute(
        select(ProjectMember.project_id, ProjectMember.project_role).where(
            ProjectMember.membership_id == ctx.membership.id
        )
    )
    return {pid: role for pid, role in rows.all()}


def _summary(
    row: tuple[Project, str, int, int, str | None], my_role: str | None
) -> ProjectSummaryOut:
    project, client_name, done, total, lead_name = row
    return ProjectSummaryOut(
        id=project.id,
        title=project.title,
        client_id=project.client_id,
        client_name=client_name,
        wedding_date=project.wedding_date,
        days_to_go=(project.wedding_date - _today()).days if project.wedding_date else None,
        venue_name=project.venue_name,
        guest_count_planned=project.guest_count_planned,
        status=project.status,
        lead_name=lead_name,
        my_role=my_role,
        progress=_progress(done, total),
    )


def _role_for(ctx: OrgContext, roles: dict[uuid.UUID, str], project_id: uuid.UUID) -> str | None:
    return "admin" if ctx.role == OrgRole.ORG_ADMIN else roles.get(project_id)


async def list_projects(
    db: AsyncSession, ctx: OrgContext, status: str | None, mine: bool
) -> list[ProjectSummaryOut]:
    stmt = _summary_query().order_by(Project.wedding_date.asc().nulls_last(), Project.title)
    if status:
        stmt = stmt.where(Project.status == status)
    else:
        stmt = stmt.where(Project.status != ProjectStatus.ARCHIVED)
    roles = await _my_roles(db, ctx)
    if mine:
        stmt = stmt.where(Project.id.in_(list(roles)))
    rows = (await db.execute(stmt)).all()
    return [_summary(r, _role_for(ctx, roles, r[0].id)) for r in rows]


async def create_project(db: AsyncSession, ctx: OrgContext, body: ProjectCreateIn) -> Project:
    if body.client_id is not None:
        client = await db.get(Client, body.client_id)
        if client is None or client.deleted_at is not None:
            raise ProblemError(422, "invalid_client", "Client not found", "Choose another client.")
    else:
        assert body.new_client_name is not None
        client = await create_client(
            db, ctx, ClientIn(display_name=body.new_client_name, status="booked")
        )

    project = Project(
        organization_id=ctx.organization_id,
        client_id=client.id,
        title=body.title or client.display_name,
        wedding_date=body.wedding_date,
        venue_name=body.venue_name,
        venue_address=body.venue_address,
        guest_count_planned=body.guest_count_planned,
        style_notes=body.style_notes,
        created_by=ctx.user.id,
    )
    db.add(project)
    await db.flush()
    db.add(
        ProjectMember(
            organization_id=ctx.organization_id,
            project_id=project.id,
            membership_id=ctx.membership.id,
            project_role=ProjectRole.LEAD,
        )
    )
    await db.flush()

    template_id = body.template_id
    if template_id is None:
        template_id = (
            await db.execute(select(ProjectTemplate.id).where(ProjectTemplate.is_default.is_(True)))
        ).scalar_one_or_none()
    task_count = 0
    if template_id is not None:
        task_count = await apply_template(
            db,
            template_id=template_id,
            organization_id=ctx.organization_id,
            project_id=project.id,
            wedding_date=project.wedding_date,
        )
    await audit.record(
        db,
        action="project.created",
        resource_type="project",
        resource_id=project.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"tasks_from_template": {"new": task_count}},
    )
    return project


async def get_project(db: AsyncSession, ctx: ProjectContext) -> ProjectDetailOut:
    project = ctx.project
    row = (await db.execute(_summary_query().where(Project.id == project.id))).one()
    summary = _summary(row, ctx.project_role)
    today = _today()

    counts = (
        await db.execute(
            select(
                func.count().filter(Task.status != TaskStatus.DONE),
                func.count().filter(Task.status != TaskStatus.DONE, Task.due_date < today),
                func.count().filter(Task.status != TaskStatus.DONE, Task.assignee_type == "client"),
            ).where(Task.project_id == project.id, ACTIVE_TASK)
        )
    ).one()

    per_milestone = (
        select(
            Task.milestone_id,
            func.count().label("total"),
            func.count().filter(Task.status == TaskStatus.DONE).label("done"),
        )
        .where(Task.project_id == project.id, ACTIVE_TASK)
        .group_by(Task.milestone_id)
        .subquery()
    )
    milestones = (
        await db.execute(
            select(Milestone, per_milestone.c.total, per_milestone.c.done)
            .outerjoin(per_milestone, per_milestone.c.milestone_id == Milestone.id)
            .where(Milestone.project_id == project.id)
            .order_by(Milestone.due_date.asc().nulls_last(), Milestone.position)
        )
    ).all()

    return ProjectDetailOut(
        **summary.model_dump(),
        venue_address=project.venue_address,
        style_notes=project.style_notes,
        notes_internal=project.notes_internal,
        version=project.version,
        open_tasks=counts[0],
        overdue_tasks=counts[1],
        client_tasks_open=counts[2],
        milestones=[
            MilestoneOut(
                id=m.id,
                title=m.title,
                due_date=m.due_date,
                completed=m.completed_at is not None or (bool(total) and total == done),
                visibility=m.visibility,
                task_total=total or 0,
                task_done=done or 0,
            )
            for m, total, done in milestones
        ],
        team=await list_members(db, ctx),
        permissions=sorted(p.value for p in ProjectPerm if ctx.can(p)),
    )


def _check_version(project: Project, if_match: str | None) -> None:
    if if_match is None:
        raise ProblemError(
            428, "precondition_required", "Version missing", "Reload the wedding and try again."
        )
    if if_match.strip('"W/') != str(project.version):
        raise ProblemError(
            412,
            "stale_version",
            "This wedding was changed by someone else",
            "Reload the wedding and apply your changes again.",
        )


async def update_project(
    db: AsyncSession, ctx: ProjectContext, body: ProjectUpdateIn, if_match: str | None
) -> None:
    project = ctx.project
    _check_version(project, if_match)
    fields = body.model_dump(exclude_unset=True)
    before = {k: getattr(project, k) for k in fields}
    nullable = {
        "wedding_date",
        "venue_name",
        "venue_address",
        "guest_count_planned",
        "style_notes",
        "notes_internal",
    }
    for key, value in fields.items():
        if value is not None or key in nullable:
            setattr(project, key, value)
    project.version += 1
    changes = audit.diff(before, {k: getattr(project, k) for k in fields})
    changes.pop("notes_internal", None)
    await audit.record(
        db,
        action="project.updated",
        resource_type="project",
        resource_id=project.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes=changes,
    )
    await db.flush()


async def set_archived(db: AsyncSession, ctx: ProjectContext, archived: bool) -> None:
    project = ctx.project
    project.status = ProjectStatus.ARCHIVED if archived else ProjectStatus.COMPLETED
    project.archived_at = datetime.now(UTC) if archived else None
    project.version += 1
    await audit.record(
        db,
        action="project.archived" if archived else "project.restored",
        resource_type="project",
        resource_id=project.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )


async def delete_project(db: AsyncSession, ctx: ProjectContext) -> None:
    ctx.project.deleted_at = datetime.now(UTC)
    await audit.record(
        db,
        action="project.deleted",
        resource_type="project",
        resource_id=ctx.project.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )


# --- Team -------------------------------------------------------------------------------


async def list_members(db: AsyncSession, ctx: ProjectContext) -> list[ProjectMemberOut]:
    rows = await db.execute(
        select(ProjectMember, User.full_name, User.email)
        .join(Membership, Membership.id == ProjectMember.membership_id)
        .join(User, User.id == Membership.user_id)
        .where(ProjectMember.project_id == ctx.project.id, ProjectMember.project_role != "client")
        .order_by(ProjectMember.project_role, User.full_name)
    )
    return [
        ProjectMemberOut(
            id=pm.id,
            membership_id=pm.membership_id,
            full_name=name,
            email=email,
            project_role=pm.project_role,
        )
        for pm, name, email in rows.all()
    ]


async def _leads(db: AsyncSession, project_id: uuid.UUID, excluding: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(ProjectMember)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.project_role == ProjectRole.LEAD,
                ProjectMember.id != excluding,
            )
        )
    ).scalar_one()


async def add_member(db: AsyncSession, ctx: ProjectContext, body: ProjectMemberIn) -> None:
    membership = await db.get(Membership, body.membership_id)
    if (
        membership is None
        or membership.organization_id != ctx.organization_id
        or membership.status != MembershipStatus.ACTIVE
        or membership.role == OrgRole.CLIENT
    ):
        raise ProblemError(
            422, "invalid_member", "Not a team member", "Choose an active member of your team."
        )
    exists = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == ctx.project.id,
                ProjectMember.membership_id == membership.id,
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise ProblemError(
            409, "already_assigned", "Already assigned", "This person is already on the wedding."
        )
    member = ProjectMember(
        organization_id=ctx.organization_id,
        project_id=ctx.project.id,
        membership_id=membership.id,
        project_role=body.project_role,
    )
    db.add(member)
    await db.flush()
    await audit.record(
        db,
        action="project_member.added",
        resource_type="project_member",
        resource_id=member.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"project_role": {"new": body.project_role}},
    )


async def _member(db: AsyncSession, ctx: ProjectContext, member_id: uuid.UUID) -> ProjectMember:
    member = await db.get(ProjectMember, member_id)
    if member is None or member.project_id != ctx.project.id or member.project_role == "client":
        raise not_found()
    return member


async def update_member(
    db: AsyncSession, ctx: ProjectContext, member_id: uuid.UUID, body: ProjectMemberUpdateIn
) -> None:
    member = await _member(db, ctx, member_id)
    if member.project_role == ProjectRole.LEAD and body.project_role != "lead":
        if await _leads(db, ctx.project.id, member.id) == 0:
            raise ProblemError(
                409, "last_lead", "A lead is required", "Every wedding needs at least one lead."
            )
    before = member.project_role
    member.project_role = body.project_role
    await audit.record(
        db,
        action="project_member.updated",
        resource_type="project_member",
        resource_id=member.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"project_role": {"old": before, "new": body.project_role}},
    )


async def remove_member(db: AsyncSession, ctx: ProjectContext, member_id: uuid.UUID) -> None:
    member = await _member(db, ctx, member_id)
    if member.project_role == ProjectRole.LEAD and await _leads(db, ctx.project.id, member.id) == 0:
        raise ProblemError(
            409, "last_lead", "A lead is required", "Every wedding needs at least one lead."
        )
    await db.delete(member)
    await audit.record(
        db,
        action="project_member.removed",
        resource_type="project_member",
        resource_id=member_id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )


# --- Vendors ----------------------------------------------------------------------------


def _vendor_out(link: ProjectVendor, vendor: Vendor) -> ProjectVendorOut:
    return ProjectVendorOut(
        id=link.id,
        vendor_id=vendor.id,
        name=vendor.name,
        category=vendor.category,
        contact_name=vendor.contact_name,
        email=vendor.email,
        phone=vendor.phone,
        status=link.status,
        notes=link.notes,
    )


async def list_vendors(db: AsyncSession, ctx: ProjectContext) -> list[ProjectVendorOut]:
    rows = await db.execute(
        select(ProjectVendor, Vendor)
        .join(Vendor, Vendor.id == ProjectVendor.vendor_id)
        .where(ProjectVendor.project_id == ctx.project.id)
        .order_by(Vendor.category, Vendor.name)
    )
    return [_vendor_out(link, vendor) for link, vendor in rows.all()]


async def add_vendor(
    db: AsyncSession, ctx: ProjectContext, body: ProjectVendorIn
) -> ProjectVendorOut:
    vendor = await db.get(Vendor, body.vendor_id)
    if vendor is None or vendor.deleted_at is not None:
        raise ProblemError(422, "invalid_vendor", "Vendor not found", "Choose another vendor.")
    exists = (
        await db.execute(
            select(ProjectVendor).where(
                ProjectVendor.project_id == ctx.project.id, ProjectVendor.vendor_id == vendor.id
            )
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise ProblemError(
            409, "already_linked", "Already added", "This vendor is already on the wedding."
        )
    link = ProjectVendor(
        organization_id=ctx.organization_id,
        project_id=ctx.project.id,
        vendor_id=vendor.id,
        status=body.status,
        notes=body.notes,
    )
    db.add(link)
    await db.flush()
    await audit.record(
        db,
        action="project_vendor.added",
        resource_type="project_vendor",
        resource_id=link.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
    return _vendor_out(link, vendor)


async def _vendor_link(db: AsyncSession, ctx: ProjectContext, link_id: uuid.UUID) -> ProjectVendor:
    link = await db.get(ProjectVendor, link_id)
    if link is None or link.project_id != ctx.project.id:
        raise not_found()
    return link


async def update_vendor(
    db: AsyncSession, ctx: ProjectContext, link_id: uuid.UUID, body: ProjectVendorUpdateIn
) -> ProjectVendorOut:
    link = await _vendor_link(db, ctx, link_id)
    before = link.status
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None or key == "notes":
            setattr(link, key, value)
    await db.flush()
    if link.status != before:
        await audit.record(
            db,
            action="project_vendor.updated",
            resource_type="project_vendor",
            resource_id=link.id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.user.id,
            changes={"status": {"old": before, "new": link.status}},
        )
    vendor = await db.get(Vendor, link.vendor_id)
    assert vendor is not None
    return _vendor_out(link, vendor)


async def remove_vendor(db: AsyncSession, ctx: ProjectContext, link_id: uuid.UUID) -> None:
    link = await _vendor_link(db, ctx, link_id)
    await db.delete(link)
    await audit.record(
        db,
        action="project_vendor.removed",
        resource_type="project_vendor",
        resource_id=link_id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )


# --- Dashboard --------------------------------------------------------------------------


async def dashboard(db: AsyncSession, ctx: OrgContext) -> DashboardOut:
    today = _today()
    week_end = today + timedelta(days=7 - today.weekday())  # until Sunday night
    open_task = and_(ACTIVE_TASK, Task.status != TaskStatus.DONE)
    visible_projects = select(Project.id).where(
        Project.deleted_at.is_(None), Project.status != ProjectStatus.ARCHIVED
    )

    def count(*conditions: object) -> Select[Any]:
        return (
            select(func.count())
            .select_from(Task)
            .where(open_task, Task.project_id.in_(visible_projects), *conditions)  # type: ignore[arg-type]
        )

    due_week = (
        await db.execute(count(Task.due_date >= today, Task.due_date < week_end))
    ).scalar_one()
    due_week_mine = (
        await db.execute(
            count(
                Task.due_date >= today,
                Task.due_date < week_end,
                Task.assignee_membership_id == ctx.membership.id,
            )
        )
    ).scalar_one()
    overdue = (await db.execute(count(Task.due_date < today))).scalar_one()
    overdue_weddings = (
        await db.execute(
            select(func.count(func.distinct(Task.project_id))).where(
                open_task, Task.due_date < today, Task.project_id.in_(visible_projects)
            )
        )
    ).scalar_one()

    active_filter: Sequence[object] = (
        Project.deleted_at.is_(None),
        Project.status.in_([ProjectStatus.PLANNING, ProjectStatus.ACTIVE]),
    )
    active = (
        await db.execute(select(func.count()).select_from(Project).where(*active_filter))  # type: ignore[arg-type]
    ).scalar_one()
    next_six = (
        await db.execute(
            select(func.count())
            .select_from(Project)
            .where(
                *active_filter,  # type: ignore[arg-type]
                Project.wedding_date >= today,
                Project.wedding_date <= today + timedelta(days=183),
            )
        )
    ).scalar_one()

    roles = await _my_roles(db, ctx)
    upcoming_rows = (
        await db.execute(
            _summary_query()
            .where(
                Project.status.in_([ProjectStatus.PLANNING, ProjectStatus.ACTIVE]),
                Project.wedding_date >= today,
            )
            .order_by(Project.wedding_date)
            .limit(5)
        )
    ).all()
    return DashboardOut(
        active_weddings=active,
        weddings_next_6_months=next_six,
        tasks_due_this_week=due_week,
        tasks_due_this_week_mine=due_week_mine,
        overdue_tasks=overdue,
        overdue_weddings=overdue_weddings,
        upcoming=[_summary(r, _role_for(ctx, roles, r[0].id)) for r in upcoming_rows],
    )
