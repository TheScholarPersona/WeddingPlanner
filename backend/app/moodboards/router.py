import uuid
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Header, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.authz.deps import DbSession, ProjectContext, require_project
from app.authz.permissions import ProjectPerm
from app.jobs.queue import Jobs
from app.moodboards import images, pdf, service
from app.moodboards.models import MoodboardItem
from app.moodboards.schemas import (
    BoardIn,
    BoardOut,
    BoardSummaryOut,
    BoardUpdateIn,
    ItemUpdateIn,
    PortalBoard,
    PortalBoardSummary,
    ReorderIn,
    SectionIn,
)
from app.portal.service import Access, PortalAccess
from app.tasks import service as tasks
from app.tasks.schemas import CommentIn, CommentOut

router = APIRouter(tags=["moodboards"])
P = "/orgs/{org_id}/projects/{project_id}/moodboards"
K = "/portal/projects/{project_id}/moodboards"
B = "/{board_id}"
IfMatch = Annotated[str | None, Header()]
Size = Literal["thumb", "display", "original"]
Read = require_project(ProjectPerm.MOODBOARDS_READ)
Write = require_project(ProjectPerm.MOODBOARDS_WRITE)


def image_response(item: MoodboardItem, data: bytes, content_type: str, size: str) -> Response:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    }
    if size == "original":
        headers["Content-Disposition"] = "attachment"
        headers["Cache-Control"] = "private, no-store"
    else:
        # Derived versions never change for an item id; let the browser keep them briefly.
        headers["Cache-Control"] = "private, max-age=3600"
    return Response(content=data, media_type=content_type, headers=headers)


# --- Planner ------------------------------------------------------------------------------


@router.get(P, response_model=list[BoardSummaryOut])
async def list_boards(db: DbSession, ctx: ProjectContext = Read) -> list[BoardSummaryOut]:
    return await service.list_boards(db, ctx)


@router.post(P, response_model=BoardOut, status_code=status.HTTP_201_CREATED)
async def create_board(body: BoardIn, db: DbSession, ctx: ProjectContext = Write) -> BoardOut:
    return await service.create_board(db, ctx, body)


@router.get(P + B, response_model=BoardOut)
async def get_board(board_id: uuid.UUID, db: DbSession, ctx: ProjectContext = Read) -> BoardOut:
    return await service.get_board(db, ctx, board_id)


@router.patch(P + B, response_model=BoardOut)
async def update_board(
    board_id: uuid.UUID,
    body: BoardUpdateIn,
    db: DbSession,
    if_match: IfMatch = None,
    ctx: ProjectContext = Write,
) -> BoardOut:
    return await service.update_board(db, ctx, board_id, body, if_match)


@router.delete(P + B, status_code=status.HTTP_204_NO_CONTENT)
async def delete_board(
    board_id: uuid.UUID,
    db: DbSession,
    ctx: ProjectContext = require_project(ProjectPerm.MOODBOARDS_DELETE),
) -> None:
    await service.delete_board(db, ctx, board_id)


@router.post(P + B + "/sections", response_model=BoardOut, status_code=201)
async def add_section(
    board_id: uuid.UUID, body: SectionIn, db: DbSession, ctx: ProjectContext = Write
) -> BoardOut:
    return await service.add_section(db, ctx, board_id, body)


@router.patch(P + B + "/sections/{section_id}", response_model=BoardOut)
async def rename_section(
    board_id: uuid.UUID,
    section_id: uuid.UUID,
    body: SectionIn,
    db: DbSession,
    ctx: ProjectContext = Write,
) -> BoardOut:
    return await service.rename_section(db, ctx, board_id, section_id, body)


@router.delete(P + B + "/sections/{section_id}", response_model=BoardOut)
async def delete_section(
    board_id: uuid.UUID, section_id: uuid.UUID, db: DbSession, ctx: ProjectContext = Write
) -> BoardOut:
    return await service.delete_section(db, ctx, board_id, section_id)


@router.post(P + B + "/reorder", response_model=BoardOut)
async def reorder(
    board_id: uuid.UUID, body: ReorderIn, db: DbSession, ctx: ProjectContext = Write
) -> BoardOut:
    return await service.reorder(db, ctx, board_id, body)


@router.post(P + B + "/items", response_model=BoardOut, status_code=201)
async def upload(
    board_id: uuid.UUID,
    db: DbSession,
    jobs: Jobs,
    files: Annotated[list[UploadFile], File()],
    section_id: Annotated[uuid.UUID | None, Form()] = None,
    caption: Annotated[str | None, Form(max_length=300)] = None,
    ctx: ProjectContext = Write,
) -> BoardOut:
    checked = await images.read_images(files, ctx.user.id)
    return await service.upload(db, ctx, jobs, board_id, section_id, checked, caption)


@router.patch(P + B + "/items/{item_id}", response_model=BoardOut)
async def update_item(
    board_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ItemUpdateIn,
    db: DbSession,
    ctx: ProjectContext = Write,
) -> BoardOut:
    return await service.update_item(db, ctx, board_id, item_id, body)


@router.delete(P + B + "/items/{item_id}", response_model=BoardOut)
async def delete_item(
    board_id: uuid.UUID, item_id: uuid.UUID, db: DbSession, ctx: ProjectContext = Write
) -> BoardOut:
    return await service.delete_item(db, ctx, board_id, item_id)


@router.put(P + B + "/items/{item_id}/heart", response_model=BoardOut)
async def heart(
    board_id: uuid.UUID, item_id: uuid.UUID, db: DbSession, ctx: ProjectContext = Read
) -> BoardOut:
    return await service.set_heart(db, ctx, board_id, item_id, True)


@router.delete(P + B + "/items/{item_id}/heart", response_model=BoardOut)
async def unheart(
    board_id: uuid.UUID, item_id: uuid.UUID, db: DbSession, ctx: ProjectContext = Read
) -> BoardOut:
    return await service.set_heart(db, ctx, board_id, item_id, False)


@router.get(P + B + "/items/{item_id}/image", response_class=Response)
async def item_image(
    board_id: uuid.UUID,
    item_id: uuid.UUID,
    db: DbSession,
    size: Size = "display",
    ctx: ProjectContext = Read,
) -> Response:
    item, data, content_type = await service.image(db, ctx, board_id, item_id, size)
    return image_response(item, data, content_type, size)


@router.get(P + B + "/export.pdf", response_class=Response)
async def export_pdf(
    board_id: uuid.UUID,
    db: DbSession,
    selected_only: bool = True,
    section: uuid.UUID | None = None,
    include_couple: bool = False,
    ctx: ProjectContext = Read,
) -> Response:
    """PDF for vendors; the planner sends it on (vendors get no access to the platform)."""
    filename, data = await pdf.render(
        db,
        ctx,
        board_id,
        selected_only=selected_only,
        section_id=section,
        include_couple=include_couple,
    )
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# --- Portal (the couple) ------------------------------------------------------------------


def _portal_summary(board: BoardSummaryOut) -> PortalBoardSummary:
    return PortalBoardSummary(
        id=board.id,
        title=board.title,
        from_couple=board.created_by_type == "client",
        palette=board.palette,
        item_count=board.item_count,
        selected_count=board.selected_count,
        preview=board.preview,
        updated_at=board.updated_at,
    )


def _portal(board: BoardOut) -> PortalBoard:
    return PortalBoard(
        **_portal_summary(board).model_dump(),
        sections=board.sections,
        items=board.items,
        can_manage=board.can_manage,
        can_delete=board.can_delete,
    )


@router.get(K, response_model=list[PortalBoardSummary])
async def portal_boards(db: DbSession, access: PortalAccess = Access) -> list[PortalBoardSummary]:
    return [_portal_summary(b) for b in await service.list_boards(db, access.ctx)]


@router.post(K, response_model=PortalBoard, status_code=201)
async def portal_create(body: BoardIn, db: DbSession, access: PortalAccess = Access) -> PortalBoard:
    return _portal(await service.create_board(db, access.ctx, body))


@router.get(K + B, response_model=PortalBoard)
async def portal_board(
    board_id: uuid.UUID, db: DbSession, access: PortalAccess = Access
) -> PortalBoard:
    return _portal(await service.get_board(db, access.ctx, board_id))


@router.patch(K + B, response_model=PortalBoard)
async def portal_rename(
    board_id: uuid.UUID,
    body: BoardUpdateIn,
    db: DbSession,
    if_match: IfMatch = None,
    access: PortalAccess = Access,
) -> PortalBoard:
    return _portal(await service.update_board(db, access.ctx, board_id, body, if_match))


@router.delete(K + B, status_code=status.HTTP_204_NO_CONTENT)
async def portal_delete(board_id: uuid.UUID, db: DbSession, access: PortalAccess = Access) -> None:
    await service.delete_board(db, access.ctx, board_id)


@router.post(K + B + "/sections", response_model=PortalBoard, status_code=201)
async def portal_add_section(
    board_id: uuid.UUID, body: SectionIn, db: DbSession, access: PortalAccess = Access
) -> PortalBoard:
    return _portal(await service.add_section(db, access.ctx, board_id, body))


@router.post(K + B + "/reorder", response_model=PortalBoard)
async def portal_reorder(
    board_id: uuid.UUID, body: ReorderIn, db: DbSession, access: PortalAccess = Access
) -> PortalBoard:
    return _portal(await service.reorder(db, access.ctx, board_id, body))


@router.post(K + B + "/items", response_model=PortalBoard, status_code=201)
async def portal_upload(
    board_id: uuid.UUID,
    db: DbSession,
    jobs: Jobs,
    files: Annotated[list[UploadFile], File()],
    section_id: Annotated[uuid.UUID | None, Form()] = None,
    caption: Annotated[str | None, Form(max_length=300)] = None,
    access: PortalAccess = Access,
) -> PortalBoard:
    checked = await images.read_images(files, access.ctx.user.id)
    return _portal(
        await service.upload(db, access.ctx, jobs, board_id, section_id, checked, caption)
    )


@router.patch(K + B + "/items/{item_id}", response_model=PortalBoard)
async def portal_update_item(
    board_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ItemUpdateIn,
    db: DbSession,
    access: PortalAccess = Access,
) -> PortalBoard:
    return _portal(await service.update_item(db, access.ctx, board_id, item_id, body))


@router.delete(K + B + "/items/{item_id}", response_model=PortalBoard)
async def portal_delete_item(
    board_id: uuid.UUID, item_id: uuid.UUID, db: DbSession, access: PortalAccess = Access
) -> PortalBoard:
    return _portal(await service.delete_item(db, access.ctx, board_id, item_id))


@router.put(K + B + "/items/{item_id}/heart", response_model=PortalBoard)
async def portal_heart(
    board_id: uuid.UUID, item_id: uuid.UUID, db: DbSession, access: PortalAccess = Access
) -> PortalBoard:
    return _portal(await service.set_heart(db, access.ctx, board_id, item_id, True))


@router.delete(K + B + "/items/{item_id}/heart", response_model=PortalBoard)
async def portal_unheart(
    board_id: uuid.UUID, item_id: uuid.UUID, db: DbSession, access: PortalAccess = Access
) -> PortalBoard:
    return _portal(await service.set_heart(db, access.ctx, board_id, item_id, False))


@router.get(K + B + "/items/{item_id}/image", response_class=Response)
async def portal_image(
    board_id: uuid.UUID,
    item_id: uuid.UUID,
    db: DbSession,
    size: Literal["thumb", "display"] = "display",
    access: PortalAccess = Access,
) -> Response:
    item, data, content_type = await service.image(db, access.ctx, board_id, item_id, size)
    return image_response(item, data, content_type, size)


@router.get(K + B + "/items/{item_id}/comments", response_model=list[CommentOut])
async def portal_comments(
    board_id: uuid.UUID, item_id: uuid.UUID, db: DbSession, access: PortalAccess = Access
) -> list[CommentOut]:
    await service.get_item(db, access.ctx, board_id, item_id)
    return await tasks.list_comments(db, access.ctx, "moodboard_item", item_id)


class PortalItemCommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


@router.post(K + B + "/items/{item_id}/comments", response_model=CommentOut, status_code=201)
async def portal_comment(
    board_id: uuid.UUID,
    item_id: uuid.UUID,
    body: PortalItemCommentIn,
    db: DbSession,
    access: PortalAccess = Access,
) -> CommentOut:
    await service.get_item(db, access.ctx, board_id, item_id)
    return await tasks.add_comment(
        db,
        access.ctx,
        # The couple's comments are always visible to the couple.
        CommentIn(
            target_type="moodboard_item", target_id=item_id, body=body.body, visibility="client"
        ),
    )
