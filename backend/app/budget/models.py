"""Budget per wedding: categories, items with planned/quoted/contracted amounts, payments.

Amounts are integer cents. Every table carries project_id so that row-level security can
use the same wedding-access rule as tasks.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin

DEFAULT_CATEGORIES = (
    "Venue",
    "Catering",
    "Photography",
    "Flowers & Decor",
    "Music",
    "Attire",
    "Stationery",
    "Contingency",
)


class Budget(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "budgets"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    total_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    warning_threshold_pct: Mapped[int] = mapped_column(Integer, default=90)
    version: Mapped[int] = mapped_column(Integer, default=1)


class BudgetCategory(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "budget_categories"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    budget_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("budgets.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer, default=0)


class BudgetItem(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "budget_items"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("budget_categories.id", ondelete="CASCADE"), index=True
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vendors.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200))
    planned_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    quoted_cents: Mapped[int | None] = mapped_column(BigInteger)
    contracted_cents: Mapped[int | None] = mapped_column(BigInteger)
    internal_cost_cents: Mapped[int | None] = mapped_column(BigInteger)
    paid_by: Mapped[str] = mapped_column(String(10), default="client")
    notes_internal: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(10), default="internal")
    position: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)


class Payment(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "payments"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    budget_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("budget_items.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(200))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    due_date: Mapped[date | None] = mapped_column(Date)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
