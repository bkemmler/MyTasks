from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import argon2
import jwt
from argon2.exceptions import VerificationError, VerifyMismatchError

from app.core.config import settings


def naive_utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


_ph = argon2.PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerificationError, VerifyMismatchError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


ALGORITHM = "HS256"


def create_access_token(user_id: int, is_admin: bool, jti: str) -> str:
    now = naive_utc_now()
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "is_admin": is_admin,
        "exp": now + timedelta(minutes=15),
        "iat": now,
        "jti": jti,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def constant_time_compare(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b, strict=False):
        result |= ord(x) ^ ord(y)
    return result == 0
