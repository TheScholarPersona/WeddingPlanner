from pydantic import BaseModel


class PreferencesOut(BaseModel):
    task_assigned: bool
    comments: bool
    documents: bool
    daily_digest: bool


class PreferencesIn(BaseModel):
    task_assigned: bool | None = None
    comments: bool | None = None
    documents: bool | None = None
    daily_digest: bool | None = None
