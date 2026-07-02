from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Admin
from app.database.repositories.base import BaseRepository


class AdminRepository(BaseRepository[Admin]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Admin)

    async def get_by_user_id(self, user_id: int) -> Admin | None:
        stmt = select(Admin).where(Admin.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
