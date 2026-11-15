import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["contract", "quote", "invoice", "planning", "inspiration", "other"]
VisibilityT = Literal["internal", "client"]


class VersionOut(BaseModel):
    id: uuid.UUID
    number: int
    filename: str
    content_type: str
    size_bytes: int
    scan_status: str
    downloadable: bool
    uploaded_by_name: str | None
    created_at: datetime


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    category: Category
    visibility: VisibilityT
    uploaded_by_type: Literal["team", "client"]
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime
    version: int
    current: VersionOut | None
    version_count: int


class DocumentDetailOut(DocumentOut):
    versions: list[VersionOut]


class DocumentUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category: Category | None = None
    visibility: VisibilityT | None = None
