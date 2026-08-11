from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

LITERAL_STATUS = ["offen", "in_bearbeitung", "wartend", "erledigt"]


class TaskExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str | None = None
    due_at: str | None = None
    due_source_phrase: str | None = None
    due_is_all_day: bool = False
    start_at: str | None = None
    category: str | None = None
    category_suggestion: str | None = None
    priority: int = Field(ge=1, le=4)
    status: str = Field(default="offen", pattern="^(offen|in_bearbeitung|wartend|erledigt)$")
    waiting_for: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=5)
    subtasks: list[str] = Field(default_factory=list, max_length=8)
    estimated_minutes: int | None = None
    location: str | None = None
    url: str | None = None
    recurrence_rule: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    ambiguities: list[str] = Field(default_factory=list)
