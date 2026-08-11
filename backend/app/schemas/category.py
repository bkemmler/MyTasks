from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    color: str | None = None
    aliases: list[str] = Field(default_factory=list)
    is_default: bool = False
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    color: str | None = None
    aliases: list[str] | None = None
    is_default: bool | None = None
    sort_order: int | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None = None
    aliases: str | None = None
    is_default: bool
    sort_order: int
