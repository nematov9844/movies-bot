"""Saves a ``ParsedCaption`` into the database through the exact same
``MovieService``/``SeriesService`` calls ``movie_add.py``/``series_manage.py``
already use — a parsed post ends up indistinguishable from one entered by
hand, and gets the same category/premium/audit-log handling for free.

This never writes raw SQL of its own and never guesses at anything the
parser left ambiguous, with one exception:
- no ``title`` at all -> can't name a movie or a series.
- an ``episode_number`` with no ``season_number`` -> defaults to season 1.
  Most real-world channels never mention a season at all in their captions
  (they're single-season shows, or just don't bother), so treating "no
  season marker" as season 1 matches reality far more often than it doesn't.
- no ``episode_number`` at all -> saved as a standalone movie, *unless* the
  caption itself uses an episode word ("qism"/"epizod"/"episode") without a
  number ever resolving next to it (``episode_marker_seen``) — that's someone
  else's episode we simply failed to read the number of, not a movie, and
  filing it as one would silently misplace it outside its show entirely.
- a parsed ``episode_number`` that's already taken in that season -> refuses
  rather than silently renumbering or overwriting the existing row (this
  matters for bulk backfills off a channel's full history, where posts
  aren't necessarily processed in episode order and a real duplicate/
  mislabeled post is exactly the kind of thing a human should look at) —
  *unless* the caller explicitly opts in via ``replace_on_collision`` (set by
  the caller for a source known to carry better quality than what's already
  in the catalog), in which case the existing row's file is overwritten in
  place instead of refused.
"""

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Movie
from app.database.repositories.movie_repository import MovieRepository
from app.services.movie.movie_service import MovieService
from app.services.parser.caption_parser import ParsedCaption
from app.services.series.series_service import SeriesService

_SLUG_INVALID_RE = re.compile(r"[^a-z0-9]+")
_SLUG_MAX_LEN = 20
_CODE_MAX_LEN = 32

# A real episode/movie is never this short — trailers, teaser clips, and
# promotional "coming soon" snippets are. Gated on file size too so a genuine
# full-length video with missing/zero duration metadata (a known Telegram
# quirk for some containers) isn't misflagged just because its duration
# field came back empty.
_MIN_CONTENT_DURATION_SECONDS = 180
_MIN_CONTENT_FILE_SIZE_BYTES = 60 * 1024 * 1024


def _slugify(text: str, max_len: int = _SLUG_MAX_LEN) -> str:
    slug = _SLUG_INVALID_RE.sub("-", text.lower()).strip("-")
    return (slug or "item")[:max_len]


@dataclass(slots=True)
class IngestResult:
    success: bool
    reason: str | None = None
    movie: Movie | None = None
    series_id: int | None = None
    season_id: int | None = None


class CaptionIngestService:
    def __init__(self, session: AsyncSession) -> None:
        self._movie_repo = MovieRepository(session)
        self._movie_service = MovieService(session)
        self._series_service = SeriesService(session)

    async def save(
        self,
        parsed: ParsedCaption,
        *,
        file_id: str,
        file_unique_id: str | None = None,
        storage_message_id: int | None = None,
        duration: int | None = None,
        file_size: int | None = None,
        is_premium: bool = False,
        created_by: int | None = None,
        source_label: str | None = None,
        replace_on_collision: bool = False,
    ) -> IngestResult:
        if not parsed.title:
            return IngestResult(success=False, reason="missing_title")

        if (
            duration is not None
            and duration < _MIN_CONTENT_DURATION_SECONDS
            and (file_size is None or file_size < _MIN_CONTENT_FILE_SIZE_BYTES)
        ):
            return IngestResult(success=False, reason="suspiciously_short_duration")

        if parsed.is_episode:
            return await self._save_episode(
                parsed,
                file_id=file_id,
                file_unique_id=file_unique_id,
                storage_message_id=storage_message_id,
                duration=duration,
                file_size=file_size,
                is_premium=is_premium,
                created_by=created_by,
                source_channel=source_label,
                replace_on_collision=replace_on_collision,
            )

        if parsed.episode_marker_seen:
            return IngestResult(success=False, reason="ambiguous_episode_number")

        code = await self._unique_code(parsed.title)
        movie = await self._movie_service.create_movie(
            code=code,
            title=parsed.title,
            description=None,
            file_id=file_id,
            file_unique_id=file_unique_id,
            storage_message_id=storage_message_id,
            duration=duration,
            file_size=file_size,
            is_premium=is_premium,
            created_by=created_by,
            quality=parsed.quality,
            year=parsed.year,
            source_channel=source_label,
        )
        return IngestResult(success=True, movie=movie)

    async def _save_episode(
        self,
        parsed: ParsedCaption,
        *,
        file_id: str,
        file_unique_id: str | None,
        storage_message_id: int | None,
        duration: int | None,
        file_size: int | None,
        is_premium: bool,
        created_by: int | None,
        source_channel: str | None = None,
        replace_on_collision: bool = False,
    ) -> IngestResult:
        title = parsed.title
        season_number = parsed.season_number if parsed.season_number is not None else 1
        assert title is not None

        series = await self._series_service.get_series_by_title(title)
        if series is None:
            series = await self._series_service.create_series(title, source_channel=source_channel)

        season = await self._series_service.get_season_by_number(series.id, season_number)
        if season is None:
            season = await self._series_service.create_season(series.id, season_number)

        episode_number = parsed.episode_number
        assert episode_number is not None  # guaranteed by ``parsed.is_episode``
        clash = await self._movie_repo.get_by_season_and_episode(season.id, episode_number)
        if clash is not None:
            # A part/cour marker means this episode number only counts within its own
            # part, not across the whole season — a collision here is *not* good evidence
            # this is the same episode re-uploaded, so it's never auto-replaced even for an
            # otherwise-trusted source; a human needs to work out the real running number.
            if not replace_on_collision or parsed.part_marker_seen:
                return IngestResult(
                    success=False,
                    reason="episode_number_taken",
                    series_id=series.id,
                    season_id=season.id,
                )
            updated = await self._movie_repo.update(
                clash.id,
                file_id=file_id,
                file_unique_id=file_unique_id,
                storage_message_id=storage_message_id,
                duration=duration,
                file_size=file_size,
                quality=parsed.quality,
                year=parsed.year,
                source_channel=source_channel,
            )
            assert updated is not None  # clash was just fetched by this same id
            return IngestResult(
                success=True,
                reason="replaced_existing_episode",
                movie=updated,
                series_id=series.id,
                season_id=season.id,
            )

        episode = await self._series_service.add_episode(
            season_id=season.id,
            series_title=series.title,
            season_number=season.number,
            file_id=file_id,
            file_unique_id=file_unique_id,
            storage_message_id=storage_message_id,
            duration=duration,
            file_size=file_size,
            is_premium=is_premium,
            created_by=created_by,
            quality=parsed.quality,
            year=parsed.year,
            episode_number=episode_number,
            source_channel=source_channel,
        )
        return IngestResult(success=True, movie=episode, series_id=series.id, season_id=season.id)

    async def _unique_code(self, title: str) -> str:
        base_code = _slugify(title)
        code = base_code
        suffix = 1
        while await self._movie_repo.get_by_code(code) is not None:
            suffix += 1
            code = f"{base_code}-{suffix}"[:_CODE_MAX_LEN]
        return code
