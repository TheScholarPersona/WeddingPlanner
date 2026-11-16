"""Tasks, milestones, checklists, comments and the activity feed of a wedding.

Everything runs under row-level security: a wedding the user cannot access has no tasks.
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.audit import service as audit
from app.auth.models import User
from app.authz.deps import OrgContext, ProjectContext, not_found
from app.authz.permissions import ADMIN_PROJECT_ROLE
from app.core.errors import ProblemError
from app.core.versioning import check_version
from app.notifications import service as notify
from app.organizations.models import Membership, MembershipStatus, OrgRole
from app.projects.models import Project, ProjectMember
from app.tasks.models import (
    ActivityEvent,
    Comment,
    Milestone,
    Task,
    TaskChecklistItem,
    TaskStatus,
    Visibility,
)
from app.tasks.schemas import (
    ActivityOut,
    ActivityPageOut,
    ChecklistItemIn,
    ChecklistItemOut,
    ChecklistItemUpdateIn,
    CommentIn,
    CommentOut,
    CommentUpdateIn,
    MilestoneDetailOut,
    MilestoneIn,
    MilestoneUpdateIn,
    MyTaskOut,
    ReorderIn,
    TaskDetailOut,
    TaskIn,
    TaskOut,
    TaskUpdateIn,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _today() -> date:
    return _now().date()


# --- Activity ---------------------------------------------------------------------------


async def record_activity(
    db: AsyncSession,
    ctx: ProjectContext,
    *,
    verb: str,
    target_type: str,
    target_id: uuid.UUID | None,
    summary: str,
    visibility: str = Visibility.INTERNAL,
) -> None:
    db.add(
        ActivityEvent(
            organization_id=ctx.organization_id,
            project_id=ctx.project.id,
            actor_user_id=ctx.user.id,
            verb=verb,
            target_type=target_type,
            target_id=target_id,
            summary=summary[:300],
            visibility=visibility,
        )
    )
    await db.flush()


async def list_activity(
    db: AsyncSession, ctx: ProjectContext, limit: int, cursor: uuid.UUID | None
) -> ActivityPageOut:
    stmt = (
        select(ActivityEvent, User.full_name)
        .outerjoin(User, User.id == ActivityEvent.actor_user_id)
        .where(ActivityEvent.project_id == ctx.project.id)
        .order_by(ActivityEvent.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        stmt = stmt.where(ActivityEvent.id < cursor)
    rows = (await db.execute(stmt)).all()
    items = [
        ActivityOut(
            id=e.id,
            verb=e.verb,
            summary=e.summary,
            actor_name=name,
            target_type=e.target_type,
            target_id=e.target_id,
            visibility=e.visibility,
            created_at=e.created_at,
        )
        for e, name in rows[:limit]
    ]
    return ActivityPageOut(items=items, next_cursor=items[-1].id if len(rows) > limit else None)


# --- Task queries -----------------------------------------------------------------------

AssigneeUser = aliased(User)
CompletedBy = aliased(User)


def _task_select() -> Any:
    checklist = (
        select(
            TaskChecklistItem.task_id,
            func.count().label("total"),
            func.count().filter(TaskChecklistItem.is_done.is_(True)).label("done"),
        )
        .group_by(TaskChecklistItem.task_id)
        .subquery()
    )
    comments = (
        select(Comment.target_id, func.count().label("n"))
        .where(Comment.target_type == "task")
        .group_by(Comment.target_id)
        .subquery()
    )
    return (
        select(
            Task,
            Milestone.title,
            AssigneeUser.full_name,
            CompletedBy.full_name,
            func.coalesce(checklist.c.total, 0),
            func.coalesce(checklist.c.done, 0),
            func.coalesce(comments.c.n, 0),
        )
        .outerjoin(Milestone, Milestone.id == Task.milestone_id)
        .outerjoin(Membership, Membership.id == Task.assignee_membership_id)
        .outerjoin(AssigneeUser, AssigneeUser.id == Membership.user_id)
        .outerjoin(CompletedBy, CompletedBy.id == Task.completed_by)
        .outerjoin(checklist, checklist.c.task_id == Task.id)
        .outerjoin(comments, comments.c.target_id == Task.id)
        .where(Task.deleted_at.is_(None))
    )


def _task_fields(row: Any) -> dict[str, Any]:
    task, milestone_title, assignee, completed_by, total, done, comment_count = row
    return {
        "id": task.id,
        "project_id": task.project_id,
        "milestone_id": task.milestone_id,
        "milestone_title": milestone_title,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "due_date": task.due_date,
        "overdue": bool(
            task.due_date and task.due_date < _today() and task.status not in ("done", "cancelled")
        ),
        "assignee_type": task.assignee_type,
        "assignee_membership_id": task.assignee_membership_id,
        "assignee_name": assignee,
        "visibility": task.visibility,
        "completed_at": task.completed_at,
        "completed_by_name": completed_by,
        "position": task.position,
        "version": task.version,
        "checklist_total": total,
        "checklist_done": done,
        "comment_count": comment_count,
    }


async def list_tasks(
    db: AsyncSession,
    ctx: ProjectContext,
    *,
    status: str | None,
    assignee: str | None,
    milestone_id: uuid.UUID | None,
    visibility: str | None,
) -> list[TaskOut]:
    stmt = _task_select().where(Task.project_id == ctx.project.id)
    if status == "open":
        stmt = stmt.where(Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]))
    elif status:
        stmt = stmt.where(Task.status == status)
    if assignee == "me":
        stmt = stmt.where(Task.assignee_membership_id == ctx.membership.id)
    elif assignee == "client":
        stmt = stmt.where(Task.assignee_type == "client")
    elif assignee:
        stmt = stmt.where(Task.assignee_membership_id == uuid.UUID(assignee))
    if milestone_id:
        stmt = stmt.where(Task.milestone_id == milestone_id)
    if visibility:
        stmt = stmt.where(Task.visibility == visibility)
    stmt = stmt.order_by(Task.due_date.asc().nulls_last(), Task.position, Task.title)
    return [TaskOut(**_task_fields(row)) for row in (await db.execute(stmt)).all()]


async def _get_task(db: AsyncSession, ctx: ProjectContext, task_id: uuid.UUID) -> Task:
    task = await db.get(Task, task_id)
    if task is None or task.project_id != ctx.project.id or task.deleted_at is not None:
        raise not_found()
    return task


async def get_task(db: AsyncSession, ctx: ProjectContext, task_id: uuid.UUID) -> TaskDetailOut:
    await _get_task(db, ctx, task_id)
    row = (await db.execute(_task_select().where(Task.id == task_id))).one()
    items = (
        await db.execute(
            select(TaskChecklistItem)
            .where(TaskChecklistItem.task_id == task_id)
            .order_by(TaskChecklistItem.position, TaskChecklistItem.created_at)
        )
    ).scalars()
    return TaskDetailOut(
        **_task_fields(row),
        checklist=[
            ChecklistItemOut(id=i.id, title=i.title, is_done=i.is_done, position=i.position)
            for i in items
        ],
    )


async def my_tasks(db: AsyncSession, ctx: OrgContext, status: str) -> list[MyTaskOut]:
    stmt = (
        _task_select()
        .add_columns(Project.title, Project.wedding_date)
        .join(Project, Project.id == Task.project_id)
        .where(
            Task.assignee_membership_id == ctx.membership.id,
            Project.deleted_at.is_(None),
            Project.status != "archived",
        )
        .order_by(Task.due_date.asc().nulls_last(), Project.wedding_date, Task.title)
    )
    if status == "open":
        stmt = stmt.where(Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]))
    else:
        stmt = stmt.where(Task.status == TaskStatus.DONE).limit(100)
    rows = (await db.execute(stmt)).all()
    return [
        MyTaskOut(**_task_fields(row[:7]), project_title=row[7], project_wedding_date=row[8])
        for row in rows
    ]


# --- Task changes -----------------------------------------------------------------------


async def _check_assignee(
    db: AsyncSession, ctx: ProjectContext, assignee_type: str, membership_id: uuid.UUID | None
) -> uuid.UUID | None:
    if assignee_type == "client":
        return None
    if membership_id is None:
        return None
    membership = await db.get(Membership, membership_id)
    if (
        membership is None
        or membership.organization_id != ctx.organization_id
        or membership.status != MembershipStatus.ACTIVE
        or membership.role == OrgRole.CLIENT
    ):
        raise _invalid_assignee()
    if membership.role != OrgRole.ORG_ADMIN:
        assigned = (
            await db.execute(
                select(ProjectMember.id).where(
                    ProjectMember.project_id == ctx.project.id,
                    ProjectMember.membership_id == membership.id,
                )
            )
        ).scalar_one_or_none()
        if assigned is None:
            raise _invalid_assignee()
    return membership.id


def _invalid_assignee() -> ProblemError:
    return ProblemError(
        422, "invalid_assignee", "Not on this wedding", "Assign someone from this wedding's team."
    )


async def _check_milestone(
    db: AsyncSession, ctx: ProjectContext, milestone_id: uuid.UUID | None
) -> None:
    if milestone_id is None:
        return
    milestone = await db.get(Milestone, milestone_id)
    if milestone is None or milestone.project_id != ctx.project.id:
        raise ProblemError(
            422, "invalid_milestone", "Milestone not found", "Choose a milestone of this wedding."
        )


async def create_task(db: AsyncSession, ctx: ProjectContext, body: TaskIn) -> TaskDetailOut:
    await _check_milestone(db, ctx, body.milestone_id)
    assignee = await _check_assignee(db, ctx, body.assignee_type, body.assignee_membership_id)
    position = (
        await db.execute(
            select(func.coalesce(func.max(Task.position), 0)).where(
                Task.project_id == ctx.project.id
            )
        )
    ).scalar_one() + 1
    task = Task(
        organization_id=ctx.organization_id,
        project_id=ctx.project.id,
        milestone_id=body.milestone_id,
        title=body.title.strip(),
        description=body.description,
        due_date=body.due_date,
        priority=body.priority,
        assignee_type=body.assignee_type,
        assignee_membership_id=assignee,
        visibility=body.visibility,
        position=position,
    )
    db.add(task)
    await db.flush()
    for index, title in enumerate(t for t in body.checklist if t.strip()):
        db.add(
            TaskChecklistItem(
                organization_id=ctx.organization_id,
                task_id=task.id,
                title=title.strip(),
                position=index,
            )
        )
    await record_activity(
        db,
        ctx,
        verb="task.created",
        target_type="task",
        target_id=task.id,
        summary=task.title,
        visibility=task.visibility,
    )
    if task.visibility == Visibility.CLIENT:
        await _audit_shared(db, ctx, task)
    if task.assignee_membership_id is not None:
        await notify.task_assigned(db, ctx, task.id, task.title, task.assignee_membership_id)
    return await get_task(db, ctx, task.id)


async def _audit_shared(db: AsyncSession, ctx: ProjectContext, task: Task) -> None:
    await audit.record(
        db,
        action="task.shared_with_client",
        resource_type="task",
        resource_id=task.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"visibility": {"new": "client"}, "project_id": {"new": str(ctx.project.id)}},
    )


async def update_task(
    db: AsyncSession,
    ctx: ProjectContext,
    task_id: uuid.UUID,
    body: TaskUpdateIn,
    if_match: str | None,
) -> TaskDetailOut:
    task = await _get_task(db, ctx, task_id)
    check_version(task.version, if_match, "task")
    fields = body.model_dump(exclude_unset=True)

    if "milestone_id" in fields:
        await _check_milestone(db, ctx, fields["milestone_id"])
    if "assignee_type" in fields or "assignee_membership_id" in fields:
        assignee_type = fields.get("assignee_type") or task.assignee_type
        membership_id = fields.get("assignee_membership_id", task.assignee_membership_id)
        fields["assignee_type"] = assignee_type
        fields["assignee_membership_id"] = await _check_assignee(
            db, ctx, assignee_type, membership_id
        )

    was_shared = task.visibility == Visibility.CLIENT
    previous_assignee = task.assignee_membership_id
    nullable = {"description", "milestone_id", "due_date", "assignee_membership_id"}
    for key, value in fields.items():
        if value is not None or key in nullable:
            setattr(task, key, value)
    if task.status != TaskStatus.DONE:
        task.completed_at = None
        task.completed_by = None
    task.version += 1
    await db.flush()

    if task.assignee_membership_id is not None and task.assignee_membership_id != previous_assignee:
        await notify.task_assigned(db, ctx, task.id, task.title, task.assignee_membership_id)

    if task.visibility == Visibility.CLIENT and not was_shared:
        await _audit_shared(db, ctx, task)
        await record_activity(
            db,
            ctx,
            verb="task.shared",
            target_type="task",
            target_id=task.id,
            summary=task.title,
            visibility=Visibility.CLIENT,
        )
    elif was_shared and task.visibility == Visibility.INTERNAL:
        await audit.record(
            db,
            action="task.unshared",
            resource_type="task",
            resource_id=task.id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.user.id,
            changes={"visibility": {"old": "client", "new": "internal"}},
        )
    return await get_task(db, ctx, task.id)


async def _sync_milestone(db: AsyncSession, ctx: ProjectContext, milestone_id: uuid.UUID) -> None:
    """A milestone is complete when all of its active tasks are done."""
    milestone = await db.get(Milestone, milestone_id)
    if milestone is None:
        return
    open_tasks = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                Task.milestone_id == milestone_id,
                Task.deleted_at.is_(None),
                Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
            )
        )
    ).scalar_one()
    if open_tasks == 0 and milestone.completed_at is None:
        milestone.completed_at = _now()
        await record_activity(
            db,
            ctx,
            verb="milestone.completed",
            target_type="milestone",
            target_id=milestone.id,
            summary=milestone.title,
            visibility=milestone.visibility,
        )
    elif open_tasks > 0 and milestone.completed_at is not None:
        milestone.completed_at = None


async def set_done(
    db: AsyncSession, ctx: ProjectContext, task_id: uuid.UUID, done: bool
) -> TaskDetailOut:
    task = await _get_task(db, ctx, task_id)
    if done and task.status != TaskStatus.DONE:
        task.status = TaskStatus.DONE
        task.completed_at = _now()
        task.completed_by = ctx.user.id
        verb = "task.completed"
    elif not done and task.status == TaskStatus.DONE:
        task.status = TaskStatus.OPEN
        task.completed_at = None
        task.completed_by = None
        verb = "task.reopened"
    else:
        return await get_task(db, ctx, task.id)
    task.version += 1
    await db.flush()
    await record_activity(
        db,
        ctx,
        verb=verb,
        target_type="task",
        target_id=task.id,
        summary=task.title,
        visibility=task.visibility,
    )
    if task.milestone_id:
        await _sync_milestone(db, ctx, task.milestone_id)
    return await get_task(db, ctx, task.id)


async def delete_task(db: AsyncSession, ctx: ProjectContext, task_id: uuid.UUID) -> None:
    task = await _get_task(db, ctx, task_id)
    task.deleted_at = _now()
    await audit.record(
        db,
        action="task.deleted",
        resource_type="task",
        resource_id=task.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
    )
    if task.milestone_id:
        await db.flush()
        await _sync_milestone(db, ctx, task.milestone_id)


async def reorder(db: AsyncSession, ctx: ProjectContext, body: ReorderIn) -> None:
    ids = [item.id for item in body.items]
    tasks = {
        t.id: t
        for t in (
            await db.execute(
                select(Task).where(Task.project_id == ctx.project.id, Task.id.in_(ids))
            )
        ).scalars()
    }
    if len(tasks) != len(set(ids)):
        raise not_found()
    for item in body.items:
        tasks[item.id].position = item.position


# --- Checklist --------------------------------------------------------------------------


async def add_checklist_item(
    db: AsyncSession, ctx: ProjectContext, task_id: uuid.UUID, body: ChecklistItemIn
) -> TaskDetailOut:
    task = await _get_task(db, ctx, task_id)
    position = (
        await db.execute(
            select(func.coalesce(func.max(TaskChecklistItem.position), -1)).where(
                TaskChecklistItem.task_id == task.id
            )
        )
    ).scalar_one() + 1
    db.add(
        TaskChecklistItem(
            organization_id=ctx.organization_id,
            task_id=task.id,
            title=body.title.strip(),
            position=position,
        )
    )
    await db.flush()
    return await get_task(db, ctx, task.id)


async def _checklist_item(
    db: AsyncSession, ctx: ProjectContext, task_id: uuid.UUID, item_id: uuid.UUID
) -> TaskChecklistItem:
    await _get_task(db, ctx, task_id)
    item = await db.get(TaskChecklistItem, item_id)
    if item is None or item.task_id != task_id:
        raise not_found()
    return item


async def update_checklist_item(
    db: AsyncSession,
    ctx: ProjectContext,
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ChecklistItemUpdateIn,
) -> TaskDetailOut:
    item = await _checklist_item(db, ctx, task_id, item_id)
    if body.title is not None:
        item.title = body.title.strip()
    if body.is_done is not None:
        item.is_done = body.is_done
    await db.flush()
    return await get_task(db, ctx, task_id)


async def delete_checklist_item(
    db: AsyncSession, ctx: ProjectContext, task_id: uuid.UUID, item_id: uuid.UUID
) -> TaskDetailOut:
    item = await _checklist_item(db, ctx, task_id, item_id)
    await db.delete(item)
    await db.flush()
    return await get_task(db, ctx, task_id)


# --- Milestones -------------------------------------------------------------------------


async def list_milestones(db: AsyncSession, ctx: ProjectContext) -> list[MilestoneDetailOut]:
    counts = (
        select(
            Task.milestone_id,
            func.count().label("total"),
            func.count().filter(Task.status == TaskStatus.DONE).label("done"),
        )
        .where(Task.deleted_at.is_(None), Task.status != TaskStatus.CANCELLED)
        .group_by(Task.milestone_id)
        .subquery()
    )
    rows = await db.execute(
        select(Milestone, counts.c.total, counts.c.done)
        .outerjoin(counts, counts.c.milestone_id == Milestone.id)
        .where(Milestone.project_id == ctx.project.id)
        .order_by(Milestone.due_date.asc().nulls_last(), Milestone.position)
    )
    return [
        MilestoneDetailOut(
            id=m.id,
            title=m.title,
            due_date=m.due_date,
            completed_at=m.completed_at,
            visibility=m.visibility,
            position=m.position,
            task_total=total or 0,
            task_done=done or 0,
        )
        for m, total, done in rows.all()
    ]


async def create_milestone(
    db: AsyncSession, ctx: ProjectContext, body: MilestoneIn
) -> list[MilestoneDetailOut]:
    db.add(
        Milestone(
            organization_id=ctx.organization_id,
            project_id=ctx.project.id,
            title=body.title.strip(),
            due_date=body.due_date,
            visibility=body.visibility,
        )
    )
    await db.flush()
    return await list_milestones(db, ctx)


async def _milestone(db: AsyncSession, ctx: ProjectContext, milestone_id: uuid.UUID) -> Milestone:
    milestone = await db.get(Milestone, milestone_id)
    if milestone is None or milestone.project_id != ctx.project.id:
        raise not_found()
    return milestone


async def update_milestone(
    db: AsyncSession, ctx: ProjectContext, milestone_id: uuid.UUID, body: MilestoneUpdateIn
) -> list[MilestoneDetailOut]:
    milestone = await _milestone(db, ctx, milestone_id)
    fields = body.model_dump(exclude_unset=True)
    completed = fields.pop("completed", None)
    for key, value in fields.items():
        if value is not None or key == "due_date":
            setattr(milestone, key, value)
    if completed is True and milestone.completed_at is None:
        milestone.completed_at = _now()
        await record_activity(
            db,
            ctx,
            verb="milestone.completed",
            target_type="milestone",
            target_id=milestone.id,
            summary=milestone.title,
            visibility=milestone.visibility,
        )
    elif completed is False:
        milestone.completed_at = None
    await db.flush()
    return await list_milestones(db, ctx)


async def delete_milestone(db: AsyncSession, ctx: ProjectContext, milestone_id: uuid.UUID) -> None:
    milestone = await _milestone(db, ctx, milestone_id)
    await db.delete(milestone)  # tasks stay; their milestone_id is set to NULL by the FK


# --- Comments ---------------------------------------------------------------------------


async def _check_target(
    db: AsyncSession, ctx: ProjectContext, target_type: str, target_id: uuid.UUID
) -> str:
    """Validate a comment target and return a short label for the activity feed."""
    if target_type == "project":
        if target_id != ctx.project.id:
            raise not_found()
        return ctx.project.title
    if target_type == "moodboard_item":
        from app.moodboards.models import Moodboard, MoodboardItem

        row = (
            await db.execute(
                select(MoodboardItem, Moodboard.title)
                .join(Moodboard, Moodboard.id == MoodboardItem.board_id)
                .where(MoodboardItem.id == target_id, MoodboardItem.project_id == ctx.project.id)
            )
        ).one_or_none()
        if row is None:
            raise not_found()
        item, board_title = row
        return item.caption or f"Image on {board_title}"
    target: Task | Milestone | None = (
        await db.get(Task, target_id)
        if target_type == "task"
        else await db.get(Milestone, target_id)
    )
    if target is None or target.project_id != ctx.project.id:
        raise not_found()
    return target.title


def _comment_out(comment: Comment, author: str | None, ctx: ProjectContext) -> CommentOut:
    return CommentOut(
        id=comment.id,
        target_type=comment.target_type,
        target_id=comment.target_id,
        author_name=author,
        is_mine=comment.author_user_id == ctx.user.id,
        body=comment.body,
        visibility=comment.visibility,
        created_at=comment.created_at,
        edited_at=comment.edited_at,
    )


async def list_comments(
    db: AsyncSession, ctx: ProjectContext, target_type: str, target_id: uuid.UUID
) -> list[CommentOut]:
    rows = await db.execute(
        select(Comment, User.full_name)
        .outerjoin(User, User.id == Comment.author_user_id)
        .where(
            Comment.project_id == ctx.project.id,
            Comment.target_type == target_type,
            Comment.target_id == target_id,
        )
        .order_by(Comment.created_at)
    )
    return [_comment_out(c, name, ctx) for c, name in rows.all()]


async def add_comment(db: AsyncSession, ctx: ProjectContext, body: CommentIn) -> CommentOut:
    label = await _check_target(db, ctx, body.target_type, body.target_id)
    comment = Comment(
        organization_id=ctx.organization_id,
        project_id=ctx.project.id,
        target_type=body.target_type,
        target_id=body.target_id,
        author_user_id=ctx.user.id,
        body=body.body.strip(),
        visibility=body.visibility,
    )
    db.add(comment)
    await db.flush()
    await record_activity(
        db,
        ctx,
        verb="comment.created",
        target_type=body.target_type,
        target_id=body.target_id,
        summary=label,
        visibility=body.visibility,
    )
    if body.target_type == "moodboard_item":
        await notify.moodboard_commented(db, ctx, body.target_id, label)
    if body.target_type == "task":
        task = await _get_task(db, ctx, body.target_id)
        await notify.commented(
            db,
            ctx,
            task_id=task.id,
            title=task.title,
            assignee_membership_id=task.assignee_membership_id,
            assignee_type=task.assignee_type,
            shared=comment.visibility == Visibility.CLIENT,
        )
    return _comment_out(comment, ctx.user.full_name, ctx)


async def _comment(db: AsyncSession, ctx: ProjectContext, comment_id: uuid.UUID) -> Comment:
    comment = await db.get(Comment, comment_id)
    if comment is None or comment.project_id != ctx.project.id:
        raise not_found()
    return comment


async def update_comment(
    db: AsyncSession, ctx: ProjectContext, comment_id: uuid.UUID, body: CommentUpdateIn
) -> CommentOut:
    comment = await _comment(db, ctx, comment_id)
    if comment.author_user_id != ctx.user.id:
        raise ProblemError(403, "forbidden", "Not allowed", "You can only edit your own comments.")
    comment.body = body.body.strip()
    comment.edited_at = _now()
    await db.flush()
    return _comment_out(comment, ctx.user.full_name, ctx)


async def delete_comment(db: AsyncSession, ctx: ProjectContext, comment_id: uuid.UUID) -> None:
    comment = await _comment(db, ctx, comment_id)
    if comment.author_user_id != ctx.user.id and ctx.project_role != ADMIN_PROJECT_ROLE:
        raise ProblemError(
            403, "forbidden", "Not allowed", "You can only delete your own comments."
        )
    await db.delete(comment)
