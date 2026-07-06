import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import REDIS_KEY_MOVIE_CODE, REDIS_KEY_SETTING
from app.database.redis_client import get_redis
from app.database.repositories.movie_repository import MovieRepository
from app.services.movie.movie_service import MovieCard, MovieService

_TEST_USER_ID = 900101


@pytest.fixture(autouse=True)
async def _cleanup_cache():
    yield
    redis = get_redis()
    await redis.delete(REDIS_KEY_MOVIE_CODE.format(code="cache-test"))
    await redis.delete(REDIS_KEY_MOVIE_CODE.format(code="poster-test"))
    await redis.delete(REDIS_KEY_SETTING.format(key="premium_enabled"))


async def test_get_by_code_cached_miss_then_hit(session: AsyncSession) -> None:
    await MovieRepository(session).create(code="cache-test", title="Cache Test", file_id="f1")
    await session.commit()
    service = MovieService(session)

    first = await service.get_by_code_cached("cache-test")
    assert first is not None
    assert first.title == "Cache Test"

    cached_raw = await get_redis().get(REDIS_KEY_MOVIE_CODE.format(code="cache-test"))
    assert cached_raw is not None


async def test_get_by_code_cached_serves_stale_value_until_invalidated(session: AsyncSession) -> None:
    """Proves the cache is real: a direct DB update (bypassing the service) isn't reflected."""
    movie = await MovieRepository(session).create(code="cache-test", title="Original", file_id="f1")
    await session.commit()
    service = MovieService(session)

    first = await service.get_by_code_cached("cache-test")
    assert first is not None and first.title == "Original"

    await MovieRepository(session).update(movie.id, title="Changed Directly")
    await session.commit()

    still_cached = await service.get_by_code_cached("cache-test")
    assert still_cached is not None
    assert still_cached.title == "Original"


async def test_update_movie_invalidates_cache(session: AsyncSession) -> None:
    movie = await MovieRepository(session).create(code="cache-test", title="Original", file_id="f1")
    await session.commit()
    service = MovieService(session)

    await service.get_by_code_cached("cache-test")  # populate cache
    await service.update_movie(movie.id, title="Updated Through Service")
    await session.commit()

    refreshed = await service.get_by_code_cached("cache-test")
    assert refreshed is not None
    assert refreshed.title == "Updated Through Service"


async def test_get_by_code_cached_returns_none_for_inactive_movie(session: AsyncSession) -> None:
    await MovieRepository(session).create(
        code="cache-test", title="Inactive", file_id="f1", is_active=False
    )
    await session.commit()
    service = MovieService(session)

    assert await service.get_by_code_cached("cache-test") is None


async def test_check_access_allows_free_movie(session: AsyncSession) -> None:
    service = MovieService(session)
    card = MovieCard(
        id=1, code="x", title="t", description=None, file_id="f", is_premium=False, is_active=True
    )
    assert await service.check_access(_TEST_USER_ID, card) is True


async def test_check_access_blocks_premium_movie_for_non_premium_user(session: AsyncSession) -> None:
    service = MovieService(session)
    card = MovieCard(
        id=1, code="x", title="t", description=None, file_id="f", is_premium=True, is_active=True
    )
    assert await service.check_access(_TEST_USER_ID, card) is False


async def test_check_access_kill_switch_allows_everyone_when_premium_disabled(
    session: AsyncSession,
) -> None:
    from app.services.settings.settings_service import SettingsService

    await SettingsService(session).set("premium_enabled", "false")
    await session.commit()

    service = MovieService(session)
    card = MovieCard(
        id=1, code="x", title="t", description=None, file_id="f", is_premium=True, is_active=True
    )
    assert await service.check_access(_TEST_USER_ID, card) is True


async def test_search_matches_by_code_not_just_title(session: AsyncSession) -> None:
    await MovieRepository(session).create(code="matrix-1999", title="Something Unrelated", file_id="f1")
    await session.flush()

    service = MovieService(session)
    results, total = await service.search("matrix-1999", 1, 10)
    assert total == 1
    assert results[0].code == "matrix-1999"


async def test_create_movie_stores_poster_file_id(session: AsyncSession) -> None:
    service = MovieService(session)
    movie = await service.create_movie(
        code="poster-test",
        title="Poster Test",
        description=None,
        file_id="f1",
        file_unique_id=None,
        storage_message_id=None,
        duration=None,
        file_size=None,
        is_premium=False,
        created_by=None,
        poster_file_id="poster-abc",
    )
    assert movie.poster_file_id == "poster-abc"


async def test_create_movie_stores_quality_and_year(session: AsyncSession) -> None:
    service = MovieService(session)
    movie = await service.create_movie(
        code="quality-test",
        title="Quality Test",
        description=None,
        file_id="f1",
        file_unique_id=None,
        storage_message_id=None,
        duration=None,
        file_size=None,
        is_premium=False,
        created_by=None,
        quality="1080p",
        year=2010,
    )
    assert movie.quality == "1080p"
    assert movie.year == 2010


async def test_update_movie_changes_poster_file_id(session: AsyncSession) -> None:
    service = MovieService(session)
    movie = await MovieRepository(session).create(code="poster-test", title="Poster Test", file_id="f1")
    await session.flush()

    updated = await service.update_movie(movie.id, poster_file_id="new-poster")
    assert updated is not None
    assert updated.poster_file_id == "new-poster"


async def test_get_by_code_cached_round_trips_poster_file_id(session: AsyncSession) -> None:
    await MovieRepository(session).create(
        code="poster-test", title="Poster Test", file_id="f1", poster_file_id="poster-xyz"
    )
    await session.commit()
    service = MovieService(session)

    first = await service.get_by_code_cached("poster-test")
    assert first is not None
    assert first.poster_file_id == "poster-xyz"

    # Second call is served from the Redis cache (JSON round trip), not the DB row directly.
    second = await service.get_by_code_cached("poster-test")
    assert second is not None
    assert second.poster_file_id == "poster-xyz"
