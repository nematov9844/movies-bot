from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.admin_repository import AdminRepository


class AdminService:
    """Minimal admin lookups.

    Phase 3 only needs "is this user an admin" for the maintenance-mode
    gate. Phase 4 builds the full owner/admin/moderator role hierarchy and
    ``require_permission`` on top of this same class.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AdminRepository(session)

    async def is_admin(self, user_id: int) -> bool:
        admin = await self._repo.get_by_user_id(user_id)
        return admin is not None and admin.is_active
