"""Client portal: what the couple sees of their wedding.

Every query runs with app.role = 'client', so the restrictive RLS policies hide everything
that is not shared with the couple; the portal schemas additionally omit internal fields.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from fastapi import Depends
from sqlalchemy import select

from app.auth.models import User
from app.authz.deps import CurrentUser, DbSession, ProjectContext, not_found
from app.budget import service as budget_service
from app.budget.models import Budget
from app.core.errors import ProblemError
from app.db.tenant import set_tenant_context
from app.documents import service as document_service
from app.documents.schemas import DocumentOut
from app.events import service as event_service
from app.organizations.models import Membership, MembershipStatus, Organization, OrgRole
from app.portal.schemas import (
    PortalBudget,
    PortalBudgetCategory,
    PortalBudgetItem,
    PortalBudgetSummary,
    PortalCalendarItem,
    PortalChecklistItem,
    PortalComment,
    PortalDocument,
    PortalFile,
    PortalMilestone,
    PortalOrganization,
    PortalOverview,
    PortalPayment,
    PortalProgress,
    PortalProjectSummary,
    PortalTask,
    PortalTeamMember,
)
from app.projects.models import Project, ProjectMember, ProjectRole
from app.tasks import service as tasks
from app.tasks.models import Comment, Milestone, Task, TaskChecklistItem, TaskStatus
from app.tasks.schemas import CommentIn


@dataclass
class PortalAccess:
    ctx: ProjectContext
    organization: Organization


async def _client_memberships(db: DbSession, user: User) -> list[Membership]:
    return list(
        (
            await db.execute(
                select(Membership).where(
                    Membership.user_id == user.id,
                    Membership.role == OrgRole.CLIENT,
                    Membership.status == MembershipStatus.ACTIVE,
                )
            )
        ).scalars()
    )


async def list_projects(db: DbSession, auth: CurrentUser) -> list[PortalProjectSummary]:
    result: list[PortalProjectSummary] = []
    for membership in await _client_memberships(db, auth.user):
        await set_tenant_context(
            db, organization_id=membership.organization_id, user_id=auth.user.id, role="client"
        )
        org = await db.get(Organization, membership.organization_id)
        if org is None or org.status != "active":
            continue
        rows = await db.execute(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(
                ProjectMember.membership_id == membership.id,
                ProjectMember.project_role == ProjectRole.CLIENT,
                Project.deleted_at.is_(None),
            )
            .order_by(Project.wedding_date)
        )
        for project in rows.scalars():
            result.append(
                PortalProjectSummary(
                    id=project.id,
                    title=project.title,
                    wedding_date=project.wedding_date,
                    organization=PortalOrganization(name=org.name, accent_color=org.accent_color),
                )
            )
    return result


async def portal_access(project_id: uuid.UUID, auth: CurrentUser, db: DbSession) -> PortalAccess:
    """Dependency: the signed-in couple's access to one wedding, with client RLS context."""
    for membership in await _client_memberships(db, auth.user):
        await set_tenant_context(
            db, organization_id=membership.organization_id, user_id=auth.user.id, role="client"
        )
        project = (
            await db.execute(
                select(Project)
                .join(ProjectMember, ProjectMember.project_id == Project.id)
                .where(
                    Project.id == project_id,
                    Project.deleted_at.is_(None),
                    ProjectMember.membership_id == membership.id,
                    ProjectMember.project_role == ProjectRole.CLIENT,
                )
            )
        ).scalar_one_or_none()
        if project is not None:
            org = await db.get(Organization, membership.organization_id)
            assert org is not None
            ctx = ProjectContext(
                user=auth.user,
                session=auth.session,
                membership=membership,
                organization_id=membership.organization_id,
                project=project,
                project_role=ProjectRole.CLIENT,
            )
            return PortalAccess(ctx=ctx, organization=org)
    raise not_found()


Access = Depends(portal_access)


def _today() -> Any:
    return datetime.now(UTC).date()


async def _tasks(db: DbSession, project_id: uuid.UUID) -> list[PortalTask]:
    task_rows = (
        await db.execute(
            select(Task, Milestone.title)
            .outerjoin(Milestone, Milestone.id == Task.milestone_id)
            .where(
                Task.project_id == project_id,
                Task.deleted_at.is_(None),
                Task.status != TaskStatus.CANCELLED,
            )
            .order_by(Task.due_date.asc().nulls_last(), Task.position)
        )
    ).all()
    ids = [t.id for t, _ in task_rows]
    checklist: dict[uuid.UUID, list[PortalChecklistItem]] = {i: [] for i in ids}
    for item in (
        await db.execute(
            select(TaskChecklistItem)
            .where(TaskChecklistItem.task_id.in_(ids))
            .order_by(TaskChecklistItem.position)
        )
    ).scalars():
        checklist[item.task_id].append(
            PortalChecklistItem(id=item.id, title=item.title, is_done=item.is_done)
        )
    counts: dict[uuid.UUID, int] = {}
    for comment in (
        await db.execute(
            select(Comment.target_id).where(
                Comment.target_type == "task", Comment.target_id.in_(ids)
            )
        )
    ).scalars():
        counts[comment] = counts.get(comment, 0) + 1
    today = _today()
    return [
        PortalTask(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status,
            due_date=task.due_date,
            overdue=bool(task.due_date and task.due_date < today and task.status != "done"),
            milestone_id=task.milestone_id,
            milestone_title=milestone_title,
            for_couple=task.assignee_type == "client",
            checklist=checklist[task.id],
            comment_count=counts.get(task.id, 0),
        )
        for task, milestone_title in task_rows
    ]


async def overview(db: DbSession, access: PortalAccess) -> PortalOverview:
    project = access.ctx.project
    tasks_ = await _tasks(db, project.id)
    done = sum(t.status == "done" for t in tasks_)
    milestones = (
        await db.execute(
            select(Milestone)
            .where(Milestone.project_id == project.id)
            .order_by(Milestone.due_date.asc().nulls_last(), Milestone.position)
        )
    ).scalars()
    team = await db.execute(
        select(User.full_name, ProjectMember.project_role)
        .select_from(ProjectMember)
        .join(Membership, Membership.id == ProjectMember.membership_id)
        .join(User, User.id == Membership.user_id)
        .where(
            ProjectMember.project_id == project.id,
            ProjectMember.project_role.in_([ProjectRole.LEAD, ProjectRole.PLANNER]),
        )
        .order_by(ProjectMember.project_role, User.full_name)
    )
    budget = await _budget_view(db, access)
    today = _today()
    return PortalOverview(
        id=project.id,
        title=project.title,
        wedding_date=project.wedding_date,
        days_to_go=(project.wedding_date - today).days if project.wedding_date else None,
        venue_name=project.venue_name,
        guest_count_planned=project.guest_count_planned,
        organization=PortalOrganization(
            name=access.organization.name, accent_color=access.organization.accent_color
        ),
        progress=PortalProgress(
            done=done, total=len(tasks_), percent=round(done * 100 / len(tasks_)) if tasks_ else 0
        ),
        next_steps=[t for t in tasks_ if t.for_couple and t.status != "done"][:5],
        milestones=[
            PortalMilestone(
                id=m.id, title=m.title, due_date=m.due_date, completed=m.completed_at is not None
            )
            for m in milestones
        ],
        team=[PortalTeamMember(full_name=n, role=r) for n, r in team.all()],
        budget=PortalBudgetSummary(
            total_cents=budget.total_cents,
            contracted_cents=sum(
                i.contracted_cents or 0 for c in budget.categories for i in c.items
            ),
            paid_cents=sum(i.paid_cents for c in budget.categories for i in c.items),
            currency=budget.currency,
        ),
    )


async def task_list(db: DbSession, access: PortalAccess) -> list[PortalTask]:
    return await _tasks(db, access.ctx.project.id)


async def _couple_task(db: DbSession, access: PortalAccess, task_id: uuid.UUID) -> Task:
    task = await db.get(Task, task_id)
    if task is None or task.project_id != access.ctx.project.id or task.deleted_at is not None:
        raise not_found()
    if task.assignee_type != "client":
        raise ProblemError(
            403, "not_your_task", "Not your task", "Your planner takes care of this task."
        )
    return task


async def set_done(
    db: DbSession, access: PortalAccess, task_id: uuid.UUID, done: bool
) -> list[PortalTask]:
    await _couple_task(db, access, task_id)
    await tasks.set_done(db, access.ctx, task_id, done)
    return await _tasks(db, access.ctx.project.id)


async def tick(
    db: DbSession, access: PortalAccess, task_id: uuid.UUID, item_id: uuid.UUID, done: bool
) -> list[PortalTask]:
    await _couple_task(db, access, task_id)
    item = await db.get(TaskChecklistItem, item_id)
    if item is None or item.task_id != task_id:
        raise not_found()
    item.is_done = done
    await db.flush()
    return await _tasks(db, access.ctx.project.id)


async def comments(db: DbSession, access: PortalAccess, task_id: uuid.UUID) -> list[PortalComment]:
    task = await db.get(Task, task_id)
    if task is None or task.project_id != access.ctx.project.id:
        raise not_found()
    return [
        PortalComment(
            id=c.id,
            author_name=c.author_name,
            is_mine=c.is_mine,
            body=c.body,
            created_at=c.created_at,
        )
        for c in await tasks.list_comments(db, access.ctx, "task", task_id)
    ]


async def add_comment(
    db: DbSession, access: PortalAccess, task_id: uuid.UUID, body: str
) -> list[PortalComment]:
    await tasks.add_comment(
        db,
        access.ctx,
        CommentIn(target_type="task", target_id=task_id, body=body, visibility="client"),
    )
    return await comments(db, access, task_id)


async def _budget_view(db: DbSession, access: PortalAccess) -> Any:
    budget = (
        await db.execute(select(Budget).where(Budget.project_id == access.ctx.project.id))
    ).scalar_one_or_none()
    if budget is None:
        budget = Budget(
            id=uuid.UUID(int=0), total_cents=0, currency="EUR", warning_threshold_pct=90, version=1
        )
        return await budget_service.load(db, access.ctx.project.id, budget)
    return await budget_service.load(db, access.ctx.project.id, budget)


async def budget(db: DbSession, access: PortalAccess) -> PortalBudget:
    view = await _budget_view(db, access)
    return PortalBudget(
        total_cents=view.total_cents,
        currency=view.currency,
        contracted_cents=view.totals.contracted_cents,
        paid_cents=view.totals.paid_cents,
        forecast_cents=view.totals.forecast_cents,
        categories=[
            PortalBudgetCategory(
                id=c.id,
                name=c.name,
                items=[
                    PortalBudgetItem(
                        id=i.id,
                        title=i.title,
                        planned_cents=i.planned_cents,
                        quoted_cents=i.quoted_cents,
                        contracted_cents=i.contracted_cents,
                        paid_cents=i.paid_cents,
                        stage="booked"
                        if i.contracted_cents is not None
                        else "quoted"
                        if i.quoted_cents is not None
                        else "planned",
                    )
                    for i in c.items
                ],
            )
            for c in view.categories
            if c.items
        ],
        upcoming_payments=[
            PortalPayment(
                id=p.id,
                item_title=p.item_title,
                label=p.label,
                amount_cents=p.amount_cents,
                due_date=p.due_date,
                overdue=p.overdue,
            )
            for p in view.upcoming_payments
        ],
    )


# --- Documents, calendar and settings (Sprint 5) -------------------------------------------


def _portal_document(
    doc: DocumentOut, user_id: uuid.UUID, own_ids: set[uuid.UUID]
) -> PortalDocument:
    current = doc.current
    return PortalDocument(
        id=doc.id,
        title=doc.title,
        category=doc.category,
        from_couple=doc.uploaded_by_type == "client",
        added_by=doc.created_by_name,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        can_delete=doc.id in own_ids,
        file=PortalFile(
            filename=current.filename,
            content_type=current.content_type,
            size_bytes=current.size_bytes,
            downloadable=current.downloadable,
            scan_status=current.scan_status,
        )
        if current
        else None,
    )


async def documents(db: DbSession, access: PortalAccess) -> list[PortalDocument]:
    from app.documents.models import Document

    docs = await document_service.list_documents(db, access.ctx)
    own = set(
        (
            await db.execute(
                select(Document.id).where(
                    Document.project_id == access.ctx.project.id,
                    Document.created_by == access.ctx.user.id,
                    Document.uploaded_by_type == "client",
                )
            )
        ).scalars()
    )
    return [_portal_document(d, access.ctx.user.id, own) for d in docs]


async def calendar(
    db: DbSession, access: PortalAccess, start: date, end: date
) -> list[PortalCalendarItem]:
    viewer = event_service.Viewer(
        access.ctx.organization_id, access.ctx.membership.id, is_client=True
    )
    items = await event_service.collect(
        db, viewer, start, end, project_id=access.ctx.project.id, mine=True
    )
    return [
        PortalCalendarItem(
            kind=i.kind,
            id=i.id,
            title=i.title,
            date=i.date,
            end_date=i.end_date,
            all_day=i.all_day,
            starts_at=i.starts_at,
            ends_at=i.ends_at,
            location=i.location,
            status=i.status,
            amount_cents=i.amount_cents,
        )
        for i in items
    ]
