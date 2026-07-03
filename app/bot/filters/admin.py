from aiogram.filters import Filter
from aiogram.types import TelegramObject
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import AdminRole
from app.core.permissions import Permission
from app.services.admin.admin_service import AdminService


class IsAdmin(Filter):
    """Passes for any active admin, regardless of role (owner/admin/moderator)."""

    async def __call__(
        self,
        event: TelegramObject,
        session: AsyncSession,
        event_from_user: TgUser | None = None,
    ) -> bool:
        if event_from_user is None:
            return False
        return await AdminService(session).is_admin(event_from_user.id)


class IsOwner(Filter):
    """Passes only when the acting user's role is exactly ``owner``."""

    async def __call__(
        self,
        event: TelegramObject,
        session: AsyncSession,
        event_from_user: TgUser | None = None,
    ) -> bool:
        if event_from_user is None:
            return False
        role = await AdminService(session).get_role(event_from_user.id)
        return role == AdminRole.OWNER


class HasPermission(Filter):
    """Passes if the acting admin's role satisfies ``permission``.

    Parameterized filter for gating specific admin actions, e.g.::

        @router.message(Command("broadcast"), HasPermission(Permission.BROADCAST))
    """

    def __init__(self, permission: Permission) -> None:
        self.permission = permission

    async def __call__(
        self,
        event: TelegramObject,
        session: AsyncSession,
        event_from_user: TgUser | None = None,
    ) -> bool:
        if event_from_user is None:
            return False
        return await AdminService(session).has_permission(event_from_user.id, self.permission)
