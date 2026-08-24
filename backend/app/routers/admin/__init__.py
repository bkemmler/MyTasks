from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_admin_user
from app.core.security import hash_password, naive_utc_now
from app.models.user import User
from app.schemas.admin import AdminUserOut, UserCreate, UserUpdate
from app.services.audit import audit

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).order_by(User.username))
    return result.scalars().all()


@router.post("/users", response_model=AdminUserOut, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    existing = await db.execute(
        select(User).where(User.username == body.username)
    )
    if existing.scalar_one_or_none():
        from app.core.exceptions import ConflictError
        raise ConflictError(f"Nutzer '{body.username}' existiert bereits")

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        email=body.email,
        display_name=body.display_name,
        is_admin=body.is_admin,
        timezone=body.timezone,
        locale=body.locale,
        must_change_password=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await audit(db, "admin.user.create", user_id=admin.id, target=body.username)
    return user


@router.get("/users/{user_id}", response_model=AdminUserOut)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        from app.core.exceptions import NotFoundError
        raise NotFoundError()
    return user


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        from app.core.exceptions import NotFoundError
        raise NotFoundError()

    for field in (
        "username", "email", "display_name", "is_admin", "is_active",
        "timezone", "locale",
    ):
        value = getattr(body, field, None)
        if value is not None:
            setattr(user, field, value)
    user.updated_at = naive_utc_now()
    await db.commit()
    await db.refresh(user)
    await audit(db, "admin.user.update", user_id=admin.id, target=str(user_id))
    return user


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    hard: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        from app.core.exceptions import NotFoundError
        raise NotFoundError()

    if hard:
        await db.delete(user)
    else:
        user.is_active = False
        user.updated_at = naive_utc_now()
    await db.commit()
    await audit(db, "admin.user.delete", user_id=admin.id, target=str(user_id), detail={"hard": hard})
    return None


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    new_password: str = Body(..., embed=True, min_length=12),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        from app.core.exceptions import NotFoundError
        raise NotFoundError()

    user.password_hash = hash_password(new_password)
    user.must_change_password = True
    user.updated_at = naive_utc_now()
    await db.commit()
    return {"detail": "Passwort zurückgesetzt"}


@router.post("/smtp/test")
async def test_smtp(
    to_address: str = Body(..., embed=True),
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Testet die eigene Mail-Konfiguration mit einer Email an die angegebene Adresse."""
    from app.services.email import render_summary_html, render_summary_text, send_email
    from app.services.user_mail import get_smtp_config

    smtp = await get_smtp_config(db, admin)
    if smtp is None:
        return {"success": False, "to": to_address, "detail": "Keine Mail-Konfiguration hinterlegt"}

    fake_user = {
        "username": admin.username,
        "display_name": admin.display_name,
    }
    fake_tasks = {
        "ueberfaellig": [{"title": "Beispiel-Task überfällig", "priority": 2, "due_at": "2026-08-08 16:00"}],
        "heute": [{"title": "Heute fällig", "priority": 3, "due_at": "2026-08-09 17:00"}],
    }
    from app.services.i18n import t as tr

    locale = admin.locale
    text = render_summary_text(fake_user, fake_tasks, locale=locale)
    html = render_summary_html(fake_user, fake_tasks, locale=locale)
    ok = await send_email(
        to=to_address,
        subject=tr(locale, "test.subject"),
        text_body=text,
        html_body=html,
        smtp=smtp,
    )
    return {"success": ok, "to": to_address}


@router.post("/summary/send")
async def send_summary_now(
    user_id: int | None = Body(None, embed=True),
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Versendet die tägliche Zusammenfassung sofort (für Testnutzer)."""
    from app.services.scheduler import send_daily_summary_to_user

    if user_id is None:
        result = await db.execute(
            select(User).where(
                User.id != admin.id,
                User.is_active,
            )
        )
        users = result.scalars().all()
        sent = 0
        for u in users:
            if await send_daily_summary_to_user(db, u):
                sent += 1
        return {"sent": sent, "total": len(users)}

    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if not u:
        from app.core.exceptions import NotFoundError
        raise NotFoundError()
    ok = await send_daily_summary_to_user(db, u)
    return {"sent": 1 if ok else 0, "user_id": user_id}


@router.post("/summary/preview")
async def preview_summary(
    user_id: int | None = Body(None, embed=True),
    admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Zeigt die Zusammenfassung als HTML/Text, ohne sie zu versenden."""
    from app.services.scheduler import build_summary_for_user

    if user_id is None:
        result = await db.execute(select(User).where(User.id == admin.id))
        u = result.scalar_one()
    else:
        result = await db.execute(select(User).where(User.id == user_id))
        u = result.scalar_one_or_none()
        if not u:
            from app.core.exceptions import NotFoundError
            raise NotFoundError()

    sections, text, html = await build_summary_for_user(db, u)
    return {
        "user": {"id": u.id, "username": u.username, "email": u.email},
        "sections": sections,
        "text": text,
        "html": html,
    }
