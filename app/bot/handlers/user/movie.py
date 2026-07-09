"""User-facing movie-code delivery: the "raqam/kod" flow from the TZ.

Also hosts ``deliver_movie``, the shared access-check + send + record-view
helper reused by the search/list handlers in ``movie_search.py`` so delivery
logic lives in exactly one place.
"""

import re

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MOVIE_CODE_PATTERN
from app.core.logger import get_logger
from app.services.movie.movie_service import MovieCard, MovieService
from app.services.settings.settings_service import SettingsService

router = Router(name="user_movie")
logger = get_logger(__name__)

_MOVIE_CODE_RE = re.compile(MOVIE_CODE_PATTERN)

DEFAULT_NOT_FOUND_TEXT = "Kechirasiz, bunday kodli kino topilmadi."
PREMIUM_REQUIRED_TEXT = (
    "⭐ Bu kino premium foydalanuvchilar uchun. "
    'Asosiy menyudagi "⭐ Premium" bo\'limi orqali premiumga o\'ting.'
)


async def deliver_movie(bot: Bot, session: AsyncSession, chat_id: int, user_id: int, movie: MovieCard) -> None:
    """Shared "send this movie" flow for code lookup, search results, and list taps.

    Checks premium access, sends the video (or explains why not), and
    records the view — kept in one place so the three delivery entry points
    (code lookup here, search/top/new/popular/category taps in
    ``movie_search.py``) can't drift out of sync.
    """
    service = MovieService(session)
    if not await service.check_access(user_id, movie):
        await bot.send_message(chat_id, PREMIUM_REQUIRED_TEXT)
        return

    bot_info = await bot.get_me()
    source_line = f"📡 Manba: {movie.source_channel}\n\n" if movie.source_channel else ""
    caption = f"🎬 <b>{movie.title}</b>\n\n{movie.description or ''}\n\n{source_line}🤖 @{bot_info.username}"
    await bot.send_video(chat_id=chat_id, video=movie.file_id, caption=caption)
    await service.record_view(movie.id, user_id)
    logger.info("movie_delivered", movie_code=movie.code, user_id=user_id)


@router.message(F.text.regexp(_MOVIE_CODE_RE), flags={"content_gate": True})
async def handle_movie_code(message: Message, session: AsyncSession, bot: Bot) -> None:
    """Looks up ``message.text`` as a movie code and delivers it if found.

    Registered after every reply-menu-button handler (see
    ``app/bot/handlers/user/__init__.py``) so exact button text is always
    consumed by its own handler first — this one only ever sees text that
    matched none of them.

    ``content_gate``: Phase 7's ForceSubscribeMiddleware will check
    ``get_flag(data, "content_gate")`` to decide whether to enforce the
    force-subscribe check before this (and every other content-serving
    handler in this phase) runs.
    """
    user = message.from_user
    if user is None:
        return

    code = (message.text or "").strip()
    movie = await MovieService(session).get_by_code_cached(code)
    if movie is None:
        text = await SettingsService(session).get("movie_not_found_text") or DEFAULT_NOT_FOUND_TEXT
        await message.answer(text)
        return

    await deliver_movie(bot, session, message.chat.id, user.id, movie)


@router.callback_query(F.data.startswith("mv:deliver:"), flags={"content_gate": True})
async def deliver_from_callback(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    """Delivers a movie tapped from a search/top/new/popular/category list."""
    if callback.data is None:
        await callback.answer()
        return

    code = callback.data.removeprefix("mv:deliver:")
    movie = await MovieService(session).get_by_code_cached(code)
    await callback.answer()
    if movie is None:
        return

    await deliver_movie(bot, session, callback.from_user.id, callback.from_user.id, movie)
