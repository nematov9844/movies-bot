from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.movie_repository import MovieRepository
from app.services.parser.caption_parser import ParsedCaption
from app.services.parser.ingest_service import CaptionIngestService
from app.services.series.series_service import SeriesService


async def test_save_episode_creates_series_and_season(session: AsyncSession) -> None:
    parsed = ParsedCaption(title="Naruto", season_number=1, episode_number=1, quality="1080p")
    result = await CaptionIngestService(session).save(parsed, file_id="f1")

    assert result.success is True
    assert result.movie is not None
    assert result.movie.season_id == result.season_id
    assert result.movie.episode_number == 1
    assert result.movie.quality == "1080p"

    series = await SeriesService(session).get_series_by_title("Naruto")
    assert series is not None
    assert series.id == result.series_id


async def test_save_second_episode_reuses_existing_series_and_season(session: AsyncSession) -> None:
    parsed1 = ParsedCaption(title="Naruto", season_number=1, episode_number=1)
    parsed2 = ParsedCaption(title="naruto", season_number=1, episode_number=2)
    service = CaptionIngestService(session)

    result1 = await service.save(parsed1, file_id="f1")
    result2 = await service.save(parsed2, file_id="f2")

    assert result1.series_id == result2.series_id
    assert result1.season_id == result2.season_id
    assert result1.movie is not None
    assert result2.movie is not None
    assert result1.movie.id != result2.movie.id
    assert result2.movie.episode_number == 2


async def test_save_episode_uses_parsed_episode_number_not_sequential_position(
    session: AsyncSession,
) -> None:
    """Regression guard: a bulk backfill processes a channel's posts in whatever order they're
    read, not necessarily episode order — the very first post handled for a season might be
    "Episode 47". Blindly auto-numbering it as episode 1 (SeriesService.add_episode's default,
    meant for the admin's no-caption-info bulk-forward flow) would silently mislabel it."""
    parsed = ParsedCaption(title="Naruto", season_number=1, episode_number=47)
    result = await CaptionIngestService(session).save(parsed, file_id="f1")

    assert result.success is True
    assert result.movie is not None
    assert result.movie.episode_number == 47


async def test_save_refuses_conflicting_episode_number(session: AsyncSession) -> None:
    parsed1 = ParsedCaption(title="Naruto", season_number=1, episode_number=5)
    parsed2 = ParsedCaption(title="Naruto", season_number=1, episode_number=5)
    service = CaptionIngestService(session)

    result1 = await service.save(parsed1, file_id="f1")
    result2 = await service.save(parsed2, file_id="f2")

    assert result1.success is True
    assert result2.success is False
    assert result2.reason == "episode_number_taken"

    # The original episode 5 is untouched — still pointing at its own file, not overwritten.
    assert result1.movie is not None
    refreshed = await MovieRepository(session).get(result1.movie.id)
    assert refreshed is not None
    assert refreshed.file_id == "f1"


async def test_save_standalone_movie_has_no_season(session: AsyncSession) -> None:
    parsed = ParsedCaption(title="Standalone Movie", year=2024)
    result = await CaptionIngestService(session).save(parsed, file_id="f1")

    assert result.success is True
    assert result.series_id is None
    assert result.season_id is None
    assert result.movie is not None
    assert result.movie.season_id is None
    assert result.movie.year == 2024


async def test_save_refuses_without_title(session: AsyncSession) -> None:
    parsed = ParsedCaption(title=None, episode_number=1)
    result = await CaptionIngestService(session).save(parsed, file_id="f1")

    assert result.success is False
    assert result.reason == "missing_title"


async def test_save_refuses_episode_without_season(session: AsyncSession) -> None:
    parsed = ParsedCaption(title="Ambiguous Show", episode_number=5, season_number=None)
    result = await CaptionIngestService(session).save(parsed, file_id="f1")

    assert result.success is False
    assert result.reason == "missing_season_number"
    assert await SeriesService(session).get_series_by_title("Ambiguous Show") is None


async def test_save_generates_unique_codes_for_duplicate_standalone_titles(session: AsyncSession) -> None:
    parsed = ParsedCaption(title="Duplicate Title")
    service = CaptionIngestService(session)

    result1 = await service.save(parsed, file_id="f1")
    result2 = await service.save(parsed, file_id="f2")

    assert result1.movie is not None
    assert result2.movie is not None
    assert result1.movie.code != result2.movie.code


async def test_save_passes_through_file_identity_fields(session: AsyncSession) -> None:
    parsed = ParsedCaption(title="Identity Test")
    result = await CaptionIngestService(session).save(
        parsed,
        file_id="f1",
        file_unique_id="uniq-1",
        storage_message_id=42,
    )

    assert result.movie is not None
    found = await MovieRepository(session).get_by_file_unique_id("uniq-1")
    assert found is not None
    assert found.id == result.movie.id
    assert found.storage_message_id == 42
