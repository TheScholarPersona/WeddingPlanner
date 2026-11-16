"""Moodboards: planner and couple collect images per wedding, the planner narrows them down.

All reads run under row-level security; couples (project role "client") only see boards shared
with them. The rules below add what RLS cannot express: couples change only their own boards
and images, and only the team selects, discards, shares or writes internal notes.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from arq import Retry
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.models import User
from app.authz.deps import FORBIDDEN, ProjectContext, not_found
from app.authz.permissions import ProjectPerm
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.ids import uuid7
from app.core.versioning import check_version
from app.db.session import get_sessionmaker
from app.db.tenant import set_tenant_context
from app.documents import scanner
from app.documents.storage import get_storage
from app.jobs.queue import PendingJobs
from app.moodboards import images
from app.moodboards.models import (
    TEMPLATE_SECTIONS,
    ItemStatus,
    Moodboard,
    MoodboardItem,
    MoodboardReaction,
    MoodboardSection,
)
from app.moodboards.schemas import (
    BoardIn,
    BoardOut,
    BoardSummaryOut,
    BoardUpdateIn,
    ItemOut,
    ItemUpdateIn,
    ReorderIn,
    SectionIn,
    SectionOut,
)
from app.notifications import service as notify
from app.projects.models import ProjectRole
from app.tasks.models import Comment
from app.tasks.service import record_activity

MAX_ITEMS_PER_WEDDING = 300
MAX_BOARDS_PER_WEDDING = 30
MAX_SECTIONS_PER_BOARD = 20


def _now() -> datetime:
    return datetime.now(UTC)


def is_client(ctx: ProjectContext) -> bool:
    return ctx.project_role == ProjectRole.CLIENT


def _can_write(ctx: ProjectContext) -> bool:
    return is_client(ctx) or ctx.can(ProjectPerm.MOODBOARDS_WRITE)


def _require_write(ctx: ProjectContext) -> None:
    if not _can_write(ctx):
        raise FORBIDDEN


def _owns_board(ctx: ProjectContext, board: Moodboard) -> bool:
    return board.created_by_type == "client" and board.created_by == ctx.user.id


def _manages(ctx: ProjectContext, board: Moodboard) -> bool:
    """Rename, add sections, reorder: the team (with write access) or the couple's own boards."""
    return _owns_board(ctx, board) if is_client(ctx) else ctx.can(ProjectPerm.MOODBOARDS_WRITE)


def _can_edit_item(ctx: ProjectContext, item: MoodboardItem) -> bool:
    if is_client(ctx):
        return item.uploaded_by_type == "client" and item.uploaded_by == ctx.user.id
    return ctx.can(ProjectPerm.MOODBOARDS_WRITE)


# --- Reading ------------------------------------------------------------------------------


async def _board(db: AsyncSession, ctx: ProjectContext, board_id: uuid.UUID) -> Moodboard:
    board = (
        await db.execute(
            select(Moodboard).where(
                Moodboard.id == board_id, Moodboard.project_id == ctx.project.id
            )
        )
    ).scalar_one_or_none()
    if board is None:
        raise not_found()
    return board


async def _counts(db: AsyncSession, board_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    result: dict[uuid.UUID, dict[str, Any]] = {
        b: {"items": 0, "selected": 0, "preview": []} for b in board_ids
    }
    if not board_ids:
        return result
    rows = await db.execute(
        select(
            MoodboardItem.board_id, MoodboardItem.id, MoodboardItem.status, MoodboardItem.thumb_key
        )
        .where(MoodboardItem.board_id.in_(board_ids))
        # Selected images first, then the board's own order.
        .order_by(MoodboardItem.status != ItemStatus.SELECTED, MoodboardItem.position)
    )
    for board_id, item_id, status, thumb in rows.all():
        if status == ItemStatus.DISCARDED:
            continue
        counts = result[board_id]
        counts["items"] += 1
        counts["selected"] += status == ItemStatus.SELECTED
        if thumb and len(counts["preview"]) < 4:
            counts["preview"].append(item_id)
    return result


def _summary_fields(board: Moodboard, counts: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": board.id,
        "title": board.title,
        "palette": list(board.palette or []),
        "item_count": counts["items"],
        "selected_count": counts["selected"],
        "preview": counts["preview"],
        "updated_at": board.updated_at,
    }


async def list_boards(db: AsyncSession, ctx: ProjectContext) -> list[BoardSummaryOut]:
    boards = list(
        (
            await db.execute(
                select(Moodboard)
                .where(Moodboard.project_id == ctx.project.id)
                .order_by(Moodboard.position, Moodboard.created_at)
            )
        ).scalars()
    )
    counts = await _counts(db, [b.id for b in boards])
    return [
        BoardSummaryOut(
            **_summary_fields(b, counts[b.id]),
            visibility=b.visibility,
            created_by_type=b.created_by_type,
        )
        for b in boards
    ]


async def _items(db: AsyncSession, ctx: ProjectContext, board: Moodboard) -> list[ItemOut]:
    rows = (
        await db.execute(
            select(MoodboardItem, User.full_name)
            .outerjoin(User, User.id == MoodboardItem.uploaded_by)
            .where(MoodboardItem.board_id == board.id)
            .order_by(MoodboardItem.position, MoodboardItem.created_at)
        )
    ).all()
    ids = [i.id for i, _ in rows]
    hearts: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)
    comments: dict[uuid.UUID, int] = defaultdict(int)
    if ids:
        for item_id, user_id, name in (
            await db.execute(
                select(MoodboardReaction.item_id, MoodboardReaction.user_id, User.full_name)
                .join(User, User.id == MoodboardReaction.user_id)
                .where(MoodboardReaction.item_id.in_(ids))
                .order_by(MoodboardReaction.created_at)
            )
        ).all():
            hearts[item_id].append((user_id, name))
        for target_id, n in (
            await db.execute(
                select(Comment.target_id, func.count())
                .where(Comment.target_type == "moodboard_item", Comment.target_id.in_(ids))
                .group_by(Comment.target_id)
            )
        ).all():
            comments[target_id] = n
    return [
        ItemOut(
            id=item.id,
            section_id=item.section_id,
            caption=item.caption,
            status=item.status,
            width=item.width,
            height=item.height,
            ready=item.processed_at is not None,
            scan_status=item.scan_status,
            uploaded_by_name=name,
            uploaded_by_type=item.uploaded_by_type,
            can_edit=_can_edit_item(ctx, item),
            hearts=len(hearts[item.id]),
            hearted_by_me=any(u == ctx.user.id for u, _ in hearts[item.id]),
            heart_names=[n for _, n in hearts[item.id]],
            comment_count=comments[item.id],
            created_at=item.created_at,
        )
        for item, name in rows
    ]


async def _can_delete_board(db: AsyncSession, ctx: ProjectContext, board: Moodboard) -> bool:
    if not is_client(ctx):
        return ctx.can(ProjectPerm.MOODBOARDS_DELETE)
    if not _owns_board(ctx, board):
        return False
    foreign = (
        await db.execute(
            select(func.count())
            .select_from(MoodboardItem)
            .where(
                MoodboardItem.board_id == board.id,
                (MoodboardItem.uploaded_by != ctx.user.id)
                | (MoodboardItem.uploaded_by_type != "client"),
            )
        )
    ).scalar_one()
    return foreign == 0


async def get_board(db: AsyncSession, ctx: ProjectContext, board_id: uuid.UUID) -> BoardOut:
    board = await _board(db, ctx, board_id)
    counts = (await _counts(db, [board.id]))[board.id]
    sections = (
        await db.execute(
            select(MoodboardSection)
            .where(MoodboardSection.board_id == board.id)
            .order_by(MoodboardSection.position, MoodboardSection.created_at)
        )
    ).scalars()
    return BoardOut(
        **_summary_fields(board, counts),
        visibility=board.visibility,
        created_by_type=board.created_by_type,
        version=board.version,
        notes_internal=None if is_client(ctx) else board.notes_internal,
        sections=[SectionOut(id=s.id, title=s.title) for s in sections],
        items=await _items(db, ctx, board),
        can_manage=_manages(ctx, board),
        can_delete=await _can_delete_board(db, ctx, board),
    )


# --- Boards and sections ------------------------------------------------------------------


async def create_board(db: AsyncSession, ctx: ProjectContext, body: BoardIn) -> BoardOut:
    _require_write(ctx)
    count = (
        await db.execute(
            select(func.count())
            .select_from(Moodboard)
            .where(Moodboard.project_id == ctx.project.id)
        )
    ).scalar_one()
    if count >= MAX_BOARDS_PER_WEDDING:
        raise ProblemError(
            409, "too_many_boards", "Too many boards", "A wedding can have up to 30 boards."
        )
    client = is_client(ctx)
    board = Moodboard(
        organization_id=ctx.organization_id,
        project_id=ctx.project.id,
        title=body.title.strip(),
        visibility="client" if client else body.visibility,
        created_by_type="client" if client else "team",
        created_by=ctx.user.id,
        palette=[],
        position=count,
    )
    db.add(board)
    await db.flush()
    if body.from_template:
        for position, title in enumerate(TEMPLATE_SECTIONS):
            db.add(
                MoodboardSection(
                    organization_id=ctx.organization_id,
                    project_id=ctx.project.id,
                    board_id=board.id,
                    title=title,
                    position=position,
                )
            )
        await db.flush()
    await record_activity(
        db,
        ctx,
        verb="moodboard.created",
        target_type="moodboard",
        target_id=board.id,
        summary=board.title,
        visibility=board.visibility,
    )
    return await get_board(db, ctx, board.id)


async def update_board(
    db: AsyncSession,
    ctx: ProjectContext,
    board_id: uuid.UUID,
    body: BoardUpdateIn,
    if_match: str | None,
) -> BoardOut:
    board = await _board(db, ctx, board_id)
    if not _manages(ctx, board):
        raise FORBIDDEN
    check_version(board.version, if_match, "board")
    fields = body.model_dump(exclude_unset=True)
    if is_client(ctx) and set(fields) - {"title"}:
        raise FORBIDDEN  # couples rename their own boards; sharing, palette, notes are the team's
    if board.created_by_type == "client" and fields.get("visibility") == "internal":
        raise ProblemError(
            409,
            "couple_board",
            "Board belongs to the couple",
            "Boards the couple created stay shared with them.",
        )
    old_visibility = board.visibility
    if fields.get("title"):
        board.title = fields["title"].strip()
    if fields.get("visibility"):
        board.visibility = fields["visibility"]
    if "palette" in fields and fields["palette"] is not None:
        board.palette = [c.lower() for c in fields["palette"]]
    if "notes_internal" in fields:
        board.notes_internal = (fields["notes_internal"] or "").strip() or None
    board.version += 1
    board.updated_at = _now()
    await db.flush()
    if old_visibility != board.visibility:
        await audit.record(
            db,
            action="moodboard.shared_with_client"
            if board.visibility == "client"
            else "moodboard.unshared",
            resource_type="moodboard",
            resource_id=board.id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.user.id,
            changes={"visibility": {"old": old_visibility, "new": board.visibility}},
        )
    return await get_board(db, ctx, board.id)


async def delete_board(db: AsyncSession, ctx: ProjectContext, board_id: uuid.UUID) -> None:
    board = await _board(db, ctx, board_id)
    if not await _can_delete_board(db, ctx, board):
        raise FORBIDDEN
    keys = await _storage_keys(db, MoodboardItem.board_id == board.id)
    images_count = (
        await db.execute(
            select(func.count())
            .select_from(MoodboardItem)
            .where(MoodboardItem.board_id == board.id)
        )
    ).scalar_one()
    await audit.record(
        db,
        action="moodboard.deleted",
        resource_type="moodboard",
        resource_id=board.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"title": {"old": board.title}, "images": {"old": images_count}},
    )
    await db.delete(board)
    await db.flush()
    await _delete_files(keys)


async def add_section(
    db: AsyncSession, ctx: ProjectContext, board_id: uuid.UUID, body: SectionIn
) -> BoardOut:
    board = await _board(db, ctx, board_id)
    if not _manages(ctx, board):
        raise FORBIDDEN
    count = (
        await db.execute(
            select(func.count())
            .select_from(MoodboardSection)
            .where(MoodboardSection.board_id == board.id)
        )
    ).scalar_one()
    if count >= MAX_SECTIONS_PER_BOARD:
        raise ProblemError(
            409, "too_many_sections", "Too many sections", "A board can have up to 20 sections."
        )
    db.add(
        MoodboardSection(
            organization_id=ctx.organization_id,
            project_id=ctx.project.id,
            board_id=board.id,
            title=body.title.strip(),
            position=count,
        )
    )
    board.updated_at = _now()
    await db.flush()
    return await get_board(db, ctx, board.id)


async def _section(db: AsyncSession, board: Moodboard, section_id: uuid.UUID) -> MoodboardSection:
    section = await db.get(MoodboardSection, section_id)
    if section is None or section.board_id != board.id:
        raise not_found()
    return section


async def rename_section(
    db: AsyncSession,
    ctx: ProjectContext,
    board_id: uuid.UUID,
    section_id: uuid.UUID,
    body: SectionIn,
) -> BoardOut:
    board = await _board(db, ctx, board_id)
    if not _manages(ctx, board):
        raise FORBIDDEN
    section = await _section(db, board, section_id)
    section.title = body.title.strip()
    await db.flush()
    return await get_board(db, ctx, board.id)


async def delete_section(
    db: AsyncSession, ctx: ProjectContext, board_id: uuid.UUID, section_id: uuid.UUID
) -> BoardOut:
    """The section goes; its images move to "Unsorted" (section_id SET NULL)."""
    board = await _board(db, ctx, board_id)
    if not _manages(ctx, board):
        raise FORBIDDEN
    section = await _section(db, board, section_id)
    await db.delete(section)
    await db.flush()
    return await get_board(db, ctx, board.id)


async def reorder(
    db: AsyncSession, ctx: ProjectContext, board_id: uuid.UUID, body: ReorderIn
) -> BoardOut:
    """Saves a drag-and-drop result. Couples may only move images within their own boards."""
    board = await _board(db, ctx, board_id)
    if not _manages(ctx, board):
        raise FORBIDDEN
    sections = {
        s.id: s
        for s in (
            await db.execute(select(MoodboardSection).where(MoodboardSection.board_id == board.id))
        ).scalars()
    }
    for position, section_id in enumerate(body.sections):
        if section_id not in sections:
            raise not_found()
        sections[section_id].position = position
    items = {
        i.id: i
        for i in (
            await db.execute(select(MoodboardItem).where(MoodboardItem.board_id == board.id))
        ).scalars()
    }
    for key, item_ids in body.items.items():
        target = uuid.UUID(key) if key else None
        if target is not None and target not in sections:
            raise not_found()
        for position, item_id in enumerate(item_ids):
            item = items.get(item_id)
            if item is None:
                raise not_found()
            item.section_id = target
            item.position = position
    board.updated_at = _now()
    await db.flush()
    return await get_board(db, ctx, board.id)


# --- Images -------------------------------------------------------------------------------


async def upload(
    db: AsyncSession,
    ctx: ProjectContext,
    jobs: PendingJobs,
    board_id: uuid.UUID,
    section_id: uuid.UUID | None,
    files: list[images.CheckedImage],
    caption: str | None = None,
) -> BoardOut:
    _require_write(ctx)
    board = await _board(db, ctx, board_id)
    section = await _section(db, board, section_id) if section_id else None
    existing = (
        await db.execute(
            select(func.count())
            .select_from(MoodboardItem)
            .where(MoodboardItem.project_id == ctx.project.id)
        )
    ).scalar_one()
    if existing + len(files) > MAX_ITEMS_PER_WEDDING:
        raise ProblemError(
            409,
            "too_many_images",
            "Too many images",
            f"A wedding can have up to {MAX_ITEMS_PER_WEDDING} moodboard images.",
        )
    in_section = (
        MoodboardItem.section_id == section.id if section else MoodboardItem.section_id.is_(None)
    )
    position = (
        await db.execute(
            select(func.coalesce(func.max(MoodboardItem.position), -1)).where(
                MoodboardItem.board_id == board.id, in_section
            )
        )
    ).scalar_one()
    scanning = get_settings().virus_scan == "clamav"
    storage = get_storage()
    client = is_client(ctx)
    for file in files:
        item_id = uuid7()
        key = (
            f"orgs/{ctx.organization_id}/projects/{ctx.project.id}/moodboards/{board.id}/{item_id}"
        )
        await storage.put(key, file.data, file.content_type)
        position += 1
        db.add(
            MoodboardItem(
                id=item_id,
                organization_id=ctx.organization_id,
                project_id=ctx.project.id,
                board_id=board.id,
                section_id=section.id if section else None,
                caption=(caption or "").strip()[:300] or None,
                storage_key=key,
                filename=file.filename,
                content_type=file.content_type,
                size_bytes=len(file.data),
                width=file.width,
                height=file.height,
                scan_status="pending" if scanning else "not_scanned",
                uploaded_by=ctx.user.id,
                uploaded_by_type="client" if client else "team",
                position=position,
            )
        )
        jobs.add(
            "process_moodboard_image",
            process_image_job,
            str(ctx.organization_id),
            str(item_id),
            str(ctx.user.id),
        )
    board.updated_at = _now()
    await db.flush()
    where = f" in {section.title}" if section else ""
    count = len(files)
    await record_activity(
        db,
        ctx,
        verb="moodboard.images_added",
        target_type="moodboard",
        target_id=board.id,
        summary=f"{count} image{'s' if count != 1 else ''}{where} · {board.title}",
        visibility=board.visibility,
    )
    if client:
        await notify.couple_added_images(db, ctx, board.title, count)
    return await get_board(db, ctx, board.id)


async def _item(
    db: AsyncSession, ctx: ProjectContext, board: Moodboard, item_id: uuid.UUID
) -> MoodboardItem:
    item = await db.get(MoodboardItem, item_id)
    if item is None or item.board_id != board.id:
        raise not_found()
    return item


async def get_item(
    db: AsyncSession, ctx: ProjectContext, board_id: uuid.UUID, item_id: uuid.UUID
) -> MoodboardItem:
    """The item, if the board is visible to this person (RLS hides boards not shared)."""
    return await _item(db, ctx, await _board(db, ctx, board_id), item_id)


async def update_item(
    db: AsyncSession,
    ctx: ProjectContext,
    board_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ItemUpdateIn,
) -> BoardOut:
    board = await _board(db, ctx, board_id)
    item = await _item(db, ctx, board, item_id)
    fields = body.model_dump(exclude_unset=True)
    if "status" in fields:
        if is_client(ctx) or not ctx.can(ProjectPerm.MOODBOARDS_WRITE):
            raise FORBIDDEN  # selecting and discarding is the planner's call
        if fields["status"]:
            item.status = fields["status"]
    if {"caption", "section_id", "move_to_unsorted"} & set(fields):
        if not _can_edit_item(ctx, item):
            raise FORBIDDEN
        if "caption" in fields:
            item.caption = (fields["caption"] or "").strip() or None
        if fields.get("section_id"):
            item.section_id = (await _section(db, board, fields["section_id"])).id
        elif fields.get("move_to_unsorted"):
            item.section_id = None
    board.updated_at = _now()
    await db.flush()
    return await get_board(db, ctx, board.id)


async def delete_item(
    db: AsyncSession, ctx: ProjectContext, board_id: uuid.UUID, item_id: uuid.UUID
) -> BoardOut:
    board = await _board(db, ctx, board_id)
    item = await _item(db, ctx, board, item_id)
    if not _can_edit_item(ctx, item):
        raise FORBIDDEN
    keys = [k for k in (item.storage_key, item.thumb_key, item.display_key) if k]
    await db.execute(
        delete(Comment).where(Comment.target_type == "moodboard_item", Comment.target_id == item.id)
    )
    await db.delete(item)
    board.updated_at = _now()
    await db.flush()
    await _delete_files(keys)
    return await get_board(db, ctx, board.id)


async def set_heart(
    db: AsyncSession, ctx: ProjectContext, board_id: uuid.UUID, item_id: uuid.UUID, on: bool
) -> BoardOut:
    board = await _board(db, ctx, board_id)
    item = await _item(db, ctx, board, item_id)
    existing = (
        await db.execute(
            select(MoodboardReaction).where(
                MoodboardReaction.item_id == item.id, MoodboardReaction.user_id == ctx.user.id
            )
        )
    ).scalar_one_or_none()
    if on and existing is None:
        db.add(
            MoodboardReaction(
                organization_id=ctx.organization_id,
                project_id=ctx.project.id,
                item_id=item.id,
                user_id=ctx.user.id,
            )
        )
    elif not on and existing is not None:
        await db.delete(existing)
    await db.flush()
    return await get_board(db, ctx, board.id)


async def image(
    db: AsyncSession,
    ctx: ProjectContext,
    board_id: uuid.UUID,
    item_id: uuid.UUID,
    size: str,
) -> tuple[MoodboardItem, bytes, str]:
    """Returns (item, bytes, content type). Couples never get the original with its metadata."""
    board = await _board(db, ctx, board_id)
    item = await _item(db, ctx, board, item_id)
    if size == "original" and not is_client(ctx):
        if item.scan_status not in ("clean", "not_scanned"):
            raise _not_ready(item)
        return item, await get_storage().get(item.storage_key), item.content_type
    key = item.thumb_key if size == "thumb" else item.display_key
    if key is None:
        raise _not_ready(item)
    return item, await get_storage().get(key), "image/webp"


def _not_ready(item: MoodboardItem) -> ProblemError:
    if item.scan_status == "infected":
        return ProblemError(409, "file_infected", "Image removed", "The file contained a virus.")
    if item.scan_status == "failed":
        return ProblemError(409, "file_failed", "Image not available", "Please upload it again.")
    return ProblemError(409, "image_processing", "Still processing", "Try again in a moment.")


# --- Files and the processing job ---------------------------------------------------------


async def _storage_keys(db: AsyncSession, *where: Any) -> list[str]:
    keys: list[str] = []
    for row in (
        await db.execute(
            select(
                MoodboardItem.storage_key, MoodboardItem.thumb_key, MoodboardItem.display_key
            ).where(*where)
        )
    ).all():
        keys += [k for k in row if k]
    return keys


async def _delete_files(keys: list[str]) -> None:
    storage = get_storage()
    for key in keys:
        await storage.delete(key)


async def process_image_job(
    ctx: dict[str, Any], organization_id: str, item_id: str, user_id: str
) -> str:
    """Worker job: virus scan, then thumbnail and display version without metadata."""
    async with get_sessionmaker()() as db:
        await set_tenant_context(
            db,
            organization_id=uuid.UUID(organization_id),
            user_id=uuid.UUID(user_id),
            role="org_admin",
        )
        item = await db.get(MoodboardItem, uuid.UUID(item_id))
        if item is None or item.processed_at is not None:
            return "skipped"
        storage = get_storage()
        data = await storage.get(item.storage_key)
        if item.scan_status == "pending":
            try:
                verdict = await scanner.scan_bytes(data)
            except scanner.ScanError as exc:
                if scanner.retry_later(ctx):
                    raise Retry(defer=scanner.RETRY_DELAY_SECONDS) from exc
                item.scan_status = "failed"
                await db.commit()
                return "failed"
            if verdict == "infected":
                item.scan_status = "infected"
                await storage.delete(item.storage_key)
                await audit.record(
                    db,
                    action="moodboard.virus_found",
                    resource_type="moodboard",
                    resource_id=item.board_id,
                    organization_id=item.organization_id,
                    actor_type="system",
                )
                await db.commit()
                return "infected"
            item.scan_status = "clean"
        derived = images.derive(data)
        base = item.storage_key
        await storage.put(f"{base}-thumb.webp", derived.thumb, "image/webp")
        await storage.put(f"{base}-display.webp", derived.display, "image/webp")
        item.thumb_key = f"{base}-thumb.webp"
        item.display_key = f"{base}-display.webp"
        item.processed_at = _now()
        await db.commit()
        return "processed"


async def project_storage_keys(db: AsyncSession, project_ids: list[uuid.UUID]) -> list[str]:
    """For client erasure: every moodboard file of these weddings."""
    if not project_ids:
        return []
    return await _storage_keys(db, MoodboardItem.project_id.in_(project_ids))
