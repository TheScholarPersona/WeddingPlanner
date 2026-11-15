"""Client portal schemas. They only contain what a couple may see: no internal notes, no
internal costs, no assignee details. Separate classes make leaking such fields impossible."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class PortalOrganization(BaseModel):
    name: str
    accent_color: str | None


class PortalProjectSummary(BaseModel):
    id: uuid.UUID
    title: str
    wedding_date: date | None
    organization: PortalOrganization


class PortalProgress(BaseModel):
    done: int
    total: int
    percent: int


class PortalTeamMember(BaseModel):
    full_name: str
    role: Literal["lead", "planner"]


class PortalMilestone(BaseModel):
    id: uuid.UUID
    title: str
    due_date: date | None
    completed: bool


class PortalChecklistItem(BaseModel):
    id: uuid.UUID
    title: str
    is_done: bool


class PortalTask(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    status: Literal["open", "in_progress", "done", "cancelled"]
    due_date: date | None
    overdue: bool
    milestone_id: uuid.UUID | None
    milestone_title: str | None
    for_couple: bool
    checklist: list[PortalChecklistItem]
    comment_count: int


class PortalBudgetSummary(BaseModel):
    total_cents: int
    contracted_cents: int
    paid_cents: int
    currency: str


class PortalOverview(BaseModel):
    id: uuid.UUID
    title: str
    wedding_date: date | None
    days_to_go: int | None
    venue_name: str | None
    guest_count_planned: int | None
    organization: PortalOrganization
    progress: PortalProgress
    next_steps: list[PortalTask]
    milestones: list[PortalMilestone]
    team: list[PortalTeamMember]
    budget: PortalBudgetSummary


class PortalBudgetItem(BaseModel):
    id: uuid.UUID
    title: str
    planned_cents: int
    quoted_cents: int | None
    contracted_cents: int | None
    paid_cents: int
    stage: Literal["planned", "quoted", "booked"]


class PortalBudgetCategory(BaseModel):
    id: uuid.UUID
    name: str
    items: list[PortalBudgetItem]


class PortalPayment(BaseModel):
    id: uuid.UUID
    item_title: str
    label: str
    amount_cents: int
    due_date: date | None
    overdue: bool


class PortalBudget(BaseModel):
    total_cents: int
    currency: str
    contracted_cents: int
    paid_cents: int
    forecast_cents: int
    categories: list[PortalBudgetCategory]
    upcoming_payments: list[PortalPayment]


class PortalComment(BaseModel):
    id: uuid.UUID
    author_name: str | None
    is_mine: bool
    body: str
    created_at: datetime


class PortalCommentIn(BaseModel):
    body: str


class PortalChecklistUpdateIn(BaseModel):
    is_done: bool
