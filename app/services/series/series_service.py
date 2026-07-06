"""Business logic for series/season/episode grouping.

An episode is still a plain ``Movie`` row (same code/file_id/premium-gating/
view-tracking as a standalone film) — this service only adds the
``Series``/``Season`` grouping on top and auto-generates each episode's
``code``/``title``/``episode_number`` so the bot's bulk-forward admin flow
never has to ask the admin anything per-video.
"""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Movie, Season, Series
from app.database.repositories.movie_repository import MovieRepository
from app.database.repositories.season_repository import SeasonRepository
from app.database.repositories.series_repository import SeriesRepository

_SLUG_INVALID_RE = re.compile(r"[^a-z0-9]+")
_SLUG_MAX_LEN = 12


def _slugify(title: str) -> str:
    slug = _SLUG_INVALID_RE.sub("-", title.lower()).strip("-")
    return (slug or "series")[:_SLUG_MAX_LEN]


class SeriesService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._series_repo = SeriesRepository(session)
        self._season_repo = SeasonRepository(session)
        self._movie_repo = MovieRepository(session)

    # --- Series ---------------------------------------------------------

    async def create_series(
        self, title: str, description: str | None = None, poster_file_id: str | None = None
    ) -> Series:
        return await self._series_repo.create(
            title=title, description=description, poster_file_id=poster_file_id, is_active=True
        )

    async def search_series(self, query: str, limit: int, offset: int) -> tuple[list[Series], int]:
        return await self._series_repo.search(query, limit, offset)

    async def list_all_series(self, limit: int | None = None, offset: int | None = None) -> list[Series]:
        return await self._series_repo.get_many(limit=limit, offset=offset)

    async def count_all_series(self) -> int:
        return await self._series_repo.count()

    async def get_series(self, series_id: int) -> Series | None:
        return await self._series_repo.get(series_id)

    async def get_series_by_title(self, title: str) -> Series | None:
        """Exact (case-insensitive) title match — for the caption parser's find-or-create
        step, where an ILIKE substring hit (``search_series``) would risk attaching an
        episode to the wrong show (e.g. "Naruto" matching "Naruto Shippuden")."""
        return await self._series_repo.get_by_title(title)

    async def get_series_with_seasons(self, series_id: int) -> Series | None:
        return await self._series_repo.get_with_seasons(series_id)

    async def update_series(
        self,
        series_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        poster_file_id: str | None = None,
    ) -> Series | None:
        fields = {
            k: v
            for k, v in {
                "title": title,
                "description": description,
                "poster_file_id": poster_file_id,
            }.items()
            if v is not None
        }
        if not fields:
            return await self._series_repo.get(series_id)
        return await self._series_repo.update(series_id, **fields)

    async def delete_series(self, series_id: int) -> bool:
        """Hard delete — cascades to its seasons; their episodes demote to standalone movies."""
        return await self._series_repo.delete(series_id)

    # --- Seasons ---------------------------------------------------------

    async def create_season(self, series_id: int, number: int) -> Season:
        return await self._season_repo.create(series_id=series_id, number=number, is_active=True)

    async def get_season(self, season_id: int) -> Season | None:
        return await self._season_repo.get(season_id)

    async def season_number_taken(self, series_id: int, number: int, *, exclude_season_id: int | None = None) -> bool:
        existing = await self._season_repo.get_by_series_and_number(series_id, number)
        return existing is not None and existing.id != exclude_season_id

    async def get_season_by_number(self, series_id: int, number: int) -> Season | None:
        return await self._season_repo.get_by_series_and_number(series_id, number)

    async def update_season(self, season_id: int, number: int) -> Season | None:
        return await self._season_repo.update(season_id, number=number)

    async def list_seasons(self, series_id: int) -> list[Season]:
        return await self._season_repo.list_by_series(series_id)

    async def list_seasons_paginated(
        self, series_id: int, limit: int, offset: int
    ) -> tuple[list[Season], int]:
        return await self._season_repo.list_by_series_paginated(series_id, limit, offset)

    async def delete_season(self, season_id: int) -> bool:
        """Hard delete — its episodes demote to standalone movies (``season_id`` FK is ON DELETE SET NULL)."""
        return await self._season_repo.delete(season_id)

    # --- Episodes (still plain Movie rows) -------------------------------

    async def add_episode(
        self,
        *,
        season_id: int,
        series_title: str,
        season_number: int,
        file_id: str,
        file_unique_id: str | None,
        storage_message_id: int | None,
        duration: int | None,
        file_size: int | None,
        is_premium: bool,
        created_by: int | None,
        quality: str | None = None,
        year: int | None = None,
    ) -> Movie:
        """Appends the next episode to a season — auto-numbered, auto-coded, no admin prompts.

        Episode number is ``max(existing) + 1`` (not a stored counter), so
        it stays correct even if an earlier episode is later removed.
        """
        episode_number = await self._movie_repo.max_episode_number(season_id) + 1
        slug = _slugify(series_title)
        code = f"{slug}-{season_id}-s{season_number}e{episode_number}"

        return await self._movie_repo.create(
            code=code,
            title=f"{series_title} — {season_number}-fasl, {episode_number}-qism",
            file_id=file_id,
            file_unique_id=file_unique_id,
            storage_message_id=storage_message_id,
            duration=duration,
            file_size=file_size,
            is_premium=is_premium,
            is_active=True,
            season_id=season_id,
            episode_number=episode_number,
            created_by=created_by,
            quality=quality,
            year=year,
        )

    async def list_episodes(self, season_id: int, limit: int, offset: int) -> tuple[list[Movie], int]:
        return await self._movie_repo.list_by_season(season_id, limit, offset)

    async def count_episodes(self, season_id: int) -> int:
        return await self._movie_repo.count(season_id=season_id, is_active=True)

    async def get_season_default_premium(self, season_id: int) -> bool:
        """The ``is_premium`` an admin should default to when *resuming* forwarding into an existing season.

        All episodes in a season are expected to share the same premium
        status (chosen once, at season creation) — read off any existing
        episode rather than storing a separate column for it. Defaults to
        ``False`` for a season with no episodes yet (the season-creation
        flow itself already asks in that case).
        """
        episodes, _ = await self._movie_repo.list_by_season(season_id, limit=1, offset=0)
        return episodes[0].is_premium if episodes else False
