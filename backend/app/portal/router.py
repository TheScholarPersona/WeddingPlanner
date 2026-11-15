import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile
from pydantic import Field

from app.authz.deps import CurrentUser, DbSession
from app.documents import service as document_service
from app.documents.files import read_upload
from app.documents.router import file_response
from app.events import service as event_service
from app.events.schemas import FeedCreatedOut, FeedOut
from app.jobs.queue import Jobs
from app.notifications import service as notification_service
from app.notifications.schemas import PreferencesIn, PreferencesOut
from app.portal import service
from app.portal.schemas import (
    PortalBudget,
    PortalCalendarItem,
    PortalChecklistUpdateIn,
    PortalComment,
    PortalDocument,
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


# --- Documents ------------------------------------------------------------------------------


@router.get(f"{K}/documents", response_model=list[PortalDocument])
async def documents(db: DbSession, access: PortalAccess = Access) -> list[PortalDocument]:
    return await service.documents(db, access)


@router.post(f"{K}/documents", response_model=list[PortalDocument], status_code=201)
async def upload_document(
    db: DbSession,
    jobs: Jobs,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=200)] = None,
    access: PortalAccess = Access,
) -> list[PortalDocument]:
    checked = await read_upload(file)
    await document_service.upload(
        db, access.ctx, jobs, checked, title=title, category="other", visibility="client"
    )
    return await service.documents(db, access)


@router.delete(f"{K}/documents/{{document_id}}", status_code=204)
async def delete_document(
    document_id: uuid.UUID, db: DbSession, access: PortalAccess = Access
) -> None:
    await document_service.delete(db, access.ctx, document_id)


@router.get(f"{K}/documents/{{document_id}}/download", response_class=Response)
async def download_document(
    document_id: uuid.UUID, db: DbSession, access: PortalAccess = Access
) -> Response:
    version, data = await document_service.download(db, access.ctx, document_id, None)
    return file_response(version, data)


# --- Calendar -------------------------------------------------------------------------------


@router.get(f"{K}/calendar", response_model=list[PortalCalendarItem])
async def calendar(
    db: DbSession, start: date, end: date, access: PortalAccess = Access
) -> list[PortalCalendarItem]:
    event_service.check_range(start, end, limit=400)
    return await service.calendar(db, access, start, end)


@router.get(f"{K}/calendar/feed", response_model=FeedOut)
async def get_feed(db: DbSession, access: PortalAccess = Access) -> FeedOut:
    return await event_service.get_feed(db, access.ctx)


@router.post(f"{K}/calendar/feed", response_model=FeedCreatedOut, status_code=201)
async def create_feed(db: DbSession, access: PortalAccess = Access) -> FeedCreatedOut:
    return await event_service.create_feed(db, access.ctx)


@router.delete(f"{K}/calendar/feed", status_code=204)
async def revoke_feed(db: DbSession, access: PortalAccess = Access) -> None:
    await event_service.revoke_feed(db, access.ctx)


# --- Notification settings ------------------------------------------------------------------


@router.get(f"{K}/notification-preferences", response_model=PreferencesOut)
async def get_preferences(db: DbSession, access: PortalAccess = Access) -> PreferencesOut:
    return await notification_service.get_preferences(db, access.ctx)


@router.patch(f"{K}/notification-preferences", response_model=PreferencesOut)
async def update_preferences(
    body: PreferencesIn, db: DbSession, access: PortalAccess = Access
) -> PreferencesOut:
    return await notification_service.update_preferences(db, access.ctx, body)
