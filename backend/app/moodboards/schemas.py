import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Hex = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
VisibilityT = Literal["internal", "client"]
StatusT = Literal["proposed", "selected", "discarded"]


class BoardIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    visibility: VisibilityT = "internal"
    from_template: bool = True


class BoardUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    visibility: VisibilityT | None = None
    palette: list[str] | None = Field(default=None, max_length=8)
    notes_internal: str | None = Field(default=None, max_length=5000)


class SectionIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)


class ReorderIn(BaseModel):
    """Full order of the board: section ids, and for each section (or "" = unsorted) its items."""

    sections: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    items: dict[str, list[uuid.UUID]] = Field(default_factory=dict)


class ItemUpdateIn(BaseModel):
    caption: str | None = Field(default=None, max_length=300)
    section_id: uuid.UUID | None = None
    status: StatusT | None = None
    move_to_unsorted: bool = False


class ItemOut(BaseModel):
    id: uuid.UUID
    section_id: uuid.UUID | None
    caption: str | None
    status: StatusT
    width: int | None
    height: int | None
    ready: bool
    scan_status: str
    uploaded_by_name: str | None
    uploaded_by_type: Literal["team", "client"]
    can_edit: bool
    hearts: int
    hearted_by_me: bool
    heart_names: list[str]
    comment_count: int
    created_at: datetime


class SectionOut(BaseModel):
    id: uuid.UUID
    title: str


class BoardSummaryOut(BaseModel):
    id: uuid.UUID
    title: str
    visibility: VisibilityT
    created_by_type: Literal["team", "client"]
    palette: list[str]
    item_count: int
    selected_count: int
    preview: list[uuid.UUID]
    updated_at: datetime


class BoardOut(BoardSummaryOut):
    version: int
    notes_internal: str | None
    sections: list[SectionOut]
    items: list[ItemOut]
    can_manage: bool
    can_delete: bool


class PortalBoardSummary(BaseModel):
    """What a couple sees: no internal notes, no visibility switch."""

    id: uuid.UUID
    title: str
    from_couple: bool
    palette: list[str]
    item_count: int
    selected_count: int
    preview: list[uuid.UUID]
    updated_at: datetime


class PortalBoard(PortalBoardSummary):
    version: int
    sections: list[SectionOut]
    items: list[ItemOut]
    can_manage: bool
    can_delete: bool
