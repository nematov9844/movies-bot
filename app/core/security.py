"""Password hashing and JWT issuance/verification for the admin web panel.

Passwords are hashed with bcrypt via passlib. JWTs are HS256, signed with
``settings.jwt_secret``, and always carry a ``type`` claim (``access`` or
``refresh``) so an access token can never be replayed where a refresh token
is expected and vice versa.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_ALGORITHM = "HS256"

TokenType = Literal["access", "refresh"]


class InvalidTokenError(Exception):
    """Raised when a JWT fails signature, expiry, or type validation."""


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def _create_token(*, user_id: int, token_type: TokenType, expires_delta: timedelta, extra_claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def create_access_token(user_id: int, role: str) -> str:
    return _create_token(
        user_id=user_id,
        token_type="access",
        expires_delta=timedelta(minutes=settings.jwt_access_expire_minutes),
        extra_claims={"role": role},
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        user_id=user_id,
        token_type="refresh",
        expires_delta=timedelta(days=settings.jwt_refresh_expire_days),
    )


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a JWT, raising ``InvalidTokenError`` on any failure.

    Validates signature and expiry (via ``pyjwt``) plus the ``type`` claim
    matching ``expected_type``, so an access token can't be used where a
    refresh token is expected, or vice versa.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != expected_type:
        raise InvalidTokenError(f"expected token type {expected_type!r}, got {payload.get('type')!r}")

    return payload
