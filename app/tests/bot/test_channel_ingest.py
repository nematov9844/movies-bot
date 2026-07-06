from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin.channel_ingest import (
    _is_configured_source_channel,
    auto_ingest_from_source_channel,
    auto_ingest_from_storage_forward,
)
from app.core.config import settings
from app.services.series.series_service import SeriesService
from app.tests.bot.helpers import make_channel_post, make_video


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

    from app.database.repositories.movie_repository import MovieRepository

    found = await MovieRepository(session).get_by_file_unique_id("backfill-unique-id")
    assert found is not None
    assert found.title == "Inception"
    assert found.year == 2010
    assert found.quality == "1080p"
    assert found.storage_message_id == 555
    bot.send_message.assert_not_called()


async def test_auto_ingest_dms_owner_on_parse_failure(session: AsyncSession) -> None:
    video = make_video(file_id="unparseable-file-id", file_unique_id="unparseable-unique-id")
    message, bot = make_channel_post(
        settings.storage_channel_id, caption="🔥🔥🔥", video=video, forwarded=True
    )

    await auto_ingest_from_storage_forward(message, bot, session)

    bot.send_message.assert_awaited_once()
    call_args = bot.send_message.await_args
    assert call_args.args[0] == settings.owner_id
    assert "missing_title" in call_args.args[1]
