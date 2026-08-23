from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserMailConfig(Base):
    """Pro-Nutzer-SMTP-Konfiguration für den E-Mail-Versand.

    Das Passwort wird Fernet-verschlüsselt gespeichert (Key abgeleitet
    aus settings.secret_key) und nie im Klartext oder in API-Responses
    zurückgegeben.
    """

    __tablename__ = "user_mail_configs"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    # none | starttls | ssl
    smtp_security: Mapped[str] = mapped_column(String(10), default="starttls", nullable=False)
    smtp_username: Mapped[str | None] = mapped_column(String(255))
    smtp_password_encrypted: Mapped[str | None] = mapped_column(Text)
    from_address: Mapped[str] = mapped_column(String(255), nullable=False)
    from_name: Mapped[str | None] = mapped_column(String(255))

    user: Mapped[User] = relationship(back_populates="mail_config")  # type: ignore[name-defined]  # noqa: F821
