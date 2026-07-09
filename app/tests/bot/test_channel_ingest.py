from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin.channel_ingest import (
    _is_configured_source_channel,
    _prefers_replace_on_collision,
    auto_ingest_from_source_channel,
    auto_ingest_from_storage_forward,
)
from app.core.config import settings
from app.database.repositories.movie_repository import MovieRepository
from app.services.series.series_service import SeriesService
from app.tests.bot.helpers import make_channel_post, make_video


def test_prefers_replace_on_collision_matches_anibro_regardless_of_full_display_name() -> None:
    assert _prefers_replace_on_collision("AniBro ⛩ | O'zbekcha Animelar 🇺🇿") is True
    assert _prefers_replace_on_collision("JEKIANIME") is False
    assert _prefers_replace_on_collision(None) is False


def test_is_configured_source_channel(monkeypatch: object) -> None:
    monkeypatch.setattr(settings, "source_channels", "JEKIANIME,JEKIKINO")  # type: ignore[attr-defined]
    message, _ = make_channel_post(-100123, chat_username="jekianime")
    assert _is_configured_source_channel(message) is True

    other, _ = make_channel_post(-100123, chat_username="somebodyelse")
    assert _is_configured_source_channel(other) is False

    no_username, _ = make_channel_post(-100123, chat_username=None)
    assert _is_configured_source_channel(no_username) is False


async def test_auto_ingest_from_source_channel_relays_and_saves(session: AsyncSession) -> None:
    relayed_video = make_video(file_id="storage-file-id", file_unique_id="storage-unique-id")
    message, bot = make_channel_post(
        -100999, chat_username="jekianime", caption="Naruto\nSeason 1 Episode 5\n1080p", video=make_video()
    )
    sent = Message.model_construct(message_id=77, date=message.date, chat=message.chat, video=relayed_video)
    bot.send_video.return_value = sent

    await auto_ingest_from_source_channel(message, bot, session)

    bot.send_video.assert_awaited_once()
    call_kwargs = bot.send_video.await_args.kwargs
    assert call_kwargs["chat_id"] == settings.storage_channel_id
    assert call_kwargs["video"] == message.video.file_id

    series = await SeriesService(session).get_series_by_title("Naruto")
    assert series is not None
    season = await SeriesService(session).get_season_by_number(series.id, 1)
    assert season is not None
    episodes, total = await SeriesService(session).list_episodes(season.id, limit=10, offset=0)
    assert total == 1
    assert episodes[0].episode_number == 5
    assert episodes[0].quality == "1080p"
    assert episodes[0].storage_message_id == 77
    bot.send_message.assert_not_called()


async def test_auto_ingest_from_source_channel_skips_when_relay_send_fails(session: AsyncSession) -> None:
    message, bot = make_channel_post(
        -100999, chat_username="jekianime", caption="Naruto\nEpisode 5", video=make_video()
    )
    bot.send_video.return_value = Message.model_construct(
        message_id=1, date=message.date, chat=message.chat, video=None
    )

    await auto_ingest_from_source_channel(message, bot, session)

    assert await SeriesService(session).get_series_by_title("Naruto") is None


async def test_auto_ingest_from_storage_forward_saves_standalone_movie(session: AsyncSession) -> None:
    video = make_video(file_id="backfill-file-id", file_unique_id="backfill-unique-id")
    message, bot = make_channel_post(
        settings.storage_channel_id,
        caption="Inception (2010)\n1080p",
        video=video,
        forwarded=True,
        message_id=555,
    )

    await auto_ingest_from_storage_forward(message, bot, session)

    found = await MovieRepository(session).get_by_file_unique_id("backfill-unique-id")
    assert found is not None
    assert found.title == "Inception"
    assert found.year == 2010
    assert found.quality == "1080p"
    assert found.storage_message_id == 555
    bot.send_message.assert_not_called()


async def test_auto_ingest_from_storage_forward_tags_source_channel(session: AsyncSession) -> None:
    """When the forward carries its original channel's identity (real forwards from a
    backfilled channel do), the saved row's dedicated ``source_channel`` column names it —
    kept separate from ``description`` so an admin can still attach a real synopsis there
    later without it colliding with this tag."""
    video = make_video(file_id="anibro-file-id", file_unique_id="anibro-unique-id")
    message, bot = make_channel_post(
        settings.storage_channel_id,
        caption="Naruto\nEpisode 5",
        video=video,
        forwarded=True,
        origin_chat_title="AniBro",
    )

    await auto_ingest_from_storage_forward(message, bot, session)

    series = await SeriesService(session).get_series_by_title("Naruto")
    assert series is not None
    assert series.source_channel == "AniBro"
    assert series.description is None

    season = await SeriesService(session).get_season_by_number(series.id, 1)
    assert season is not None
    episodes, _ = await SeriesService(session).list_episodes(season.id, limit=10, offset=0)
    assert episodes[0].source_channel == "AniBro"
    assert episodes[0].description is None


async def test_auto_ingest_from_anibro_replaces_existing_episode_on_collision(
    session: AsyncSession,
) -> None:
    """AniBro is a known-better-quality source (an explicit call from the owner) — a
    re-upload of an episode already in the catalog from an earlier backfill overwrites
    that row instead of bouncing to the owner as an unresolved duplicate."""
    existing_video = make_video(file_id="old-file-id", file_unique_id="old-unique-id")
    existing_message, existing_bot = make_channel_post(
        settings.storage_channel_id, caption="Naruto\nEpisode 5\n480p", video=existing_video, forwarded=True
    )
    await auto_ingest_from_storage_forward(existing_message, existing_bot, session)
    existing = await MovieRepository(session).get_by_file_unique_id("old-unique-id")
    assert existing is not None

    anibro_video = make_video(file_id="anibro-file-id", file_unique_id="anibro-unique-id")
    anibro_message, anibro_bot = make_channel_post(
        settings.storage_channel_id,
        caption="Naruto\nEpisode 5\n1080p",
        video=anibro_video,
        forwarded=True,
        origin_chat_title="AniBro ⛩ | O'zbekcha Animelar 🇺🇿",
        message_id=2,
    )
    await auto_ingest_from_storage_forward(anibro_message, anibro_bot, session)

    refreshed = await MovieRepository(session).get(existing.id)
    assert refreshed is not None
    assert refreshed.file_unique_id == "anibro-unique-id"
    assert refreshed.quality == "1080p"
    assert refreshed.episode_number == 5
    anibro_bot.send_video.assert_not_called()  # replaced cleanly, no failure DM


async def test_auto_ingest_dms_owner_on_parse_failure(session: AsyncSession) -> None:
    video = make_video(file_id="unparseable-file-id", file_unique_id="unparseable-unique-id")
    message, bot = make_channel_post(
        settings.storage_channel_id, caption="🔥🔥🔥", video=video, forwarded=True
    )

    await auto_ingest_from_storage_forward(message, bot, session)

    bot.send_video.assert_awaited_once()
    call_args = bot.send_video.await_args
    assert call_args.args[0] == settings.owner_id
    assert "missing_title" in call_args.kwargs["caption"]
