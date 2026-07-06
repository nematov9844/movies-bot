from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Movie
from app.database.repositories.base import BaseRepository


class MovieRepository(BaseRepository[Movie]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Movie)

    async def get_by_file_unique_id(self, file_unique_id: str) -> Movie | None:
        """Finds an existing row for the same Telegram file — ``file_unique_id`` is stable
        across re-forwards/re-uploads of the same underlying video, so a hit here means this
        exact video was already stored, not just a title collision."""
        stmt = select(Movie).where(Movie.file_unique_id == file_unique_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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

    async def max_episode_number(self, season_id: int) -> int:
        """The highest ``episode_number`` already used in this season, or 0 if it has none yet.

        The bulk-forward flow's source of the *next* episode number
        (``max + 1``) — rather than a running counter, so it's correct even
        if an episode is later deleted/reordered.
        """
        result = await self.session.scalar(
            select(func.max(Movie.episode_number)).where(Movie.season_id == season_id)
        )
        return result or 0

    async def get_by_season_and_episode(self, season_id: int, episode_number: int) -> Movie | None:
        """Finds the episode already occupying this slot, if any — guards the caption parser's
        ingest path against silently colliding with (or overwriting) an existing episode number."""
        stmt = select(Movie).where(Movie.season_id == season_id, Movie.episode_number == episode_number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_season(self, season_id: int, limit: int, offset: int) -> tuple[list[Movie], int]:
        """Episodes of a season, in watch order, for the user-facing episode picker."""
        filters = (Movie.season_id == season_id, Movie.is_active.is_(True))
        total = await self.session.scalar(select(func.count()).select_from(Movie).where(*filters))

        stmt = (
            select(Movie)
            .where(*filters)
            .order_by(Movie.episode_number)
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total or 0
