from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Movie
from app.database.repositories.base import BaseRepository


class MovieRepository(BaseRepository[Movie]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Movie)

    async def get_by_code(self, code: str) -> Movie | None:
        stmt = select(Movie).where(Movie.code == code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
