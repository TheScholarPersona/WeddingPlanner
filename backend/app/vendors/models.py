from enum import StrEnum

from sqlalchemy import SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TenantMixin, TimestampMixin


class VendorCategory(StrEnum):
    VENUE = "venue"
    CATERING = "catering"
    PHOTO = "photo"
    VIDEO = "video"
    FLOWERS = "flowers"
    MUSIC = "music"
    DECOR = "decor"
    ATTIRE = "attire"
    STATIONERY = "stationery"
    OTHER = "other"


class Vendor(IdMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    """Organization-wide vendor directory; linked to weddings through project_vendors."""

    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20))
    contact_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    website: Mapped[str | None] = mapped_column(String(300))
    notes_internal: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(SmallInteger)
