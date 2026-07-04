"""Web panel Users page: ``GET /api/users``, ``GET /api/users/{id}``, ``PATCH /api/users/{id}/block``.

Ban/unban requires ``MANAGE_USERS`` — a new permission (moderator+, mirroring
``MANAGE_MOVIES``'s threshold) since the TZ's role table never actually
covers user moderation; premium-granting from this page reuses
``POST /api/premium/grant`` rather than a separate endpoint.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies.auth import CurrentAdmin, require_permission
from app.api.dependencies.db import DbSession
from app.api.dependencies.pagination import Pagination
from app.api.schemas.common import Page
from app.api.schemas.user import UserBlockRequest, UserResponse
from app.core.permissions import Permission
from app.database.models import Admin
from app.services.audit.audit_service import AuditService
from app.services.user.user_service import UserService

router = APIRouter(prefix="/api/users", tags=["users"])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Foydalanuvchi topilmadi")

ManageUsersAdmin = Annotated[Admin, Depends(require_permission(Permission.MANAGE_USERS))]


@router.get("", response_model=Page[UserResponse])
async def list_users(
    session: DbSession,
    _current_admin: CurrentAdmin,
    pagination: Pagination,
    q: str | None = None,
) -> Page[UserResponse]:
    users, total = await UserService(session).search(q, pagination.limit, pagination.offset)
    return Page(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, session: DbSession, _current_admin: CurrentAdmin) -> UserResponse:
    user = await UserService(session).get(user_id)
    if user is None:
        raise _NOT_FOUND
    return UserResponse.model_validate(user)


@router.patch("/{user_id}/block", response_model=UserResponse)
async def set_user_blocked(
    user_id: int,
    body: UserBlockRequest,
    request: Request,
    session: DbSession,
    current_admin: ManageUsersAdmin,
) -> UserResponse:
    user = await UserService(session).set_blocked(user_id, body.blocked)
    if user is None:
        raise _NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="user_block" if body.blocked else "user_unblock",
        entity="user",
        entity_id=str(user_id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return UserResponse.model_validate(user)
