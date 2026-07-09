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


async def test_save_replaces_existing_episode_when_collision_replacement_opted_in(
    session: AsyncSession,
) -> None:
    """A caller-designated better-quality source (e.g. a channel the owner has confirmed
    uploads in higher quality than what's already in the catalog) overwrites the existing
    row on a collision instead of refusing it — same episode identity (id, season, number),
    just a newer file behind it."""
    parsed1 = ParsedCaption(title="Naruto", season_number=1, episode_number=5, quality="480p")
    parsed2 = ParsedCaption(title="Naruto", season_number=1, episode_number=5, quality="1080p")
    service = CaptionIngestService(session)

    result1 = await service.save(parsed1, file_id="f1")
    result2 = await service.save(parsed2, file_id="f2", replace_on_collision=True)

    assert result1.success is True
    assert result2.success is True
    assert result2.reason == "replaced_existing_episode"
    assert result1.movie is not None
    assert result2.movie is not None
    assert result2.movie.id == result1.movie.id  # same row, not a new episode

    refreshed = await MovieRepository(session).get(result1.movie.id)
    assert refreshed is not None
    assert refreshed.file_id == "f2"
    assert refreshed.quality == "1080p"
    assert refreshed.episode_number == 5


async def test_save_refuses_collision_replacement_when_part_marker_seen(session: AsyncSession) -> None:
    """Regression guard: a part/cour-split season's episode numbers only count within
    their own part — a collision on one of these is *not* good evidence it's the same
    episode re-uploaded, so even an opted-in "trusted source" replace must not clobber
    it blindly; this needs a human to work out the real running episode number."""
    parsed1 = ParsedCaption(title="Naruto", season_number=3, episode_number=1)
    parsed2 = ParsedCaption(title="Naruto", season_number=3, episode_number=1, part_marker_seen=True)
    service = CaptionIngestService(session)

    result1 = await service.save(parsed1, file_id="f1")
    result2 = await service.save(parsed2, file_id="f2", replace_on_collision=True)

    assert result1.success is True
    assert result2.success is False
    assert result2.reason == "episode_number_taken"

    refreshed = await MovieRepository(session).get(result1.movie.id)  # type: ignore[union-attr]
    assert refreshed is not None
    assert refreshed.file_id == "f1"  # untouched


async def test_save_standalone_movie_has_no_season(session: AsyncSession) -> None:
    parsed = ParsedCaption(title="Standalone Movie", year=2024)
    result = await CaptionIngestService(session).save(parsed, file_id="f1")

    assert result.success is True
    assert result.series_id is None
    assert result.season_id is None
    assert result.movie is not None
    assert result.movie.season_id is None
    assert result.movie.year == 2024


async def test_save_tags_source_channel_separately_from_description(session: AsyncSession) -> None:
    """``source_label`` lands in the dedicated ``source_channel`` column, not
    ``description`` — the latter stays free for an actual synopsis added later."""
    parsed = ParsedCaption(title="Standalone Movie")
    result = await CaptionIngestService(session).save(parsed, file_id="f1", source_label="AniBro")

    assert result.movie is not None
    assert result.movie.source_channel == "AniBro"
    assert result.movie.description is None


async def test_save_refuses_without_title(session: AsyncSession) -> None:
    parsed = ParsedCaption(title=None, episode_number=1)
    result = await CaptionIngestService(session).save(parsed, file_id="f1")

    assert result.success is False
    assert result.reason == "missing_title"


async def test_save_episode_without_season_defaults_to_season_one(session: AsyncSession) -> None:
    parsed = ParsedCaption(title="Ambiguous Show", episode_number=5, season_number=None)
    result = await CaptionIngestService(session).save(parsed, file_id="f1")

    assert result.success is True
    assert result.movie is not None
    assert result.movie.episode_number == 5

    series_service = SeriesService(session)
    series = await series_service.get_series_by_title("Ambiguous Show")
    assert series is not None
    season = await series_service.get_season_by_number(series.id, 1)
    assert season is not None
    assert season.id == result.season_id


async def test_save_refuses_episode_marker_without_number_instead_of_filing_as_movie(
    session: AsyncSession,
) -> None:
    """Regression guard: a caption that mentions an episode ("qism") but whose
    number never resolved must not be silently saved as a standalone movie —
    that would misfile someone's episode outside its show entirely."""
    parsed = ParsedCaption(title="Some Show", episode_marker_seen=True)
    result = await CaptionIngestService(session).save(parsed, file_id="f1")

    assert result.success is False
    assert result.reason == "ambiguous_episode_number"
    assert await SeriesService(session).get_series_by_title("Some Show") is None


async def test_save_refuses_short_clip_with_small_file_size(session: AsyncSession) -> None:
    """Regression guard: a promotional teaser/trailer forwarded from a channel's history
    often carries a real-looking title (and sometimes even an episode marker) but is far
    too short to be the actual content — auto-saving it would silently misrepresent it as
    a real episode/movie a user could tap into."""
    parsed = ParsedCaption(title="Some Show Teaser", episode_number=1)
    result = await CaptionIngestService(session).save(parsed, file_id="f1", duration=45, file_size=5 * 1024 * 1024)

    assert result.success is False
    assert result.reason == "suspiciously_short_duration"


async def test_save_keeps_short_duration_with_large_file_size(session: AsyncSession) -> None:
    """A real episode can report a bogus near-zero duration (a known Telegram metadata
    quirk for some containers) while its file size still gives away that it's the genuine
    full-length video — that combination must not be flagged as a teaser clip."""
    parsed = ParsedCaption(title="Some Show", episode_number=1)
    result = await CaptionIngestService(session).save(
        parsed, file_id="f1", duration=0, file_size=500 * 1024 * 1024
    )

    assert result.success is True


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
