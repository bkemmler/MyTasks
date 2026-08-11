from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await _create_fts(conn)
        await _migrate_schema(conn)


async def _migrate_schema(conn) -> None:
    """Fügt neue Spalten hinzu, die nicht in create_all enthalten sind."""
    try:
        await conn.execute(text("SELECT original_due_at FROM tasks LIMIT 0"))
    except Exception:
        await conn.execute(
            text("ALTER TABLE tasks ADD COLUMN original_due_at TEXT")
        )
    try:
        await conn.execute(text("SELECT notes FROM tasks LIMIT 0"))
    except Exception:
        await conn.execute(
            text("ALTER TABLE tasks ADD COLUMN notes TEXT")
        )


async def _create_fts(conn) -> None:
    try:
        await conn.execute(text("SELECT 1 FROM tasks_fts LIMIT 0"))
    except Exception:
        await conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(
                title, description, source_text, waiting_for, location,
                content='tasks', content_rowid='id',
                tokenize='unicode61 remove_diacritics 2'
            )
        """))
        await conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS tasks_fts_insert AFTER INSERT ON tasks BEGIN
                INSERT INTO tasks_fts(rowid, title, description, source_text, waiting_for, location)
                VALUES (new.id, new.title, new.description, new.source_text, new.waiting_for, new.location);
            END
        """))
        await conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS tasks_fts_delete AFTER DELETE ON tasks BEGIN
                INSERT INTO tasks_fts(tasks_fts, rowid, title, description, source_text, waiting_for, location)
                VALUES ('delete', old.id, old.title, old.description, old.source_text, old.waiting_for, old.location);
            END
        """))
        await conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS tasks_fts_update AFTER UPDATE ON tasks BEGIN
                INSERT INTO tasks_fts(tasks_fts, rowid, title, description, source_text, waiting_for, location)
                VALUES ('delete', old.id, old.title, old.description, old.source_text, old.waiting_for, old.location);
                INSERT INTO tasks_fts(rowid, title, description, source_text, waiting_for, location)
                VALUES (new.id, new.title, new.description, new.source_text, new.waiting_for, new.location);
            END
        """))
