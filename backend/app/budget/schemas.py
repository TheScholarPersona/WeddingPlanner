import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

MAX_CENTS = 100_000_000_00


def cents(default: int | None = None) -> int | None:
    """A non-negative amount in cents (default None = optional)."""
    return Field(default=default, ge=0, le=MAX_CENTS)


class BudgetUpdateIn(BaseModel):
    total_cents: int | None = Field(default=None, ge=0, le=100_000_000_00)
    warning_threshold_pct: int | None = Field(default=None, ge=50, le=100)


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CategoryUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    position: int | None = None


class ItemIn(BaseModel):
    category_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    vendor_id: uuid.UUID | None = None
    planned_cents: int = cents(0)  # type: ignore[assignment]
    quoted_cents: int | None = cents()
    contracted_cents: int | None = cents()
    internal_cost_cents: int | None = cents()
    paid_by: Literal["client", "planner"] = "client"
    notes_internal: str | None = Field(default=None, max_length=5000)
    visibility: Literal["internal", "client"] = "internal"


class ItemUpdateIn(BaseModel):
    category_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    vendor_id: uuid.UUID | None = None
    planned_cents: int | None = cents()
    quoted_cents: int | None = cents()
    contracted_cents: int | None = cents()
    internal_cost_cents: int | None = cents()
    paid_by: Literal["client", "planner"] | None = None
    notes_internal: str | None = Field(default=None, max_length=5000)
    visibility: Literal["internal", "client"] | None = None


class PaymentIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    amount_cents: int = Field(gt=0, le=100_000_000_00)
    due_date: date | None = None
    paid: bool = False


class PaymentUpdateIn(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    amount_cents: int | None = Field(default=None, gt=0, le=100_000_000_00)
    due_date: date | None = None
    paid: bool | None = None


class PaymentOut(BaseModel):
    id: uuid.UUID
    label: str
    amount_cents: int
    due_date: date | None
    paid_at: datetime | None


class ItemOut(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    title: str
    vendor_id: uuid.UUID | None
    vendor_name: str | None
    planned_cents: int
    quoted_cents: int | None
    contracted_cents: int | None
    internal_cost_cents: int | None
    paid_by: str
    notes_internal: str | None
    visibility: Literal["internal", "client"]
    version: int
    paid_cents: int
    payments: list[PaymentOut]


class CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    position: int
    planned_cents: int
    forecast_cents: int
    items: list[ItemOut]


class Totals(BaseModel):
    planned_cents: int
    quoted_cents: int
    contracted_cents: int
    paid_cents: int
    forecast_cents: int
    internal_cost_cents: int
    unplanned_cents: int


class Warning(BaseModel):
    code: Literal["over_budget", "near_budget", "quote_above_plan", "payment_overdue"]
    amount_cents: int
    item_id: uuid.UUID | None = None
    title: str | None = None


class UpcomingPayment(BaseModel):
    id: uuid.UUID
    item_id: uuid.UUID
    item_title: str
    label: str
    amount_cents: int
    due_date: date | None
    overdue: bool


class BudgetOut(BaseModel):
    id: uuid.UUID
    total_cents: int
    currency: str
    warning_threshold_pct: int
    version: int
    totals: Totals
    warnings: list[Warning]
    categories: list[CategoryOut]
    upcoming_payments: list[UpcomingPayment]
