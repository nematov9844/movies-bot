from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import MovieView
from app.database.repositories.base import BaseRepository


class MovieViewRepository(BaseRepository[MovieView]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MovieView)

    async def top_movies_since(self, since: datetime, limit: int) -> list[tuple[int, int]]:
        """``(movie_id, view_count)`` pairs for the most-viewed movies since ``since``, most-viewed first."""
        stmt = (
            select(MovieView.movie_id, func.count(MovieView.id).label("views"))
            .where(MovieView.created_at >= since)
            .group_by(MovieView.movie_id)
            .order_by(func.count(MovieView.id).desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row.movie_id, row.views) for row in result.all()]

    async def top_users_since(self, since: datetime, limit: int) -> list[tuple[int, int]]:
        """``(user_id, view_count)`` pairs for the users who watched the most movies since ``since``."""
        stmt = (
            select(MovieView.user_id, func.count(MovieView.id).label("views"))
            .where(MovieView.created_at >= since)
            .group_by(MovieView.user_id)
            .order_by(func.count(MovieView.id).desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row.user_id, row.views) for row in result.all()]
