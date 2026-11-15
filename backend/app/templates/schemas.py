import uuid
from typing import Literal

from pydantic import BaseModel, Field


class TemplateItemIn(BaseModel):
    kind: Literal["milestone", "task"]
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    offset_days: int = Field(ge=-1500, le=365)
    assignee_type: Literal["team", "client"] = "team"
    visibility: Literal["internal", "client"] = "internal"
    parent_item_id: uuid.UUID | None = None
    position: int = 0


class TemplateItemUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    offset_days: int | None = Field(default=None, ge=-1500, le=365)
    assignee_type: Literal["team", "client"] | None = None
    visibility: Literal["internal", "client"] | None = None
    parent_item_id: uuid.UUID | None = None
    position: int | None = None


class TemplateItemOut(TemplateItemIn):
    id: uuid.UUID


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    copy_from: uuid.UUID | None = None


class TemplateUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_default: bool | None = None


class TemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_default: bool
    milestone_count: int
    task_count: int


class TemplateDetailOut(TemplateOut):
    items: list[TemplateItemOut]
