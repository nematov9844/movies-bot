from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Series
from app.database.repositories.base import BaseRepository


class SeriesRepository(BaseRepository[Series]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Series)

    async def search(self, query: str, limit: int, offset: int) -> tuple[list[Series], int]:
        """Title ILIKE search over active series, paginated — mirrors MovieService.search."""
        filters = (Series.is_active.is_(True), Series.title.ilike(f"%{query}%"))

        total = await self.session.scalar(select(func.count()).select_from(Series).where(*filters))

        stmt = (
            select(Series)
            .where(*filters)
            .order_by(Series.title)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total or 0

    async def get_with_seasons(self, id: int) -> Series | None:
        stmt = select(Series).where(Series.id == id).options(selectinload(Series.seasons))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
