from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.mail import UserMailConfig
from app.models.user import User

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    """Fernet-Instanz; Key deterministisch aus dem Server-Secret abgeleitet."""
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def encrypt_password(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_password(encrypted: str) -> str | None:
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        logger.error("SMTP-Passwort konnte nicht entschlüsselt werden (Secret geändert?)")
        return None


@dataclass
class SmtpConfig:
    """Effektive SMTP-Konfiguration für einen Versand."""

    host: str
    port: int
    security: str  # none | starttls | ssl
    username: str | None
    password: str | None
    from_address: str
    from_name: str | None = None

    def is_complete(self) -> bool:
        return bool(self.host and self.from_address)


async def get_mail_config(db: AsyncSession, user_id: int) -> UserMailConfig | None:
    result = await db.execute(
        select(UserMailConfig).where(UserMailConfig.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_smtp_config(db: AsyncSession, user: User) -> SmtpConfig | None:
    """Effektive SMTP-Konfiguration des Nutzers oder None (kein Versand).

    Kein globaler Fallback: Ohne eigene Konfiguration versendet die App
    für diesen Nutzer keine E-Mails.
    """
    cfg = await get_mail_config(db, user.id)
    if not cfg or not cfg.smtp_host or not cfg.from_address:
        return None
    password = decrypt_password(cfg.smtp_password_encrypted) if cfg.smtp_password_encrypted else None
    return SmtpConfig(
        host=cfg.smtp_host,
        port=cfg.smtp_port,
        security=cfg.smtp_security,
        username=cfg.smtp_username,
        password=password,
        from_address=cfg.from_address,
        from_name=cfg.from_name,
    )
