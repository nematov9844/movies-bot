"""Reusable auth dependencies for protecting FastAPI routes.

``get_current_admin`` resolves the bearer access token to an ``Admin`` row;
``require_permission`` is a dependency *factory* that layers a permission
check on top. Later phases' routers (movies/channels/broadcast/premium/
settings/admins, Phase 13) depend on these to gate endpoints — keep them
generic, not tied to any one route.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.dependencies.db import DbSession
from app.core import security
from app.core.constants import AdminRole
from app.core.permissions import Permission
from app.core.permissions import has_permission as _permission_granted
from app.database.models import Admin
from app.services.admin.admin_service import AdminService

_bearer_scheme = HTTPBearer()

_INVALID_TOKEN_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Yaroqsiz yoki muddati o'tgan token",
    headers={"WWW-Authenticate": "Bearer"},
)
_INACTIVE_ADMIN_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Admin faol emas",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_admin(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    session: DbSession,
) -> Admin:
    try:
        payload = security.decode_token(credentials.credentials, expected_type="access")
    except security.InvalidTokenError as exc:
        raise _INVALID_TOKEN_ERROR from exc

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _INVALID_TOKEN_ERROR from exc

    admin = await AdminService(session).get_by_user_id(user_id)
    if admin is None or not admin.is_active:
        raise _INACTIVE_ADMIN_ERROR

    return admin


CurrentAdmin = Annotated[Admin, Depends(get_current_admin)]


def require_permission(permission: Permission) -> Callable[[Admin], Admin]:
    """Dependency factory: ``Depends(require_permission(Permission.BROADCAST))``."""

    def _check(current_admin: CurrentAdmin) -> Admin:
        if not _permission_granted(AdminRole(current_admin.role), permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sizda bu amal uchun ruxsat yo'q.",
            )
        return current_admin

    return _check
