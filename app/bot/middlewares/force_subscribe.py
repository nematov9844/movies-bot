"""Gates ``content_gate``-flagged handlers behind ``ForceSubscribeService.check``.

Registered as an *inner* middleware on the ``message``/``callback_query``
observers (``dp.message.middleware`` / ``dp.callback_query.middleware``),
not as an outer middleware on ``dp.update`` — per-handler flags are only
resolvable via ``get_flag`` once aiogram has already matched a specific
handler (see ``TelegramEventObserver.trigger``: filters run first, then the
matched ``HandlerObject`` is placed in ``data["handler"]`` before inner
middlewares run), so a flag-based conditional gate has to live at this layer
to see the flag at all.

``data["event_update"]`` (the raw ``Update``) is already populated by
aiogram's ``Dispatcher._listen_update`` before any middleware runs, so no
extra outer-middleware plumbing is needed to reach it here.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.dispatcher.flags import get_flag
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.channel import force_subscribe_keyboard
from app.core.constants import PENDING_UPDATE_TTL_SECONDS, REDIS_KEY_PENDING_UPDATE
from app.core.logger import get_logger
from app.database.redis_client import get_redis
from app.services.force_subscribe.force_subscribe_service import ForceSubscribeService

logger = get_logger(__name__)

FORCE_SUBSCRIBE_TEXT = "📢 Botdan foydalanish uchun quyidagi kanal(lar)ga obuna bo'ling:"


def _resolve_chat_id(event: TelegramObject) -> int | None:
    if isinstance(event, Message):
        return event.chat.id
    if isinstance(event, CallbackQuery) and event.message is not None:
        return event.message.chat.id
    return None


class ForceSubscribeMiddleware(BaseMiddleware):
    """Blocks content delivery until every required, currently-enforceable channel is joined."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not get_flag(data, "content_gate"):
            return await handler(event, data)

        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        session: AsyncSession = data["session"]
        bot: Bot = data["bot"]

        blocking = await ForceSubscribeService(session, bot).check(tg_user.id)
        if not blocking:
            return await handler(event, data)

        update = data.get("event_update")
        if isinstance(update, Update):
            redis = get_redis()
            key = REDIS_KEY_PENDING_UPDATE.format(user_id=tg_user.id)
            await redis.set(key, update.model_dump_json(), ex=PENDING_UPDATE_TTL_SECONDS)

        chat_id = _resolve_chat_id(event)
        if chat_id is not None:
            await bot.send_message(chat_id, FORCE_SUBSCRIBE_TEXT, reply_markup=force_subscribe_keyboard(blocking))

        if isinstance(event, CallbackQuery):
            await event.answer()

        logger.info("force_subscribe_blocked", user_id=tg_user.id, channel_count=len(blocking))
        return None
