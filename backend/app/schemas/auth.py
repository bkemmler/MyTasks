from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)
    device_label: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None = None
    display_name: str | None = None
    is_admin: bool
    is_active: bool
    timezone: str
    locale: str
    daily_summary_enabled: bool
    daily_summary_time: str
    default_due_time: str
    must_change_password: bool
    created_at: datetime


class MePatchRequest(BaseModel):
    email: str | None = None
    display_name: str | None = None
    timezone: str | None = None
    locale: str | None = None
    daily_summary_enabled: bool | None = None
    daily_summary_time: str | None = None
    default_due_time: str | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=12)
