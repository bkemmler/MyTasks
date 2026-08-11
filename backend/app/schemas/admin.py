from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12)
    email: str | None = None
    display_name: str | None = None
    is_admin: bool = False
    timezone: str = "Europe/Berlin"
    locale: str = "de-DE"


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = None
    display_name: str | None = None
    is_admin: bool | None = None
    is_active: bool | None = None
    timezone: str | None = None
    locale: str | None = None


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None = None
    display_name: str | None = None
    is_admin: bool
    is_active: bool
    must_change_password: bool
    failed_login_count: int
    locked_until: datetime | None = None
    created_at: datetime
    updated_at: datetime
