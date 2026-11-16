import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Header, Response, UploadFile, status

from app.authz.deps import DbSession, ProjectContext, require_project
from app.authz.permissions import ProjectPerm
from app.documents import service
from app.documents.files import read_upload
from app.documents.models import DocumentVersion
from app.documents.schemas import (
    Category,
    DocumentDetailOut,
    DocumentOut,
    DocumentUpdateIn,
    VisibilityT,
)
from app.jobs.queue import Jobs

router = APIRouter(prefix="/orgs/{org_id}/projects/{project_id}/documents", tags=["documents"])
IfMatch = Annotated[str | None, Header()]


def file_response(version: DocumentVersion, data: bytes) -> Response:
    """Always a download, never rendered by the browser in the app's origin."""
    ascii_name = version.filename.encode("ascii", "replace").decode().replace("?", "_")
    return Response(
        content=data,
        media_type=version.content_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(version.filename)}"
            ),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    db: DbSession, ctx: ProjectContext = require_project(ProjectPerm.DOCUMENTS_READ)
) -> list[DocumentOut]:
    return await service.list_documents(db, ctx)


@router.post("", response_model=DocumentDetailOut, status_code=status.HTTP_201_CREATED)
async def upload(
    db: DbSession,
    jobs: Jobs,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=200)] = None,
    category: Annotated[Category, Form()] = "other",
    visibility: Annotated[VisibilityT, Form()] = "internal",
    ctx: ProjectContext = require_project(ProjectPerm.DOCUMENTS_WRITE),
) -> DocumentDetailOut:
    checked = await read_upload(file, ctx.user.id)
    return await service.upload(
        db, ctx, jobs, checked, title=title, category=category, visibility=visibility
    )


@router.get("/{document_id}", response_model=DocumentDetailOut)
async def get_document(
    document_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.DOCUMENTS_READ),
) -> DocumentDetailOut:
    return await service.get_document(db, ctx, document_id)


@router.patch("/{document_id}", response_model=DocumentDetailOut)
async def update_document(
    document_id: uuid.UUID,
    body: DocumentUpdateIn,
    db: DbSession,
    if_match: IfMatch = None,
    ctx: ProjectContext = require_project(ProjectPerm.DOCUMENTS_WRITE),
) -> DocumentDetailOut:
    return await service.update(db, ctx, document_id, body, if_match)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.DOCUMENTS_WRITE),
) -> None:
    await service.delete(db, ctx, document_id)


@router.post(
    "/{document_id}/versions", response_model=DocumentDetailOut, status_code=status.HTTP_201_CREATED
)
async def add_version(
    document_id: uuid.UUID,
    db: DbSession,
    jobs: Jobs,
    file: Annotated[UploadFile, File()],
    ctx: ProjectContext = require_project(ProjectPerm.DOCUMENTS_WRITE),
) -> DocumentDetailOut:
    checked = await read_upload(file, ctx.user.id)
    return await service.add_version(db, ctx, jobs, document_id, checked)


@router.get("/{document_id}/download", response_class=Response)
async def download(
    document_id: uuid.UUID,
    db: DbSession,
    version: uuid.UUID | None = None,
    ctx: ProjectContext = require_project(ProjectPerm.DOCUMENTS_READ),
) -> Response:
    row, data = await service.download(db, ctx, document_id, version)
    return file_response(row, data)
