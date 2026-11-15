"""Documents of a wedding: upload, versions, sharing with the couple, download, delete.

Rows are read under row-level security (wedding access; couples only see shared documents).
Files are only handed out after the virus scan passed (or when scanning is off locally).
"""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.models import User
from app.authz.deps import ProjectContext, not_found
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.ids import uuid7
from app.core.versioning import check_version
from app.db.session import get_sessionmaker
from app.db.tenant import set_tenant_context
from app.documents import scanner
from app.documents.files import CheckedFile
from app.documents.models import DOWNLOADABLE, Document, DocumentVersion, ScanStatus
from app.documents.schemas import DocumentDetailOut, DocumentOut, DocumentUpdateIn, VersionOut
from app.documents.storage import get_storage
from app.jobs.queue import PendingJobs
from app.notifications import service as notify
from app.projects.models import ProjectRole
from app.tasks.service import record_activity

MAX_VERSIONS = 50


def _now() -> datetime:
    return datetime.now(UTC)


def _is_client(ctx: ProjectContext) -> bool:
    return ctx.project_role == ProjectRole.CLIENT


# --- Reading ------------------------------------------------------------------------------


def _version_out(v: DocumentVersion, uploader: str | None) -> VersionOut:
    return VersionOut(
        id=v.id,
        number=v.number,
        filename=v.filename,
        content_type=v.content_type.split(";")[0],
        size_bytes=v.size_bytes,
        scan_status=v.scan_status,
        downloadable=v.scan_status in DOWNLOADABLE,
        uploaded_by_name=uploader,
        created_at=v.created_at,
    )


async def _versions(
    db: AsyncSession, document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[VersionOut]]:
    result: dict[uuid.UUID, list[VersionOut]] = {i: [] for i in document_ids}
    if not document_ids:
        return result
    rows = await db.execute(
        select(DocumentVersion, User.full_name)
        .outerjoin(User, User.id == DocumentVersion.uploaded_by)
        .where(DocumentVersion.document_id.in_(document_ids))
        .order_by(DocumentVersion.number.desc())
    )
    for version, name in rows.all():
        result[version.document_id].append(_version_out(version, name))
    return result


def _document_fields(
    doc: Document, creator: str | None, versions: list[VersionOut]
) -> dict[str, Any]:
    current = next((v for v in versions if v.id == doc.current_version_id), None)
    return {
        "id": doc.id,
        "title": doc.title,
        "category": doc.category,
        "visibility": doc.visibility,
        "uploaded_by_type": doc.uploaded_by_type,
        "created_by_name": creator,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
        "version": doc.version,
        "current": current,
        "version_count": len(versions),
    }


async def list_documents(db: AsyncSession, ctx: ProjectContext) -> list[DocumentOut]:
    rows = (
        await db.execute(
            select(Document, User.full_name)
            .outerjoin(User, User.id == Document.created_by)
            .where(Document.project_id == ctx.project.id, Document.deleted_at.is_(None))
            .order_by(Document.updated_at.desc())
        )
    ).all()
    versions = await _versions(db, [d.id for d, _ in rows])
    return [DocumentOut(**_document_fields(d, name, versions[d.id])) for d, name in rows]


async def _document(db: AsyncSession, ctx: ProjectContext, document_id: uuid.UUID) -> Document:
    doc = (
        await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.project_id == ctx.project.id,
                Document.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise not_found()
    return doc


async def get_document(
    db: AsyncSession, ctx: ProjectContext, document_id: uuid.UUID
) -> DocumentDetailOut:
    doc = await _document(db, ctx, document_id)
    creator = (await db.get(User, doc.created_by)) if doc.created_by else None
    versions = (await _versions(db, [doc.id]))[doc.id]
    return DocumentDetailOut(
        **_document_fields(doc, creator.full_name if creator else None, versions),
        versions=versions,
    )


# --- Uploading ----------------------------------------------------------------------------


async def _store_version(
    db: AsyncSession,
    ctx: ProjectContext,
    jobs: PendingJobs,
    doc: Document,
    file: CheckedFile,
    number: int,
) -> DocumentVersion:
    version_id = uuid7()
    key = f"orgs/{ctx.organization_id}/projects/{ctx.project.id}/documents/{doc.id}/{version_id}"
    scanning = get_settings().virus_scan == "clamav"
    version = DocumentVersion(
        id=version_id,
        organization_id=ctx.organization_id,
        project_id=ctx.project.id,
        document_id=doc.id,
        number=number,
        storage_key=key,
        filename=file.filename,
        content_type=file.content_type,
        size_bytes=len(file.data),
        sha256=hashlib.sha256(file.data).hexdigest(),
        scan_status=ScanStatus.PENDING if scanning else ScanStatus.NOT_SCANNED,
        uploaded_by=ctx.user.id,
    )
    await get_storage().put(key, file.data, file.content_type)
    db.add(version)
    await db.flush()
    doc.current_version_id = version.id
    doc.updated_at = _now()
    await db.flush()
    if scanning:
        jobs.add(
            "scan_document",
            scan_document_job,
            str(ctx.organization_id),
            str(version.id),
            str(ctx.user.id),
        )
    return version


async def upload(
    db: AsyncSession,
    ctx: ProjectContext,
    jobs: PendingJobs,
    file: CheckedFile,
    *,
    title: str | None,
    category: str,
    visibility: str,
) -> DocumentDetailOut:
    if _is_client(ctx):
        visibility, category = "client", category or "other"
    doc = Document(
        organization_id=ctx.organization_id,
        project_id=ctx.project.id,
        title=(title or "").strip()[:200] or file.filename.rsplit(".", 1)[0][:200] or "Document",
        category=category,
        visibility=visibility,
        uploaded_by_type="client" if _is_client(ctx) else "team",
        created_by=ctx.user.id,
    )
    db.add(doc)
    await db.flush()
    await _store_version(db, ctx, jobs, doc, file, 1)
    await record_activity(
        db,
        ctx,
        verb="document.uploaded",
        target_type="document",
        target_id=doc.id,
        summary=doc.title,
        visibility=doc.visibility,
    )
    await audit.record(
        db,
        action="document.uploaded",
        resource_type="document",
        resource_id=doc.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"visibility": {"new": doc.visibility}, "size_bytes": {"new": len(file.data)}},
    )
    if doc.visibility == "client":
        await notify.document_shared(db, ctx, doc.title)
    return await get_document(db, ctx, doc.id)


async def add_version(
    db: AsyncSession,
    ctx: ProjectContext,
    jobs: PendingJobs,
    document_id: uuid.UUID,
    file: CheckedFile,
) -> DocumentDetailOut:
    doc = await _document(db, ctx, document_id)
    if _is_client(ctx) and doc.created_by != ctx.user.id:
        raise not_found()
    count = (
        await db.execute(
            select(func.count(), func.coalesce(func.max(DocumentVersion.number), 0)).where(
                DocumentVersion.document_id == doc.id
            )
        )
    ).one()
    if count[0] >= MAX_VERSIONS:
        raise ProblemError(
            409, "too_many_versions", "Too many versions", "Upload it as a new document instead."
        )
    await _store_version(db, ctx, jobs, doc, file, int(count[1]) + 1)
    doc.version += 1
    await record_activity(
        db,
        ctx,
        verb="document.version_added",
        target_type="document",
        target_id=doc.id,
        summary=doc.title,
        visibility=doc.visibility,
    )
    return await get_document(db, ctx, doc.id)


# --- Changing and deleting ----------------------------------------------------------------


async def update(
    db: AsyncSession,
    ctx: ProjectContext,
    document_id: uuid.UUID,
    body: DocumentUpdateIn,
    if_match: str | None,
) -> DocumentDetailOut:
    doc = await _document(db, ctx, document_id)
    check_version(doc.version, if_match, "document")
    before = {"title": doc.title, "category": doc.category, "visibility": doc.visibility}
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(doc, key, value.strip() if key == "title" else value)
    after = {"title": doc.title, "category": doc.category, "visibility": doc.visibility}
    if after == before:
        return await get_document(db, ctx, doc.id)
    doc.version += 1
    doc.updated_at = _now()
    await db.flush()
    if before["visibility"] != after["visibility"]:
        await audit.record(
            db,
            action="document.shared_with_client"
            if doc.visibility == "client"
            else "document.unshared",
            resource_type="document",
            resource_id=doc.id,
            organization_id=ctx.organization_id,
            actor_user_id=ctx.user.id,
            changes=audit.diff(
                {"visibility": before["visibility"]}, {"visibility": doc.visibility}
            ),
        )
        if doc.visibility == "client":
            await record_activity(
                db,
                ctx,
                verb="document.shared",
                target_type="document",
                target_id=doc.id,
                summary=doc.title,
                visibility="client",
            )
            await notify.document_shared(db, ctx, doc.title)
    return await get_document(db, ctx, doc.id)


async def delete(db: AsyncSession, ctx: ProjectContext, document_id: uuid.UUID) -> None:
    """Deletes the document and its files for good; the audit log keeps the fact."""
    doc = await _document(db, ctx, document_id)
    if _is_client(ctx) and (doc.uploaded_by_type != "client" or doc.created_by != ctx.user.id):
        raise not_found()
    keys = list(
        (
            await db.execute(
                select(DocumentVersion.storage_key).where(DocumentVersion.document_id == doc.id)
            )
        ).scalars()
    )
    await audit.record(
        db,
        action="document.deleted",
        resource_type="document",
        resource_id=doc.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"title": {"old": doc.title}, "versions": {"old": len(keys)}},
    )
    doc.current_version_id = None
    await db.flush()
    await db.delete(doc)
    await db.flush()
    storage = get_storage()
    for key in keys:
        await storage.delete(key)


# --- Downloading --------------------------------------------------------------------------


async def download(
    db: AsyncSession, ctx: ProjectContext, document_id: uuid.UUID, version_id: uuid.UUID | None
) -> tuple[DocumentVersion, bytes]:
    doc = await _document(db, ctx, document_id)
    target = version_id or doc.current_version_id
    version = (
        await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.id == target, DocumentVersion.document_id == doc.id
            )
        )
    ).scalar_one_or_none()
    if version is None:
        raise not_found()
    if version.scan_status not in DOWNLOADABLE:
        messages = {
            ScanStatus.PENDING: "The file is still being checked for viruses. Try again shortly.",
            ScanStatus.INFECTED: "The file contained a virus and was removed.",
            ScanStatus.FAILED: "The virus check failed. Please upload the file again.",
        }
        raise ProblemError(
            409,
            f"file_{version.scan_status}",
            "File not available",
            messages.get(ScanStatus(version.scan_status), "The file is not available."),
        )
    return version, await get_storage().get(version.storage_key)


# --- Virus scan job -----------------------------------------------------------------------


async def scan_document_job(
    _: dict[str, Any], organization_id: str, version_id: str, user_id: str
) -> str:
    """Worker job: scan one uploaded version and record the verdict."""
    async with get_sessionmaker()() as db:
        await set_tenant_context(
            db,
            organization_id=uuid.UUID(organization_id),
            user_id=uuid.UUID(user_id),
            role="org_admin",
        )
        version = await db.get(DocumentVersion, uuid.UUID(version_id))
        if version is None or version.scan_status != ScanStatus.PENDING:
            return "skipped"
        storage = get_storage()
        try:
            verdict = await scanner.scan_bytes(await storage.get(version.storage_key))
        except scanner.ScanError:
            version.scan_status = ScanStatus.FAILED
            verdict = None
        if verdict == "clean":
            version.scan_status = ScanStatus.CLEAN
        elif verdict == "infected":
            version.scan_status = ScanStatus.INFECTED
            await storage.delete(version.storage_key)
            await audit.record(
                db,
                action="document.virus_found",
                resource_type="document",
                resource_id=version.document_id,
                organization_id=version.organization_id,
                actor_type="system",
                changes={"version": {"new": version.number}},
            )
        version.scanned_at = _now()
        await db.commit()
        return str(version.scan_status)
