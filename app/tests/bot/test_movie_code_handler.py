import pytest
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.user.movie import (
    DEFAULT_NOT_FOUND_TEXT,
    PREMIUM_REQUIRED_TEXT,
    handle_movie_code,
)
from app.core.constants import REDIS_KEY_MOVIE_CODE, REDIS_KEY_PREMIUM, REDIS_KEY_SETTING
from app.database.redis_client import get_redis
from app.database.repositories.movie_repository import MovieRepository
from app.database.repositories.movie_view_repository import MovieViewRepository
from app.database.repositories.user_repository import UserRepository
from app.tests.bot.helpers import make_message

_TEST_USER_ID = 950001


async def _clear_cache_keys() -> None:
    redis = get_redis()
    await redis.delete(REDIS_KEY_MOVIE_CODE.format(code="handler-free"))
    await redis.delete(REDIS_KEY_MOVIE_CODE.format(code="handler-premium"))
    await redis.delete(REDIS_KEY_PREMIUM.format(user_id=_TEST_USER_ID))
    # A real bot process may have already cached this setting (hit or
    # "miss") in the same Redis this test talks to — cleared so the
    # not-found test reliably observes the DB-driven (test-isolated) state.
    await redis.delete(REDIS_KEY_SETTING.format(key="movie_not_found_text"))


@pytest.fixture(autouse=True)
async def _cleanup_cache():
    await _clear_cache_keys()
    yield
    await _clear_cache_keys()


def _configure_bot_identity(bot) -> None:
    bot.get_me.return_value = TgUser(id=1, is_bot=True, first_name="TestBot", username="test_bot")


async def test_movie_code_found_delivers_and_records_view(session: AsyncSession) -> None:
    await UserRepository(session).create(id=_TEST_USER_ID)  # UserUpsertMiddleware already ran
    movie = await MovieRepository(session).create(
        code="handler-free", title="Handler Movie", file_id="file-abc"
    )
    await session.commit()
    message, bot = make_message(_TEST_USER_ID, "handler-free")
    _configure_bot_identity(bot)

    await handle_movie_code(message, session, bot)

    bot.send_video.assert_awaited_once()
    call_kwargs = bot.send_video.await_args.kwargs
    assert call_kwargs["video"] == "file-abc"

    refreshed = await MovieRepository(session).get(movie.id)
    assert refreshed.view_count == 1
    views = await MovieViewRepository(session).get_many(movie_id=movie.id, user_id=_TEST_USER_ID)
    assert len(views) == 1


async def test_movie_code_not_found_sends_default_text(session: AsyncSession) -> None:
    message, bot = make_message(_TEST_USER_ID, "no-such-code")

    await handle_movie_code(message, session, bot)

    bot.send_video.assert_not_called()
    sent = bot.await_args.args[0]
    assert sent.text == DEFAULT_NOT_FOUND_TEXT


async def test_movie_code_premium_gate_blocks_non_premium_user(session: AsyncSession) -> None:
    await MovieRepository(session).create(
        code="handler-premium", title="Premium Movie", file_id="file-xyz", is_premium=True
    )
    await session.commit()
    message, bot = make_message(_TEST_USER_ID, "handler-premium")
    _configure_bot_identity(bot)

    await handle_movie_code(message, session, bot)

    bot.send_video.assert_not_called()
    bot.send_message.assert_awaited_once_with(message.chat.id, PREMIUM_REQUIRED_TEXT)
