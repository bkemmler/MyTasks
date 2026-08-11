from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models._utils import utcnow

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.tag import TaskTag
    from app.models.user import User


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    source_text: Mapped[str | None] = mapped_column(Text)

    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    original_due_at: Mapped[datetime | None] = mapped_column(DateTime)
    due_is_all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    start_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: utcnow(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: utcnow(),
        onupdate=lambda: utcnow(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)

    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL")
    )
    priority: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False, server_default="3"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="offen",
        nullable=False,
        server_default="offen",
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )

    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    waiting_for: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(2048))
    recurrence_rule: Mapped[str | None] = mapped_column(String(500))
    recurrence_parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tasks.id")
    )
    parent_task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE")
    )
    sort_order: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    llm_state: Mapped[str] = mapped_column(
        String(20),
        default="none",
        nullable=False,
        server_default="none",
    )
    llm_confidence: Mapped[float | None] = mapped_column(Float)
    llm_model: Mapped[str | None] = mapped_column(String(255))
    prompt_version: Mapped[int | None] = mapped_column(Integer)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("priority BETWEEN 1 AND 4", name="ck_task_priority"),
        CheckConstraint(
            "status IN ('offen','in_bearbeitung','wartend','erledigt','abgebrochen')",
            name="ck_task_status",
        ),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="ck_task_progress"),
        CheckConstraint(
            "llm_state IN ('none','pending','done','failed')", name="ck_task_llm_state"
        ),
    )

    user: Mapped[User] = relationship(back_populates="tasks")
    category: Mapped[Category | None] = relationship(back_populates="tasks")
    subtasks: Mapped[list[Subtask]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="Subtask.sort_order"
    )
    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    task_tags: Mapped[list[TaskTag]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class Subtask(Base):
    __tablename__ = "subtasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    task: Mapped[Task] = relationship(back_populates="subtasks")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    remind_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    channel: Mapped[str] = mapped_column(String(10), default="push", nullable=False)

    task: Mapped[Task] = relationship(back_populates="reminders")
