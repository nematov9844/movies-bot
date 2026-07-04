"""Business logic for the Statistics module (Phase 10).

Two halves, per the TZ's "real-time counters in Redis, kun oxirida DB ga
flush" design:

- Module-level ``increment_*``/``mark_active_user`` functions: fire-and-
  forget Redis writes, callable from anywhere a countable event happens
  (a new user upsert, a movie delivery, a raised exception, an API
  request). Deliberately session-free, since some call sites (the bot's
  global error handler, the API request middleware) never have a DB
  session to hand.
- ``StatsService``: DB-backed reads for the bot's Statistika screen —
  today's live Redis snapshot, historical week/month sums from the
  ``statistics`` table, and period-windowed top-10 movies/users straight
  from ``movie_views`` — plus ``flush_today`` for Phase 11's daily
  scheduler job to call.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    REDIS_KEY_STATS_TODAY,
    STATS_MONTH_DAYS,
    STATS_TOP_LIMIT,
    STATS_WEEK_DAYS,
)
from app.database.models import Statistics
from app.database.redis_client import get_redis
from app.database.repositories.movie_repository import MovieRepository
from app.database.repositories.movie_view_repository import MovieViewRepository
from app.database.repositories.premium_user_repository import PremiumUserRepository
from app.database.repositories.statistics_repository import StatisticsRepository
from app.database.repositories.user_repository import UserRepository

_KEY_NEW_USERS = REDIS_KEY_STATS_TODAY.format(metric="new_users")
_KEY_MOVIES_SENT = REDIS_KEY_STATS_TODAY.format(metric="movies_sent")
_KEY_ERRORS = REDIS_KEY_STATS_TODAY.format(metric="errors")
_KEY_API_REQUESTS = REDIS_KEY_STATS_TODAY.format(metric="api_requests")
_KEY_ACTIVE_USERS = REDIS_KEY_STATS_TODAY.format(metric="active_users")


async def increment_new_user() -> None:
    await get_redis().incr(_KEY_NEW_USERS)


async def mark_active_user(user_id: int) -> None:
    """Add ``user_id`` to today's distinct-active-users set (cardinality read via ``SCARD``)."""
    await get_redis().sadd(_KEY_ACTIVE_USERS, user_id)


async def increment_movies_sent() -> None:
    await get_redis().incr(_KEY_MOVIES_SENT)


async def increment_errors() -> None:
    await get_redis().incr(_KEY_ERRORS)


async def increment_api_requests() -> None:
    await get_redis().incr(_KEY_API_REQUESTS)


@dataclass(slots=True)
class MovieRank:
    title: str
    code: str
    views: int


@dataclass(slots=True)
class UserRank:
    user_id: int
    label: str
    views: int


@dataclass(slots=True)
class PeriodStats:
    new_users: int
    active_users: int
    movies_sent: int
    errors: int
    top_movies: list[MovieRank]
    top_users: list[UserRank]


@dataclass(slots=True)
class DailyStat:
    day: date
    new_users: int
    active_users: int
    movies_sent: int


@dataclass(slots=True)
class DashboardData:
    """Web panel Dashboard page (Phase 13): summary cards + a chart series.

    Deliberately a plain dataclass, not the API's Pydantic response model —
    services stay presentation-agnostic; ``app/api/routes/stats.py`` maps
    this onto ``DashboardResponse``.
    """

    total_users: int
    new_users_today: int
    total_movies: int
    active_premium_count: int
    daily: list[DailyStat]


async def _read_counters(redis: Redis) -> tuple[int, int, int, int]:
    new_users = int(await redis.get(_KEY_NEW_USERS) or 0)
    movies_sent = int(await redis.get(_KEY_MOVIES_SENT) or 0)
    errors = int(await redis.get(_KEY_ERRORS) or 0)
    active_users = await redis.scard(_KEY_ACTIVE_USERS)
    return new_users, movies_sent, errors, active_users


class StatsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = StatisticsRepository(session)
        self._movie_repo = MovieRepository(session)
        self._view_repo = MovieViewRepository(session)
        self._user_repo = UserRepository(session)
        self._premium_user_repo = PremiumUserRepository(session)

    async def _ranked_movies(self, since: datetime) -> list[MovieRank]:
        pairs = await self._view_repo.top_movies_since(since, STATS_TOP_LIMIT)
        ranks = []
        for movie_id, views in pairs:
            movie = await self._movie_repo.get(movie_id)
            if movie is not None:
                ranks.append(MovieRank(title=movie.title, code=movie.code, views=views))
        return ranks

    async def _ranked_users(self, since: datetime) -> list[UserRank]:
        pairs = await self._view_repo.top_users_since(since, STATS_TOP_LIMIT)
        ranks = []
        for user_id, views in pairs:
            user = await self._user_repo.get(user_id)
            label = f"@{user.username}" if user is not None and user.username else str(user_id)
            ranks.append(UserRank(user_id=user_id, label=label, views=views))
        return ranks

    async def get_today(self) -> PeriodStats:
        """Live snapshot: not-yet-flushed Redis counters + today's ``movie_views`` window."""
        since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        new_users, movies_sent, errors, active_users = await _read_counters(get_redis())
        return PeriodStats(
            new_users=new_users,
            active_users=active_users,
            movies_sent=movies_sent,
            errors=errors,
            top_movies=await self._ranked_movies(since),
            top_users=await self._ranked_users(since),
        )

    async def get_period(self, days: int) -> PeriodStats:
        """Historical sums from the flushed ``statistics`` table over the trailing ``days`` days."""
        sums = await self._repo.sum_since(date.today() - timedelta(days=days))
        since_dt = datetime.now(UTC) - timedelta(days=days)
        return PeriodStats(
            new_users=sums["new_users"],
            active_users=sums["active_users"],
            movies_sent=sums["movies_sent"],
            errors=sums["errors"],
            top_movies=await self._ranked_movies(since_dt),
            top_users=await self._ranked_users(since_dt),
        )

    async def get_week(self) -> PeriodStats:
        return await self.get_period(STATS_WEEK_DAYS)

    async def get_month(self) -> PeriodStats:
        return await self.get_period(STATS_MONTH_DAYS)

    async def get_dashboard(self, days: int = STATS_MONTH_DAYS) -> DashboardData:
        """Web panel Dashboard page: summary cards + a ``days``-long daily chart series.

        The chart series comes from the flushed ``statistics`` table (so it
        never includes today's not-yet-flushed row); ``new_users_today``
        is the one live Redis figure mixed in, same as ``get_today``.
        """
        total_users = await self._user_repo.count()
        total_movies = await self._movie_repo.count(is_active=True)
        active_premium_count = await self._premium_user_repo.count(is_active=True)
        new_users_today, _, _, _ = await _read_counters(get_redis())

        rows = await self._repo.list_since(date.today() - timedelta(days=days))
        daily = [
            DailyStat(
                day=row.date,
                new_users=row.new_users,
                active_users=row.active_users,
                movies_sent=row.movies_sent,
            )
            for row in rows
        ]

        return DashboardData(
            total_users=total_users,
            new_users_today=new_users_today,
            total_movies=total_movies,
            active_premium_count=active_premium_count,
            daily=daily,
        )

    async def flush_today(self, for_date: date) -> Statistics:
        """Persist today's live Redis counters into the ``statistics`` row for ``for_date``, then reset them.

        Meant to be called by Phase 11's daily 00:05 scheduler job with
        yesterday's date (the day that just ended) — 00:05 is early enough
        into the new day that resetting the counters right after reading
        them can't meaningfully clash with new-day traffic.
        """
        redis = get_redis()
        new_users, movies_sent, errors, active_users = await _read_counters(redis)
        api_requests = int(await redis.get(_KEY_API_REQUESTS) or 0)

        row = await self._repo.upsert_day(
            for_date,
            new_users=new_users,
            active_users=active_users,
            movies_sent=movies_sent,
            errors=errors,
            api_requests=api_requests,
        )

        await redis.delete(
            _KEY_NEW_USERS, _KEY_MOVIES_SENT, _KEY_ERRORS, _KEY_API_REQUESTS, _KEY_ACTIVE_USERS
        )
        return row
