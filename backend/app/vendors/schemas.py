import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

CategoryT = Literal[
    "venue",
    "catering",
    "photo",
    "video",
    "flowers",
    "music",
    "decor",
    "attire",
    "stationery",
    "other",
]


class VendorIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: CategoryT
    contact_name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=300, pattern=r"^https?://")
    notes_internal: str | None = Field(default=None, max_length=10_000)
    rating: int | None = Field(default=None, ge=1, le=5)


class VendorUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: CategoryT | None = None
    contact_name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=300, pattern=r"^https?://")
    notes_internal: str | None = Field(default=None, max_length=10_000)
    rating: int | None = Field(default=None, ge=1, le=5)


class VendorOut(BaseModel):
    id: uuid.UUID
    name: str
    category: CategoryT
    contact_name: str | None
    email: str | None
    phone: str | None
    website: str | None
    notes_internal: str | None
    rating: int | None
    project_count: int
