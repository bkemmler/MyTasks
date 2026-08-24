from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._utils import utcnow


class LLMJob(Base):
    __tablename__ = "llm_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE")
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        String(20), default="queued", nullable=False, server_default="queued"
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: utcnow(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        CheckConstraint(
            "state IN ('queued','running','done','failed')", name="ck_llm_job_state"
        ),
    )


class LLMCorrection(Base):
    __tablename__ = "llm_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="SET NULL")
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    llm_output: Mapped[str] = mapped_column(Text, nullable=False)
    corrected: Mapped[str] = mapped_column(Text, nullable=False)
    changed_fields: Mapped[str] = mapped_column(Text, nullable=False)
    use_as_example: Mapped[bool] = mapped_column(
        Integer, default=1, nullable=False, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: utcnow(), nullable=False
    )


class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = (UniqueConstraint("name", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: utcnow(), nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id")
    )


class UserLLMConfig(Base):
    """Pro-Nutzer-Ollama-Konfiguration.

    ollama_model leer = LLM deaktiviert (nur lokale Extraktion).
    Kein globaler Fallback mehr — TASKS_OLLAMA_MODEL ist obsolet.
    """

    __tablename__ = "user_llm_configs"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    ollama_base_url: Mapped[str] = mapped_column(
        String(255), default="http://localhost:11434", nullable=False
    )
    ollama_model: Mapped[str] = mapped_column(String(255), default="", nullable=False)
