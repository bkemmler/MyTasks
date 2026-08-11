from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import AuditLog

logger = logging.getLogger(__name__)


async def audit(
    db: AsyncSession,
    action: str,
    user_id: int | None = None,
    target: str | None = None,
    detail: dict[str, Any] | None = None,
    actor_ip: str | None = None,
) -> None:
    """Schreibt einen Eintrag ins Audit-Log (fire-and-forget)."""
    try:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            target=target,
            detail=json.dumps(detail) if detail else None,
            actor_ip=actor_ip,
        )
        db.add(entry)
        await db.commit()
    except Exception:
        logger.warning("Audit-Log fehlgeschlagen für action=%s", action)
