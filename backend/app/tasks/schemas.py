import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

StatusT = Literal["open", "in_progress", "done", "cancelled"]
PriorityT = Literal["low", "normal", "high"]
AssigneeT = Literal["team", "client"]
VisibilityT = Literal["internal", "client"]


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    milestone_id: uuid.UUID | None = None
    due_date: date | None = None
    priority: PriorityT = "normal"
    assignee_type: AssigneeT = "team"
    assignee_membership_id: uuid.UUID | None = None
    visibility: VisibilityT = "internal"
    checklist: list[str] = Field(default_factory=list, max_length=50)


class TaskUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    milestone_id: uuid.UUID | None = None
    due_date: date | None = None
    priority: PriorityT | None = None
    status: Literal["open", "in_progress", "cancelled"] | None = None
    assignee_type: AssigneeT | None = None
    assignee_membership_id: uuid.UUID | None = None
    visibility: VisibilityT | None = None


class ChecklistItemIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ChecklistItemUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    is_done: bool | None = None


class ChecklistItemOut(BaseModel):
    id: uuid.UUID
    title: str
    is_done: bool
    position: int


class TaskOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    milestone_id: uuid.UUID | None
    milestone_title: str | None
    title: str
    description: str | None
    status: StatusT
    priority: PriorityT
    due_date: date | None
    overdue: bool
    assignee_type: AssigneeT
    assignee_membership_id: uuid.UUID | None
    assignee_name: str | None
    visibility: VisibilityT
    completed_at: datetime | None
    completed_by_name: str | None
    position: int
    version: int
    checklist_total: int
    checklist_done: int
    comment_count: int


class TaskDetailOut(TaskOut):
    checklist: list[ChecklistItemOut]


class MyTaskOut(TaskOut):
    project_title: str
    project_wedding_date: date | None


class ReorderItem(BaseModel):
    id: uuid.UUID
    position: int


class ReorderIn(BaseModel):
    items: list[ReorderItem] = Field(min_length=1, max_length=500)


class MilestoneIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: date | None = None
    visibility: VisibilityT = "internal"


class MilestoneUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_date: date | None = None
    visibility: VisibilityT | None = None
    completed: bool | None = None


class MilestoneDetailOut(BaseModel):
    id: uuid.UUID
    title: str
    due_date: date | None
    completed_at: datetime | None
    visibility: VisibilityT
    position: int
    task_total: int
    task_done: int


class CommentIn(BaseModel):
    target_type: Literal["project", "task", "milestone"]
    target_id: uuid.UUID
    body: str = Field(min_length=1, max_length=5000)
    visibility: VisibilityT = "internal"


class CommentUpdateIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class CommentOut(BaseModel):
    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    author_name: str | None
    is_mine: bool
    body: str
    visibility: VisibilityT
    created_at: datetime
    edited_at: datetime | None


class ActivityOut(BaseModel):
    id: uuid.UUID
    verb: str
    summary: str
    actor_name: str | None
    target_type: str
    target_id: uuid.UUID | None
    visibility: VisibilityT
    created_at: datetime


class ActivityPageOut(BaseModel):
    items: list[ActivityOut]
    next_cursor: uuid.UUID | None
