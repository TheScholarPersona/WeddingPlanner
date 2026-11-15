import uuid

from fastapi import APIRouter
from pydantic import Field

from app.authz.deps import CurrentUser, DbSession
from app.portal import service
from app.portal.schemas import (
    PortalBudget,
    PortalChecklistUpdateIn,
    PortalComment,
    PortalOverview,
    PortalProjectSummary,
    PortalTask,
)
from app.portal.schemas import PortalCommentIn as _CommentIn
from app.portal.service import Access, PortalAccess

router = APIRouter(prefix="/portal", tags=["portal"])
K = "/projects/{project_id}"


class CommentIn(_CommentIn):
    body: str = Field(min_length=1, max_length=5000)


@router.get("/projects", response_model=list[PortalProjectSummary])
async def projects(db: DbSession, auth: CurrentUser) -> list[PortalProjectSummary]:
    return await service.list_projects(db, auth)


@router.get(K, response_model=PortalOverview)
async def overview(db: DbSession, access: PortalAccess = Access) -> PortalOverview:
    return await service.overview(db, access)


@router.get(f"{K}/tasks", response_model=list[PortalTask])
async def tasks(db: DbSession, access: PortalAccess = Access) -> list[PortalTask]:
    return await service.task_list(db, access)


@router.post(f"{K}/tasks/{{task_id}}/complete", response_model=list[PortalTask])
async def complete(
    task_id: uuid.UUID, db: DbSession, access: PortalAccess = Access
) -> list[PortalTask]:
    return await service.set_done(db, access, task_id, True)


@router.post(f"{K}/tasks/{{task_id}}/reopen", response_model=list[PortalTask])
async def reopen(
    task_id: uuid.UUID, db: DbSession, access: PortalAccess = Access
) -> list[PortalTask]:
    return await service.set_done(db, access, task_id, False)


@router.patch(f"{K}/tasks/{{task_id}}/checklist/{{item_id}}", response_model=list[PortalTask])
async def tick(
    task_id: uuid.UUID,
    item_id: uuid.UUID,
    body: PortalChecklistUpdateIn,
    db: DbSession,
    access: PortalAccess = Access,
) -> list[PortalTask]:
    return await service.tick(db, access, task_id, item_id, body.is_done)


@router.get(f"{K}/tasks/{{task_id}}/comments", response_model=list[PortalComment])
async def comments(
    task_id: uuid.UUID, db: DbSession, access: PortalAccess = Access
) -> list[PortalComment]:
    return await service.comments(db, access, task_id)


@router.post(f"{K}/tasks/{{task_id}}/comments", response_model=list[PortalComment], status_code=201)
async def add_comment(
    task_id: uuid.UUID, body: CommentIn, db: DbSession, access: PortalAccess = Access
) -> list[PortalComment]:
    return await service.add_comment(db, access, task_id, body.body)


@router.get(f"{K}/budget", response_model=PortalBudget)
async def budget(db: DbSession, access: PortalAccess = Access) -> PortalBudget:
    return await service.budget(db, access)
