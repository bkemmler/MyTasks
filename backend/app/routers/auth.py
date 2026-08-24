from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import (
    authenticate_user,
    create_refresh_token,
    get_current_user,
    store_refresh_token,
)
from app.core.exceptions import NotFoundError, UnauthorizedError
from app.core.security import create_access_token, hash_password, naive_utc_now, verify_password
from app.models.user import RefreshToken as RefreshTokenModel
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LLMConfigIn,
    LLMConfigOut,
    LoginRequest,
    MailConfigIn,
    MailConfigOut,
    MePatchRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
)
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, body.username, body.password)

    await audit(db, "login.success", user_id=user.id, actor_ip=request.client.host if request.client else None)

    access_jti = secrets.token_hex(16)
    access_token = create_access_token(user.id, user.is_admin, access_jti)

    raw_refresh, token_hash = create_refresh_token(user.id, body.device_label)
    await store_refresh_token(db, user.id, token_hash, body.device_label)

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()

    result = await db.execute(
        select(RefreshTokenModel).where(
            RefreshTokenModel.token_hash == token_hash,
            RefreshTokenModel.revoked_at.is_(None),
        )
    )
    rt = result.scalar_one_or_none()
    if not rt or rt.expires_at < naive_utc_now():
        raise UnauthorizedError("Ungültiges Refresh-Token")

    result = await db.execute(
        select(User).where(User.id == rt.user_id, User.is_active)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("Nutzer nicht gefunden")

    rt.revoked_at = naive_utc_now()

    new_raw, new_hash = create_refresh_token(user.id)
    new_rt = await store_refresh_token(db, user.id, new_hash)
    rt.replaced_by = new_rt.id

    await db.commit()

    access_jti = secrets.token_hex(16)
    access_token = create_access_token(user.id, user.is_admin, access_jti)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_raw,
    )


@router.post("/logout")
async def logout(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    result = await db.execute(
        select(RefreshTokenModel).where(
            RefreshTokenModel.token_hash == token_hash,
            RefreshTokenModel.revoked_at.is_(None),
        )
    )
    rt = result.scalar_one_or_none()
    if rt:
        rt.revoked_at = naive_utc_now()
        await db.commit()
    return {"detail": "ok"}


@router.get("/me", response_model=MeResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=MeResponse)
async def patch_me(
    body: MePatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field in (
        "email",
        "display_name",
        "timezone",
        "locale",
        "daily_summary_enabled",
        "daily_summary_time",
        "default_due_time",
    ):
        value = getattr(body, field, None)
        if value is not None:
            setattr(current_user, field, value)
    current_user.updated_at = naive_utc_now()
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/me/password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.old_password, current_user.password_hash):
        raise UnauthorizedError("Altes Passwort ist falsch")

    current_user.password_hash = hash_password(body.new_password)
    current_user.must_change_password = False
    current_user.updated_at = naive_utc_now()
    await db.commit()
    return {"detail": "Passwort geändert"}


def _mail_config_out(cfg) -> MailConfigOut:
    return MailConfigOut(
        smtp_host=cfg.smtp_host,
        smtp_port=cfg.smtp_port,
        smtp_security=cfg.smtp_security,
        smtp_username=cfg.smtp_username,
        has_password=bool(cfg.smtp_password_encrypted),
        from_address=cfg.from_address,
        from_name=cfg.from_name,
    )


@router.get("/me/mail-config", response_model=MailConfigOut)
async def get_mail_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Eigene Mail-Konfiguration lesen (Passwort wird nie zurückgegeben)."""
    from app.services.user_mail import get_mail_config

    cfg = await get_mail_config(db, current_user.id)
    if not cfg:
        raise NotFoundError("Keine Mail-Konfiguration hinterlegt")
    return _mail_config_out(cfg)


@router.put("/me/mail-config", response_model=MailConfigOut)
async def put_mail_config(
    body: MailConfigIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Eigene Mail-Konfiguration speichern. Leeres Passwort = bestehendes behalten."""
    from app.models.mail import UserMailConfig
    from app.services.user_mail import encrypt_password, get_mail_config

    cfg = await get_mail_config(db, current_user.id)
    if cfg is None:
        cfg = UserMailConfig(user_id=current_user.id)
        db.add(cfg)

    cfg.smtp_host = body.smtp_host
    cfg.smtp_port = body.smtp_port
    cfg.smtp_security = body.smtp_security
    cfg.smtp_username = body.smtp_username
    cfg.from_address = body.from_address
    cfg.from_name = body.from_name

    if body.smtp_password:  # leer/None → bestehendes Passwort behalten
        cfg.smtp_password_encrypted = encrypt_password(body.smtp_password)

    await db.commit()
    await audit(
        db,
        "mail.config.update",
        user_id=current_user.id,
        target=body.smtp_host,
    )
    return _mail_config_out(cfg)


@router.delete("/me/mail-config", status_code=204)
async def delete_mail_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Eigene Mail-Konfiguration löschen (deaktiviert den E-Mail-Versand)."""
    from app.services.user_mail import get_mail_config

    cfg = await get_mail_config(db, current_user.id)
    if cfg:
        await db.delete(cfg)
        await db.commit()
        await audit(db, "mail.config.delete", user_id=current_user.id)
    return None


@router.post("/me/mail-config/test")
async def test_mail_config(
    to_address: str | None = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Versendet eine Test-Email mit der eigenen Konfiguration."""
    from app.services.email import render_summary_html, render_summary_text, send_email
    from app.services.user_mail import get_smtp_config

    smtp = await get_smtp_config(db, current_user)
    if smtp is None:
        return {"success": False, "detail": "Keine gültige Mail-Konfiguration hinterlegt"}

    target = to_address or current_user.email or smtp.from_address
    fake_user = {
        "username": current_user.username,
        "display_name": current_user.display_name,
    }
    fake_tasks = {
        "heute": [{"title": "Das ist eine Test-Email von MyTasks", "priority": 3, "due_at": None}],
    }
    from app.services.i18n import t as tr

    ok = await send_email(
        to=target,
        subject=tr(current_user.locale, "test.subject"),
        text_body=render_summary_text(fake_user, fake_tasks, locale=current_user.locale),
        html_body=render_summary_html(fake_user, fake_tasks, locale=current_user.locale),
        smtp=smtp,
    )
    return {"success": ok, "to": target}


def _llm_config_out(cfg) -> LLMConfigOut:
    return LLMConfigOut(
        ollama_base_url=cfg.ollama_base_url,
        ollama_model=cfg.ollama_model,
        enabled=bool(cfg.ollama_model),
    )


@router.get("/me/llm-config", response_model=LLMConfigOut)
async def get_llm_config_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Eigene LLM-Konfiguration lesen (404 wenn nie konfiguriert)."""
    from app.services.user_llm import get_llm_config_row

    cfg = await get_llm_config_row(db, current_user.id)
    if not cfg:
        raise NotFoundError("Keine LLM-Konfiguration hinterlegt")
    return _llm_config_out(cfg)


@router.put("/me/llm-config", response_model=LLMConfigOut)
async def put_llm_config(
    body: LLMConfigIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Eigene LLM-Konfiguration speichern. Leeres Modell = deaktiviert."""
    from app.models.llm import UserLLMConfig
    from app.services.user_llm import get_llm_config_row

    cfg = await get_llm_config_row(db, current_user.id)
    if cfg is None:
        cfg = UserLLMConfig(user_id=current_user.id)
        db.add(cfg)

    base_url = body.ollama_base_url.strip()
    if not base_url.startswith(("http://", "https://")):
        from app.core.exceptions import ValidationError as AppValidationError
        raise AppValidationError("Base-URL muss mit http:// oder https:// beginnen")

    cfg.ollama_base_url = base_url.rstrip("/")
    cfg.ollama_model = body.ollama_model.strip()

    await db.commit()
    await audit(db, "llm.config.update", user_id=current_user.id, target=base_url)
    return _llm_config_out(cfg)


@router.delete("/me/llm-config", status_code=204)
async def delete_llm_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Eigene LLM-Konfiguration löschen (nur lokale Extraktion)."""
    from app.services.user_llm import get_llm_config_row

    cfg = await get_llm_config_row(db, current_user.id)
    if cfg:
        await db.delete(cfg)
        await db.commit()
        await audit(db, "llm.config.delete", user_id=current_user.id)
    return None


@router.post("/me/llm-config/test")
async def test_llm_config(
    body: dict | None = Body(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Testet die Ollama-Verbindung und liefert die verfügbaren Modelle.

    Optional body: {"ollama_base_url": "..."} — sonst gespeicherte Config.
    """
    from app.services.user_llm import list_ollama_models

    base_url = (body or {}).get("ollama_base_url") or ""
    if not base_url:
        from app.services.user_llm import get_llm_config_row

        cfg = await get_llm_config_row(db, current_user.id)
        if not cfg:
            return {"success": False, "models": [], "detail": "Keine Base-URL angegeben"}
        base_url = cfg.ollama_base_url

    try:
        models = await list_ollama_models(base_url)
        return {"success": True, "models": models}
    except Exception as e:
        return {"success": False, "models": [], "detail": str(e)[:200]}
