"""Consents a couple gives an organization (optional, can be withdrawn at any time)."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin


class ConsentKind(StrEnum):
    PORTFOLIO = "portfolio"  # the planner may show the wedding (photos, details) as a reference
    REVIEWS = "reviews"  # the planner may ask for a review after the wedding


# Bump when the wording of a consent changes; older answers are shown as outdated.
CONSENT_TEXT_VERSION = 1


class Consent(IdMixin, TenantMixin, Base):
    __tablename__ = "consents"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "kind", name="uq_consents_kind"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(40))
    granted: Mapped[bool] = mapped_column(Boolean)
    text_version: Mapped[int] = mapped_column(Integer, default=CONSENT_TEXT_VERSION)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
