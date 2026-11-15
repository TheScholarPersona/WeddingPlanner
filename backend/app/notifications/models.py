"""Per-user email notification settings and a log of sent digests."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class NotificationPreference(IdMixin, TimestampMixin, TenantMixin, Base):
    """Missing rows mean the defaults (everything on); see notifications.service."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_notification_preferences_user"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    task_assigned: Mapped[bool] = mapped_column(Boolean, default=True)
    comments: Mapped[bool] = mapped_column(Boolean, default=True)
    documents: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_digest: Mapped[bool] = mapped_column(Boolean, default=True)


class NotificationLog(IdMixin, TenantMixin, Base):
    __tablename__ = "notification_log"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", "kind", "ref", name="uq_notification_log_once"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))
    ref: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
