from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Statistics
from app.database.repositories.base import BaseRepository


class StatisticsRepository(BaseRepository[Statistics]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Statistics)

    async def get_by_date(self, day: date) -> Statistics | None:
        stmt = select(Statistics).where(Statistics.date == day)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_day(
        self,
        day: date,
        *,
        new_users: int,
        active_users: int,
        movies_sent: int,
        errors: int,
        api_requests: int,
    ) -> Statistics:
        """Write the day's aggregate row, overwriting it if the flush job ever re-runs for the same date."""
        values = {
            "new_users": new_users,
            "active_users": active_users,
            "movies_sent": movies_sent,
            "errors": errors,
            "api_requests": api_requests,
        }
        stmt = (
            pg_insert(Statistics)
            .values(date=day, **values)
            .on_conflict_do_update(index_elements=[Statistics.date], set_=values)
            .returning(Statistics)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def sum_since(self, since: date) -> dict[str, int]:
        """Column-wise sums across every flushed day from ``since`` (inclusive) to today."""
        stmt = select(
            func.coalesce(func.sum(Statistics.new_users), 0),
            func.coalesce(func.sum(Statistics.active_users), 0),
            func.coalesce(func.sum(Statistics.movies_sent), 0),
            func.coalesce(func.sum(Statistics.errors), 0),
            func.coalesce(func.sum(Statistics.api_requests), 0),
        ).where(Statistics.date >= since)
        result = await self.session.execute(stmt)
        new_users, active_users, movies_sent, errors, api_requests = result.one()
        return {
            "new_users": new_users,
            "active_users": active_users,
            "movies_sent": movies_sent,
            "errors": errors,
            "api_requests": api_requests,
        }
