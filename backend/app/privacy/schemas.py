from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ConsentKindT = Literal["portfolio", "reviews"]


class ConsentOut(BaseModel):
    kind: ConsentKindT
    granted: bool | None  # None: not decided yet
    decided_at: datetime | None
    outdated: bool = False


class ConsentIn(BaseModel):
    kind: ConsentKindT
    granted: bool


class CoupleConsentsOut(BaseModel):
    full_name: str
    consents: list[ConsentOut]


class EraseClientIn(BaseModel):
    confirm: str = Field(min_length=1, max_length=200)


class EraseSummaryOut(BaseModel):
    weddings: int
    files: int
    portal_accounts: int


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=1024)
    confirm: Literal["DELETE"]
