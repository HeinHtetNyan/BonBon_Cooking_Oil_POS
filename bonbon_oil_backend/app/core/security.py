"""
Security utilities: password hashing, JWT creation/verification.

Passwords use bcrypt via passlib — work factor 12 for production.
JWTs are HS256 signed with SECRET_KEY. RS256 migration path is supported
by swapping jose.jwt.encode/decode calls here without touching call sites.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import TokenExpiredError, TokenInvalidError

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


# Password

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def needs_rehash(hashed: str) -> bool:
    """True when the stored hash uses a deprecated/weaker scheme."""
    return _pwd_context.needs_update(hashed)


# JWT

def _build_payload(
    subject: str | UUID,
    token_type: str,
    expires_delta: timedelta,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + expires_delta,
        "iss": settings.JWT_ISSUER,
        "type": token_type,
    }
    if extra:
        payload.update(extra)
    return payload


def create_access_token(
    subject: str | UUID,
    *,
    roles: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    payload = _build_payload(
        subject=subject,
        token_type="access",
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        extra={**(extra or {}), "roles": roles or []},
    )
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | UUID) -> str:
    payload = _build_payload(
        subject=subject,
        token_type="refresh",
        expires_delta=timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT.

    Raises TokenExpiredError or TokenInvalidError — never raw JWTError —
    so callers can catch specific domain exceptions.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_iss": True},
            issuer=settings.JWT_ISSUER,
        )
        return payload
    except JWTError as exc:
        if "expired" in str(exc).lower():
            raise TokenExpiredError from exc
        raise TokenInvalidError from exc


def extract_subject(token: str) -> str:
    payload = decode_token(token)
    sub: str | None = payload.get("sub")
    if not sub:
        raise TokenInvalidError
    return sub
