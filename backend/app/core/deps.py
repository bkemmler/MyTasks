from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.models.user import RefreshToken as RefreshTokenModel
from app.models.user import User


def _naive_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def get_current_user(
    request: Request,
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]

    if not token:
        raise UnauthorizedError("Kein Token")

    try:
        payload = decode_access_token(token)
    except Exception:
        raise UnauthorizedError("Ungültiges Token") from None

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id, User.is_active))
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedError("Nutzer nicht gefunden oder deaktiviert")

    if user.locked_until and user.locked_until > _naive_utc():
        raise UnauthorizedError("Konto gesperrt")

    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_admin:
        raise UnauthorizedError("Admin-Rechte erforderlich")
    return current_user


def create_refresh_token(user_id: int, device_label: str | None = None) -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


async def store_refresh_token(
    db: AsyncSession,
    user_id: int,
    token_hash: str,
    device_label: str | None = None,
) -> RefreshTokenModel:
    rt = RefreshTokenModel(
        user_id=user_id,
        token_hash=token_hash,
        device_label=device_label,
        issued_at=_naive_utc(),
        expires_at=_naive_utc() + timedelta(days=30),
    )
    db.add(rt)
    await db.commit()
    return rt


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> User:
    from app.core.security import verify_password

    result = await db.execute(
        select(User).where(User.username == username, User.is_active)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedError("Ungültige Anmeldedaten")

    if user.locked_until and user.locked_until > _naive_utc():
        raise UnauthorizedError("Konto gesperrt")

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= 10:
            user.locked_until = _naive_utc() + timedelta(hours=1)
        elif user.failed_login_count >= 5:
            user.locked_until = _naive_utc() + timedelta(minutes=15)
        await db.commit()
        raise UnauthorizedError("Ungültige Anmeldedaten")

    user.failed_login_count = 0
    user.locked_until = None
    return user
