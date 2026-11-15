import uuid
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class TemplateItemKind(StrEnum):
    MILESTONE = "milestone"
    TASK = "task"


class ProjectTemplate(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "project_templates"

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class TemplateItem(IdMixin, TimestampMixin, TenantMixin, Base):
    """A milestone or task; due dates are offsets in days relative to the wedding date."""

    __tablename__ = "template_items"

    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_templates.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    offset_days: Mapped[int] = mapped_column(Integer)  # negative = before the wedding
    assignee_type: Mapped[str] = mapped_column(String(10), default="team")
    visibility: Mapped[str] = mapped_column(String(10), default="internal")
    parent_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("template_items.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
