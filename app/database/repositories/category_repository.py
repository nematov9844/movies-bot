from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Category
from app.database.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Category)

    async def list_active(self) -> list[Category]:
        stmt = select(Category).where(Category.is_active.is_(True)).order_by(Category.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ids(self, ids: list[int]) -> list[Category]:
        """Fetch categories by id, e.g. resolving an add/edit-movie wizard's selection."""
        if not ids:
            return []
        stmt = select(Category).where(Category.id.in_(ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> Category | None:
        stmt = select(Category).where(Category.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
