from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Season
from app.database.repositories.base import BaseRepository


class SeasonRepository(BaseRepository[Season]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Season)

    async def get_by_series_and_number(self, series_id: int, number: int) -> Season | None:
        stmt = select(Season).where(Season.series_id == series_id, Season.number == number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_series(self, series_id: int) -> list[Season]:
        stmt = select(Season).where(Season.series_id == series_id).order_by(Season.number)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
