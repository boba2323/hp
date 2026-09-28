"""Minimal JWT authentication for Django Ninja.

Access tokens are short lived (60 min by default) and sent as
``Authorization: Bearer <token>``. Refresh tokens only work against
``POST /api/auth/refresh``.
"""

from datetime import UTC, datetime, timedelta

import jwt
from django.conf import settings
from ninja.security import HttpBearer


def _encode(user, token_type: str, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.pk),
        "type": token_type,
        "role": user.role,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user) -> str:
    return _encode(user, "access", settings.JWT_ACCESS_TTL)


def create_refresh_token(user) -> str:
    return _encode(user, "refresh", settings.JWT_REFRESH_TTL)


def decode_token(token: str, expected_type: str | None = None) -> dict | None:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.PyJWTError:
        return None
    if expected_type and payload.get("type") != expected_type:
        return None
    return payload


class JWTAuth(HttpBearer):
    """Ninja security class - sets ``request.auth`` to the ``User`` instance."""

    def authenticate(self, request, token):
        payload = decode_token(token, "access")
        if not payload:
            return None

        from apps.accounts.models import User

        try:
            return User.objects.get(pk=payload["sub"], is_active=True)
        except (User.DoesNotExist, ValueError, TypeError):
            return None


jwt_auth = JWTAuth()
