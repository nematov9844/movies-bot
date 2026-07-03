from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Movie
from app.database.repositories.base import BaseRepository


class MovieRepository(BaseRepository[Movie]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Movie)

    async def get_by_code(self, code: str) -> Movie | None:
        """Look up a movie by its unique code, with ``categories`` eager-loaded.

        Used both for the cache-miss path of ``MovieService.get_by_code_cached``
        and directly by the admin find/edit/delete flow (which, unlike the
        cached lookup, must also be able to see inactive movies). Eager
        loading ``categories`` up front avoids a ``MissingGreenlet`` error
        from accessing that relationship lazily later in async code.
        """
        stmt = select(Movie).where(Movie.code == code).options(selectinload(Movie.categories))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
