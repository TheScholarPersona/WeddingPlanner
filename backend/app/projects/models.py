import uuid
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin


class ProjectStatus(StrEnum):
    PLANNING = "planning"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ProjectRole(StrEnum):
    LEAD = "lead"
    PLANNER = "planner"
    VIEWER = "viewer"
    CLIENT = "client"


class ProjectVendorStatus(StrEnum):
    CONSIDERED = "considered"
    REQUESTED = "requested"
    BOOKED = "booked"
    CANCELLED = "cancelled"


class Project(IdMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    """One wedding. Visible to org admins and to the people assigned to it."""

    __tablename__ = "projects"

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    wedding_date: Mapped[date | None] = mapped_column(Date)
    venue_name: Mapped[str | None] = mapped_column(String(200))
    venue_address: Mapped[str | None] = mapped_column(String(500))
    guest_count_planned: Mapped[int | None] = mapped_column(Integer)
    style_notes: Mapped[str | None] = mapped_column(Text)
    notes_internal: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=ProjectStatus.PLANNING)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    version: Mapped[int] = mapped_column(Integer, default=1)


class ProjectMember(IdMixin, TenantMixin, Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "membership_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memberships.id", ondelete="CASCADE"), index=True
    )
    project_role: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ProjectVendor(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "project_vendors"
    __table_args__ = (UniqueConstraint("project_id", "vendor_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default=ProjectVendorStatus.CONSIDERED)
    notes: Mapped[str | None] = mapped_column(Text)
