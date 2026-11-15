import uuid
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin


class ClientStatus(StrEnum):
    INQUIRY = "inquiry"
    PROPOSAL = "proposal"
    BOOKED = "booked"
    COMPLETED = "completed"
    LOST = "lost"


class ContactRole(StrEnum):
    PARTNER = "partner"
    FAMILY = "family"
    OTHER = "other"


class Client(IdMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    """A booking, usually a couple. Visible to admins, its creator and its weddings' teams."""

    __tablename__ = "clients"

    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default=ClientStatus.INQUIRY)
    source: Mapped[str | None] = mapped_column(String(100))
    notes_internal: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class ClientContact(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "client_contacts"

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(20), default=ContactRole.PARTNER)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
