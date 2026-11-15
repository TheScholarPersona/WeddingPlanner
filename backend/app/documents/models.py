"""Documents of a wedding and their uploaded file versions (files live in S3 storage)."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin


class DocumentCategory(StrEnum):
    CONTRACT = "contract"
    QUOTE = "quote"
    INVOICE = "invoice"
    PLANNING = "planning"
    INSPIRATION = "inspiration"
    OTHER = "other"


class ScanStatus(StrEnum):
    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"
    FAILED = "failed"
    NOT_SCANNED = "not_scanned"  # virus scanning switched off (local development only)


DOWNLOADABLE = frozenset({ScanStatus.CLEAN, ScanStatus.NOT_SCANNED})


class Document(IdMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    __tablename__ = "documents"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20), default=DocumentCategory.OTHER)
    visibility: Mapped[str] = mapped_column(String(10), default="internal")
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL", use_alter=True)
    )
    uploaded_by_type: Mapped[str] = mapped_column(String(10), default="team")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(Integer, default=1)


class DocumentVersion(IdMixin, TenantMixin, Base):
    __tablename__ = "document_versions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    scan_status: Mapped[str] = mapped_column(String(20), default=ScanStatus.PENDING)
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
