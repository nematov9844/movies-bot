from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.movie_repository import MovieRepository
from app.services.movie.movie_service import MovieService
from app.services.series.series_service import SeriesService


async def test_create_and_search_series(session: AsyncSession) -> None:
    service = SeriesService(session)
    await service.create_series("Naruto", "Anime")
    await service.create_series("One Piece")

    results, total = await service.search_series("naru", limit=10, offset=0)
    assert total == 1
    assert results[0].title == "Naruto"


async def test_create_series_stores_poster_file_id(session: AsyncSession) -> None:
    service = SeriesService(session)
    series = await service.create_series("Naruto", "Anime", poster_file_id="poster-abc")
    assert series.poster_file_id == "poster-abc"


async def test_update_series_changes_poster_file_id(session: AsyncSession) -> None:
    service = SeriesService(session)
    series = await service.create_series("Naruto")

    updated = await service.update_series(series.id, poster_file_id="new-poster")
    assert updated is not None
    assert updated.poster_file_id == "new-poster"


async def test_season_number_uniqueness(session: AsyncSession) -> None:
    service = SeriesService(session)
    series = await service.create_series("Naruto")
    await service.create_season(series.id, 1)

    assert await service.season_number_taken(series.id, 1) is True
    assert await service.season_number_taken(series.id, 2) is False


async def test_add_episode_auto_numbers_sequentially(session: AsyncSession) -> None:
    service = SeriesService(session)
    series = await service.create_series("Naruto")
    season = await service.create_season(series.id, 1)

    ep1 = await service.add_episode(
        season_id=season.id,
        series_title=series.title,
        season_number=season.number,
        file_id="f1",
        file_unique_id=None,
        storage_message_id=None,
        duration=None,
        file_size=None,
        is_premium=False,
        created_by=None,
    )
    ep2 = await service.add_episode(
        season_id=season.id,
        series_title=series.title,
        season_number=season.number,
        file_id="f2",
        file_unique_id=None,
        storage_message_id=None,
        duration=None,
        file_size=None,
        is_premium=False,
        created_by=None,
    )

    assert ep1.episode_number == 1
    assert ep2.episode_number == 2
    assert ep1.code != ep2.code
    assert ep1.season_id == season.id


async def test_add_episode_code_matches_movie_code_pattern(session: AsyncSession) -> None:
    """Regression guard: generated codes must satisfy MOVIE_CODE_PATTERN (used by movie_add.py etc)."""
    import re

    from app.core.constants import MOVIE_CODE_PATTERN

    service = SeriesService(session)
    series = await service.create_series("Some Weird Title!! 日本語")
    season = await service.create_season(series.id, 1)

    episode = await service.add_episode(
        season_id=season.id,
        series_title=series.title,
        season_number=season.number,
        file_id="f1",
        file_unique_id=None,
        storage_message_id=None,
        duration=None,
        file_size=None,
        is_premium=False,
        created_by=None,
    )

    assert re.match(MOVIE_CODE_PATTERN, episode.code)


async def test_list_episodes_ordered_and_paginated(session: AsyncSession) -> None:
    service = SeriesService(session)
    series = await service.create_series("Naruto")
    season = await service.create_season(series.id, 1)
    for i in range(5):
        await service.add_episode(
            season_id=season.id,
            series_title=series.title,
            season_number=season.number,
            file_id=f"f{i}",
            file_unique_id=None,
            storage_message_id=None,
            duration=None,
            file_size=None,
            is_premium=False,
            created_by=None,
        )

    page1, total = await service.list_episodes(season.id, limit=2, offset=0)
    assert total == 5
    assert [e.episode_number for e in page1] == [1, 2]

    page2, _ = await service.list_episodes(season.id, limit=2, offset=2)
    assert [e.episode_number for e in page2] == [3, 4]


async def test_delete_season_demotes_episodes_to_standalone(session: AsyncSession) -> None:
    service = SeriesService(session)
    series = await service.create_series("Naruto")
    season = await service.create_season(series.id, 1)
    episode = await service.add_episode(
        season_id=season.id,
        series_title=series.title,
        season_number=season.number,
        file_id="f1",
        file_unique_id=None,
        storage_message_id=None,
        duration=None,
        file_size=None,
        is_premium=False,
        created_by=None,
    )
    await session.flush()

    await service.delete_season(season.id)
    await session.flush()

    # The DB's ON DELETE SET NULL fires regardless, but `episode` is still
    # sitting in this session's identity map with its pre-delete in-memory
    # value — an explicit refresh (not needed by any real caller, which
    # never holds a loaded episode across its own season's deletion) is
    # what a fresh read would see.
    await session.refresh(episode)

    survivor = await MovieRepository(session).get(episode.id)
    assert survivor is not None  # not deleted...
    assert survivor.season_id is None  # ...just demoted to a standalone movie


async def test_search_standalone_only_excludes_episodes(session: AsyncSession) -> None:
    series_service = SeriesService(session)
    series = await series_service.create_series("Naruto")
    season = await series_service.create_season(series.id, 1)
    await series_service.add_episode(
        season_id=season.id,
        series_title=series.title,
        season_number=season.number,
        file_id="f1",
        file_unique_id=None,
        storage_message_id=None,
        duration=None,
        file_size=None,
        is_premium=False,
        created_by=None,
    )
    standalone = await MovieRepository(session).create(code="standalone-naruto", title="Naruto Movie", file_id="f2")
    await session.flush()

    movie_service = MovieService(session)
    results, total = await movie_service.search("Naruto", 1, 10, standalone_only=True)
    assert total == 1
    assert results[0].id == standalone.id

    # Without the flag, both the standalone movie and the episode match.
    all_results, all_total = await movie_service.search("Naruto", 1, 10)
    assert all_total == 2


async def test_get_series_by_title_is_exact_case_insensitive_match(session: AsyncSession) -> None:
    service = SeriesService(session)
    await service.create_series("Naruto Shippuden")
    naruto = await service.create_series("Naruto")

    found = await service.get_series_by_title("naruto")
    assert found is not None
    assert found.id == naruto.id
    assert await service.get_series_by_title("Nar") is None


async def test_get_season_by_number(session: AsyncSession) -> None:
    service = SeriesService(session)
    series = await service.create_series("Naruto")
    season = await service.create_season(series.id, 2)

    found = await service.get_season_by_number(series.id, 2)
    assert found is not None
    assert found.id == season.id
    assert await service.get_season_by_number(series.id, 3) is None


async def test_add_episode_stores_quality_and_year(session: AsyncSession) -> None:
    service = SeriesService(session)
    series = await service.create_series("Naruto")
    season = await service.create_season(series.id, 1)

    episode = await service.add_episode(
        season_id=season.id,
        series_title=series.title,
        season_number=season.number,
        file_id="f1",
        file_unique_id=None,
        storage_message_id=None,
        duration=None,
        file_size=None,
        is_premium=False,
        created_by=None,
        quality="1080p",
        year=2013,
    )

    assert episode.quality == "1080p"
    assert episode.year == 2013


async def test_add_episode_with_explicit_episode_number_ignores_sequential_position(
    session: AsyncSession,
) -> None:
    service = SeriesService(session)
    series = await service.create_series("Naruto")
    season = await service.create_season(series.id, 1)

    episode = await service.add_episode(
        season_id=season.id,
        series_title=series.title,
        season_number=season.number,
        file_id="f1",
        file_unique_id=None,
        storage_message_id=None,
        duration=None,
        file_size=None,
        is_premium=False,
        created_by=None,
        episode_number=47,
    )

    assert episode.episode_number == 47
