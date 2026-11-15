"""Milestones, tasks, checklists, comments and the per-wedding activity feed."""

import uuid
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin


class Visibility(StrEnum):
    INTERNAL = "internal"
    CLIENT = "client"


class TaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class Milestone(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "milestones"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    position: Mapped[int] = mapped_column(Integer, default=0)
    visibility: Mapped[str] = mapped_column(String(10), default=Visibility.INTERNAL)


class Task(IdMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    __tablename__ = "tasks"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("milestones.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.OPEN)
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    due_date: Mapped[date | None] = mapped_column(Date)
    assignee_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memberships.id", ondelete="SET NULL")
    )
    assignee_type: Mapped[str] = mapped_column(String(10), default="team")
    visibility: Mapped[str] = mapped_column(String(10), default=Visibility.INTERNAL)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TaskChecklistItem(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "task_checklist_items"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)


class CommentTarget(StrEnum):
    PROJECT = "project"
    TASK = "task"
    MILESTONE = "milestone"


class Comment(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "comments"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[uuid.UUID]
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(10), default=Visibility.INTERNAL)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityEvent(IdMixin, TenantMixin, Base):
    """What happened in a wedding, for the feed. Not an audit trail (see audit_log)."""

    __tablename__ = "activity_events"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    verb: Mapped[str] = mapped_column(String(40))
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[uuid.UUID | None]
    summary: Mapped[str] = mapped_column(String(300))
    visibility: Mapped[str] = mapped_column(String(10), default=Visibility.INTERNAL)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
