from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SubtaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    is_done: bool
    sort_order: int
    completed_at: datetime | None = None


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    notes: str | None = None
    source_text: str | None = None
    due_at: datetime | None = None
    due_is_all_day: bool = False
    start_at: datetime | None = None
    category_id: int | None = None
    priority: int = Field(default=3, ge=1, le=4)
    status: str = Field(default="offen", pattern="^(offen|in_bearbeitung|wartend)$")
    estimated_minutes: int | None = None
    waiting_for: str | None = None
    location: str | None = None
    url: str | None = None
    recurrence_rule: str | None = None
    tags: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    notes: str | None = None
    due_at: datetime | None = None
    due_is_all_day: bool | None = None
    start_at: datetime | None = None
    category_id: int | None = None
    priority: int | None = Field(default=None, ge=1, le=4)
    status: str | None = Field(
        default=None,
        pattern="^(offen|in_bearbeitung|wartend|erledigt|abgebrochen)$",
    )
    estimated_minutes: int | None = None
    waiting_for: str | None = None
    location: str | None = None
    url: str | None = None
    recurrence_rule: str | None = None
    needs_review: bool | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    title: str
    description: str | None = None
    notes: str | None = None
    source_text: str | None = None
    due_at: datetime | None = None
    original_due_at: datetime | None = None
    due_is_all_day: bool
    start_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    category_id: int | None = None
    priority: int
    status: str
    progress_percent: int
    estimated_minutes: int | None = None
    waiting_for: str | None = None
    location: str | None = None
    url: str | None = None
    recurrence_rule: str | None = None
    llm_state: str
    llm_confidence: float | None = None
    needs_review: bool
    review_notes: str | None = None
    subtasks: list[SubtaskOut] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class CaptureRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    mode: str = "single"


class TaskSearchResult(BaseModel):
    tasks: list[TaskOut]
    total: int


class SubtaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
