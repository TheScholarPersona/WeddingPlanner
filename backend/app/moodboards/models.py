"""Moodboards of a wedding: boards with sections, images and hearts."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ItemStatus(StrEnum):
    PROPOSED = "proposed"
    SELECTED = "selected"
    DISCARDED = "discarded"


# Sections of a new board created from the template (UI copy stays English).
TEMPLATE_SECTIONS = (
    "Overall look",
    "Venue",
    "Flowers",
    "Table decor",
    "Cake",
    "Outfits",
    "Stationery",
)


class _ProjectScoped(IdMixin, TenantMixin):
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )


class Moodboard(_ProjectScoped, TimestampMixin, Base):
    __tablename__ = "moodboards"

    title: Mapped[str] = mapped_column(String(120))
    visibility: Mapped[str] = mapped_column(String(10), default="internal")
    created_by_type: Mapped[str] = mapped_column(String(10), default="team")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    palette: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    notes_internal: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)


class MoodboardSection(_ProjectScoped, TimestampMixin, Base):
    __tablename__ = "moodboard_sections"

    board_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("moodboards.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer, default=0)


class MoodboardItem(_ProjectScoped, TimestampMixin, Base):
    __tablename__ = "moodboard_items"

    board_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("moodboards.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("moodboard_sections.id", ondelete="SET NULL")
    )
    caption: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), default=ItemStatus.PROPOSED)
    storage_key: Mapped[str] = mapped_column(String(300), unique=True)
    thumb_key: Mapped[str | None] = mapped_column(String(300))
    display_key: Mapped[str | None] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    scan_status: Mapped[str] = mapped_column(String(20), default="pending")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    uploaded_by_type: Mapped[str] = mapped_column(String(10), default="team")
    position: Mapped[int] = mapped_column(Integer, default=0)


class MoodboardReaction(_ProjectScoped, Base):
    __tablename__ = "moodboard_reactions"
    __table_args__ = (UniqueConstraint("item_id", "user_id", name="uq_moodboard_reactions_user"),)

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("moodboard_items.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
