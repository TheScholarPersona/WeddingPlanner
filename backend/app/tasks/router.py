import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query, Response, status

from app.authz.deps import DbSession, OrgContext, ProjectContext, require, require_project
from app.authz.permissions import Perm, ProjectPerm
from app.tasks import service
from app.tasks.schemas import (
    ActivityPageOut,
    ChecklistItemIn,
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

router = APIRouter(prefix="/orgs/{org_id}", tags=["tasks"])
P = "/projects/{project_id}"
T = f"{P}/tasks/{{task_id}}"


def _etag(response: Response, task: TaskDetailOut) -> TaskDetailOut:
    response.headers["ETag"] = f'"{task.version}"'
    return task


@router.get("/tasks", response_model=list[MyTaskOut])
async def my_tasks(
    db: DbSession,
    ctx: OrgContext = require(Perm.MY_TASKS),
    status: Literal["open", "done"] = "open",
) -> list[MyTaskOut]:
    return await service.my_tasks(db, ctx, status)


@router.get(f"{P}/tasks", response_model=list[TaskOut])
async def list_tasks(
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_READ),
    status: Literal["open", "in_progress", "done", "cancelled"] | None = None,
    assignee: Annotated[str | None, Query(pattern=r"^(me|client|[0-9a-f-]{36})$")] = None,
    milestone_id: uuid.UUID | None = None,
    visibility: Literal["internal", "client"] | None = None,
) -> list[TaskOut]:
    return await service.list_tasks(
        db, ctx, status=status, assignee=assignee, milestone_id=milestone_id, visibility=visibility
    )


@router.post(f"{P}/tasks", response_model=TaskDetailOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskIn,
    response: Response,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_WRITE),
) -> TaskDetailOut:
    return _etag(response, await service.create_task(db, ctx, body))


@router.post(f"{P}/tasks/reorder", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_tasks(
    body: ReorderIn, db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.TASKS_WRITE)
) -> None:
    await service.reorder(db, ctx, body)


@router.get(T, response_model=TaskDetailOut)
async def get_task(
    task_id: uuid.UUID,
    response: Response,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_READ),
) -> TaskDetailOut:
    return _etag(response, await service.get_task(db, ctx, task_id))


@router.patch(T, response_model=TaskDetailOut)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdateIn,
    response: Response,
    db: DbSession,
    if_match: Annotated[str | None, Header()] = None,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_WRITE),
) -> TaskDetailOut:
    return _etag(response, await service.update_task(db, ctx, task_id, body, if_match))


@router.post(f"{T}/complete", response_model=TaskDetailOut)
async def complete_task(
    task_id: uuid.UUID,
    response: Response,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_WRITE),
) -> TaskDetailOut:
    return _etag(response, await service.set_done(db, ctx, task_id, True))


@router.post(f"{T}/reopen", response_model=TaskDetailOut)
async def reopen_task(
    task_id: uuid.UUID,
    response: Response,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_WRITE),
) -> TaskDetailOut:
    return _etag(response, await service.set_done(db, ctx, task_id, False))


@router.delete(T, status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_WRITE),
) -> None:
    await service.delete_task(db, ctx, task_id)


@router.post(f"{T}/checklist", response_model=TaskDetailOut, status_code=201)
async def add_checklist_item(
    task_id: uuid.UUID,
    body: ChecklistItemIn,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_WRITE),
) -> TaskDetailOut:
    return await service.add_checklist_item(db, ctx, task_id, body)


@router.patch(f"{T}/checklist/{{item_id}}", response_model=TaskDetailOut)
async def update_checklist_item(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ChecklistItemUpdateIn,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_WRITE),
) -> TaskDetailOut:
    return await service.update_checklist_item(db, ctx, task_id, item_id, body)


@router.delete(f"{T}/checklist/{{item_id}}", response_model=TaskDetailOut)
async def delete_checklist_item(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_WRITE),
) -> TaskDetailOut:
    return await service.delete_checklist_item(db, ctx, task_id, item_id)


@router.get(f"{P}/milestones", response_model=list[MilestoneDetailOut])
async def list_milestones(
    db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.TASKS_READ)
) -> list[MilestoneDetailOut]:
    return await service.list_milestones(db, ctx)


@router.post(f"{P}/milestones", response_model=list[MilestoneDetailOut], status_code=201)
async def create_milestone(
    body: MilestoneIn, db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.TASKS_WRITE)
) -> list[MilestoneDetailOut]:
    return await service.create_milestone(db, ctx, body)


@router.patch(f"{P}/milestones/{{milestone_id}}", response_model=list[MilestoneDetailOut])
async def update_milestone(
    milestone_id: uuid.UUID,
    body: MilestoneUpdateIn,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_WRITE),
) -> list[MilestoneDetailOut]:
    return await service.update_milestone(db, ctx, milestone_id, body)


@router.delete(f"{P}/milestones/{{milestone_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_milestone(
    milestone_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_WRITE),
) -> None:
    await service.delete_milestone(db, ctx, milestone_id)


@router.get(f"{P}/comments", response_model=list[CommentOut])
async def list_comments(
    target_type: Literal["project", "task", "milestone"],
    target_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.TASKS_READ),
) -> list[CommentOut]:
    return await service.list_comments(db, ctx, target_type, target_id)


@router.post(f"{P}/comments", response_model=CommentOut, status_code=201)
async def add_comment(
    body: CommentIn, db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.COMMENT)
) -> CommentOut:
    return await service.add_comment(db, ctx, body)


@router.patch(f"{P}/comments/{{comment_id}}", response_model=CommentOut)
async def update_comment(
    comment_id: uuid.UUID,
    body: CommentUpdateIn,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.COMMENT),
) -> CommentOut:
    return await service.update_comment(db, ctx, comment_id, body)


@router.delete(f"{P}/comments/{{comment_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.COMMENT),
) -> None:
    await service.delete_comment(db, ctx, comment_id)


@router.get(f"{P}/activity", response_model=ActivityPageOut)
async def activity(
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.READ),
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: uuid.UUID | None = None,
) -> ActivityPageOut:
    return await service.list_activity(db, ctx, limit, cursor)
