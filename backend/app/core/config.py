from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TASKS_",
        env_file="/etc/tasks/tasks.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MyTasks"
    app_version: str = ""
    api_version: str = "1"
    db_schema_revision: str = "0000"
    git_sha: str = "dev"
    built_at: str = "1970-01-01T00:00:00Z"
    min_android_version: str = "0.0.0"

    database_url: str = f"sqlite+aiosqlite:///{Path.cwd() / 'var' / 'tasks.db'}"
    bind_host: str = "0.0.0.0"
    bind_port: int = 5000
    log_level: str = "INFO"
    secret_key: str = "change-me-in-production-use-env-or-file"
    secret_key_file: str = ""

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    ollama_timeout_seconds: int = 90
    ollama_keep_alive: str = "30m"

    rate_limit_enabled: bool = True

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "starttls"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = ""
    smtp_from_name: str = "MyTasks"
    smtp_reply_to: str = ""
    smtp_encryption_key: str = ""

    daily_summary_enabled_default: bool = False

    def model_post_init(self, __context: object) -> None:
        if self.secret_key_file:
            key = Path(self.secret_key_file).read_text().strip()
            if key:
                self.secret_key = key


settings = Settings()
