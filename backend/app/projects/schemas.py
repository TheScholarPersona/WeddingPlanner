import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ProjectStatusT = Literal["planning", "active", "completed", "archived"]
TeamProjectRole = Literal["lead", "planner", "viewer"]
ProjectVendorStatusT = Literal["considered", "requested", "booked", "cancelled"]


class Progress(BaseModel):
    done: int
    total: int
    percent: int


class ProjectCreateIn(BaseModel):
    client_id: uuid.UUID | None = None
    new_client_name: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    wedding_date: date | None = None
    venue_name: str | None = Field(default=None, max_length=200)
    venue_address: str | None = Field(default=None, max_length=500)
    guest_count_planned: int | None = Field(default=None, ge=0, le=10_000)
    style_notes: str | None = Field(default=None, max_length=5000)
    template_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one_client(self) -> "ProjectCreateIn":
        if (self.client_id is None) == (self.new_client_name is None):
            raise ValueError("Choose an existing client or enter a new client name")
        return self


class ProjectUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    wedding_date: date | None = None
    venue_name: str | None = Field(default=None, max_length=200)
    venue_address: str | None = Field(default=None, max_length=500)
    guest_count_planned: int | None = Field(default=None, ge=0, le=10_000)
    style_notes: str | None = Field(default=None, max_length=5000)
    notes_internal: str | None = Field(default=None, max_length=10_000)
    status: Literal["planning", "active", "completed"] | None = None


class ProjectSummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    client_id: uuid.UUID
    client_name: str
    wedding_date: date | None
    days_to_go: int | None
    venue_name: str | None
    guest_count_planned: int | None
    status: ProjectStatusT
    lead_name: str | None
    my_role: str | None
    progress: Progress


class MilestoneOut(BaseModel):
    id: uuid.UUID
    title: str
    due_date: date | None
    completed: bool
    visibility: str
    task_total: int
    task_done: int


class ProjectMemberOut(BaseModel):
    id: uuid.UUID
    membership_id: uuid.UUID
    full_name: str
    email: str
    project_role: str


class ProjectDetailOut(ProjectSummaryOut):
    venue_address: str | None
    style_notes: str | None
    notes_internal: str | None
    version: int
    open_tasks: int
    overdue_tasks: int
    client_tasks_open: int
    milestones: list[MilestoneOut]
    team: list[ProjectMemberOut]
    permissions: list[str]


class ProjectMemberIn(BaseModel):
    membership_id: uuid.UUID
    project_role: TeamProjectRole = "planner"


class ProjectMemberUpdateIn(BaseModel):
    project_role: TeamProjectRole


class ProjectVendorIn(BaseModel):
    vendor_id: uuid.UUID
    status: ProjectVendorStatusT = "considered"
    notes: str | None = Field(default=None, max_length=5000)


class ProjectVendorUpdateIn(BaseModel):
    status: ProjectVendorStatusT | None = None
    notes: str | None = Field(default=None, max_length=5000)


class ProjectVendorOut(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    name: str
    category: str
    contact_name: str | None
    email: str | None
    phone: str | None
    status: ProjectVendorStatusT
    notes: str | None


class DashboardOut(BaseModel):
    active_weddings: int
    weddings_next_6_months: int
    tasks_due_this_week: int
    tasks_due_this_week_mine: int
    overdue_tasks: int
    overdue_weddings: int
    upcoming: list[ProjectSummaryOut]
