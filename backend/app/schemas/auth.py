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


class MailConfigIn(BaseModel):
    """Eigene Mail-Konfiguration. Passwort leer lassen = unverändert."""

    smtp_host: str = Field(min_length=1, max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: str = Field(default="starttls", pattern="^(none|starttls|ssl)$")
    smtp_username: str | None = Field(default=None, max_length=255)
    smtp_password: str | None = Field(default=None, max_length=255)
    from_address: str = Field(min_length=3, max_length=255)
    from_name: str | None = Field(default=None, max_length=255)


class MailConfigOut(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_security: str
    smtp_username: str | None = None
    has_password: bool = False
    from_address: str
    from_name: str | None = None


class LLMConfigIn(BaseModel):
    """Eigene LLM-Konfiguration. Leeres Modell = LLM deaktiviert."""

    ollama_base_url: str = Field(min_length=1, max_length=255)
    ollama_model: str = Field(default="", max_length=255)


class LLMConfigOut(BaseModel):
    ollama_base_url: str
    ollama_model: str
    enabled: bool = False
