"""Business logic for the movie catalog: CRUD, delivery access, and browsing.

Phase 6's first substantial consumer of ``Movie``/``Category``/``MovieView``.
Follows ``UserService.get_profile``'s style of composing several
repositories behind one read-heavy service, plus the cache-aside pattern
already sketched by ``REDIS_KEY_MOVIE_CODE`` in ``app.core.constants``.
"""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MOVIE_CODE_CACHE_TTL_SECONDS, REDIS_KEY_MOVIE_CODE
from app.core.metrics import bot_movies_sent_total
from app.database.models import Movie, MovieView
from app.database.redis_client import get_redis
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.movie_repository import MovieRepository
from app.database.repositories.movie_view_repository import MovieViewRepository
from app.services.premium.premium_service import PremiumService
from app.services.settings.settings_service import SettingsService
from app.services.stats.stats_service import increment_movies_sent

# Sentinel distinguishing "leave this field alone" from "set it to None" in
# ``MovieService.update_movie`` — plain ``None`` can't be used as that
# default since ``description`` legitimately needs to be clearable to NULL.
_UNSET: Any = object()


@dataclass(slots=True)
class MovieCard:
    """Minimal, delivery-ready view of a movie.

    This — not the full ``Movie`` ORM row — is what gets cached (as JSON)
    under ``REDIS_KEY_MOVIE_CODE`` and returned by ``get_by_code_cached``,
    so every code-lookup/search/list-tap delivery handler works against the
    same small shape regardless of whether it came from cache or the DB.
    """

    id: int
    code: str
    title: str
    description: str | None
    file_id: str
    is_premium: bool
    is_active: bool
    # Defaulted so a pre-existing cached JSON blob (written before this field
    # existed, still live for up to its 1h TTL) deserializes fine instead of
    # raising a TypeError for a missing kwarg.
    poster_file_id: str | None = None


class MovieService:
    """Compose the movie/category/view/premium repositories for the movie module."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = MovieRepository(session)
        self._category_repo = CategoryRepository(session)
        self._view_repo = MovieViewRepository(session)
        self._premium_service = PremiumService(session)
        self._settings_service = SettingsService(session)

    async def create_movie(
        self,
        *,
        code: str,
        title: str,
        description: str | None,
        file_id: str,
        file_unique_id: str | None,
        storage_message_id: int | None,
        duration: int | None,
        file_size: int | None,
        is_premium: bool,
        created_by: int | None,
        category_ids: list[int] | None = None,
        poster_file_id: str | None = None,
    ) -> Movie:
        # Resolve categories *before* creating the row: assigning to
        # ``movie.categories`` after the fact (once the row is persistent)
        # would make SQLAlchemy lazy-load the current collection first for
        # history tracking, which needs a greenlet context we're not in
        # here and raises ``MissingGreenlet``. Passing it as a constructor
        # field instead is safe since the object is still transient then.
        categories = await self._category_repo.get_by_ids(category_ids) if category_ids else []
        movie = await self._repo.create(
            code=code,
            title=title,
            description=description,
            file_id=file_id,
            poster_file_id=poster_file_id,
            file_unique_id=file_unique_id,
            storage_message_id=storage_message_id,
            duration=duration,
            file_size=file_size,
            is_premium=is_premium,
            created_by=created_by,
            categories=categories,
        )
        return movie

    async def get(self, movie_id: int) -> Movie | None:
        """Raw row lookup by primary key — the web panel's movie detail/edit form."""
        return await self._repo.get(movie_id)

    async def update_movie(
        self,
        movie_id: int,
        *,
        code: str | None = _UNSET,
        title: str | None = _UNSET,
        description: str | None = _UNSET,
        poster_file_id: str | None = _UNSET,
        is_premium: bool | None = _UNSET,
        is_active: bool | None = _UNSET,
        category_ids: list[int] | None = _UNSET,
    ) -> Movie | None:
        """Apply the given field(s) — anything left as ``_UNSET`` is untouched.

        Always invalidates the old code's Redis cache entry (any cached
        field, not just the code, may have changed) and, if ``code`` is
        being changed, the new code's entry too (defensive — it shouldn't
        already be cached, but a stale hit there would serve the wrong
        movie).
        """
        movie = await self._repo.get(movie_id)
        if movie is None:
            return None

        old_code = movie.code
        if code is not _UNSET:
            movie.code = code
        if title is not _UNSET:
            movie.title = title
        if description is not _UNSET:
            movie.description = description
        if poster_file_id is not _UNSET:
            movie.poster_file_id = poster_file_id
        if is_premium is not _UNSET:
            movie.is_premium = is_premium
        if is_active is not _UNSET:
            movie.is_active = is_active
        if category_ids is not _UNSET:
            # Unlike create_movie, this row is already persistent, so
            # assigning straight to ``.categories`` would trigger an
            # implicit lazy-load of the current collection outside a
            # greenlet context (MissingGreenlet). Load it explicitly first
            # via an awaited refresh so the collection is already populated
            # by the time we overwrite it.
            await self._session.refresh(movie, attribute_names=["categories"])
            movie.categories = await self._category_repo.get_by_ids(category_ids or [])

        await self._session.flush()
        # `updated_at`'s `onupdate=func.now()` marks it expired after this
        # UPDATE — an unawaited attribute access on it outside a greenlet
        # context (e.g. Pydantic serializing the returned row) would raise
        # MissingGreenlet. Refreshing now, still inside an awaited context,
        # means every caller gets a fully-populated row back safely.
        await self._session.refresh(movie)

        redis = get_redis()
        await redis.delete(REDIS_KEY_MOVIE_CODE.format(code=old_code))
        if code is not _UNSET and code != old_code:
            await redis.delete(REDIS_KEY_MOVIE_CODE.format(code=code))
        return movie

    async def delete_movie(self, movie_id: int) -> Movie | None:
        """Soft-delete: flips ``is_active`` off and invalidates its cache entry."""
        movie = await self._repo.update(movie_id, is_active=False)
        if movie is None:
            return None
        await get_redis().delete(REDIS_KEY_MOVIE_CODE.format(code=movie.code))
        return movie

    async def get_by_code_cached(self, code: str) -> MovieCard | None:
        """Cache-aside lookup by code, 1-hour TTL. Only ever returns active movies.

        An inactive movie behaves as "not found" here — the admin
        find/edit/delete flow goes through ``MovieRepository.get_by_code``
        directly instead, so it can still see inactive movies.
        """
        redis = get_redis()
        key = REDIS_KEY_MOVIE_CODE.format(code=code)

        cached = await redis.get(key)
        if cached is not None:
            return MovieCard(**json.loads(cached))

        movie = await self._repo.get_by_code(code)
        if movie is None or not movie.is_active:
            return None

        card = MovieCard(
            id=movie.id,
            code=movie.code,
            title=movie.title,
            description=movie.description,
            file_id=movie.file_id,
            is_premium=movie.is_premium,
            is_active=movie.is_active,
            poster_file_id=movie.poster_file_id,
        )
        await redis.set(key, json.dumps(asdict(card)), ex=MOVIE_CODE_CACHE_TTL_SECONDS)
        return card

    async def check_access(self, user_id: int, movie: MovieCard) -> bool:
        """``True`` unless ``movie`` is premium-only and ``user_id`` has no active premium.

        Mirrors ``ForceSubscribeService``'s "settings toggle turns the whole
        gate off" rule: with Phase 12's ``premium_enabled`` setting off, the
        premium subsystem is off entirely, so every movie is freely
        accessible regardless of ``is_premium`` — a user's actual premium
        status (``PremiumService.is_premium``, still queried honestly
        elsewhere, e.g. the Profil screen) is untouched by this switch.
        """
        if not movie.is_premium:
            return True
        if not await self._settings_service.get_bool("premium_enabled", default=True):
            return True
        return await self._premium_service.is_premium(user_id)

    async def record_view(self, movie_id: int, user_id: int) -> None:
        """Insert a ``movie_views`` row, bump ``Movie.view_count``, and count it in today's live stats."""
        self._session.add(MovieView(movie_id=movie_id, user_id=user_id))
        movie = await self._repo.get(movie_id)
        if movie is not None:
            movie.view_count += 1
        await self._session.flush()
        await increment_movies_sent()
        bot_movies_sent_total.inc()

    async def search(
        self, query: str, page: int, size: int, *, standalone_only: bool = False
    ) -> tuple[list[Movie], int]:
        """Title-or-code ``ILIKE`` search over active movies, paginated.

        ``standalone_only`` excludes series episodes (``season_id IS NOT
        NULL``) — used by the user-facing browse search, which shows a
        matching Series grouped instead of its individual episodes (see
        ``movie_search.py``). The admin panel's Movies page keeps the
        default (``False``): admins manage every row, episodes included.
        """
        filters = [
            Movie.is_active.is_(True),
            or_(Movie.title.ilike(f"%{query}%"), Movie.code.ilike(f"%{query}%")),
        ]
        if standalone_only:
            filters.append(Movie.season_id.is_(None))

        total = await self._session.scalar(select(func.count()).select_from(Movie).where(*filters))

        stmt = (
            select(Movie)
            .where(*filters)
            .order_by(Movie.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total or 0

    async def list_top(self, limit: int) -> list[Movie]:
        stmt = (
            select(Movie).where(Movie.is_active.is_(True)).order_by(Movie.view_count.desc()).limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_new(self, limit: int) -> list[Movie]:
        stmt = (
            select(Movie).where(Movie.is_active.is_(True)).order_by(Movie.created_at.desc()).limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_popular_recent(self, days: int, limit: int) -> list[Movie]:
        """Movies with the most views in the last ``days`` days, most-viewed first."""
        since = datetime.now(UTC) - timedelta(days=days)
        stmt = (
            select(Movie)
            .join(MovieView, MovieView.movie_id == Movie.id)
            .where(Movie.is_active.is_(True), MovieView.created_at >= since)
            .group_by(Movie.id)
            .order_by(func.count(MovieView.id).desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_category(
        self, category_id: int, page: int, size: int
    ) -> tuple[list[Movie], int]:
        filters = (Movie.is_active.is_(True), Movie.categories.any(id=category_id))

        total = await self._session.scalar(select(func.count()).select_from(Movie).where(*filters))

        stmt = (
            select(Movie)
            .where(*filters)
            .order_by(Movie.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total or 0
