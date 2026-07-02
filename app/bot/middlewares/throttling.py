from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from app.core.constants import REDIS_KEY_THROTTLE
from app.core.logger import get_logger
from app.database.redis_client import get_redis

logger = get_logger(__name__)

THROTTLE_TTL_SECONDS = 1


class ThrottlingMiddleware(BaseMiddleware):
    """Limits each user to one heavy request per second (message/callback).

    "1 foydalanuvchi = sekundiga max 1 og'ir so'rov". Uses ``SET NX EX`` on
    a per-user Redis key; if the key is already set the update is dropped
    silently (no handler call, no reply) — this is the expected UX for
    double-taps, not an error worth surfacing to the user.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update) or not (event.message or event.callback_query):
            return await handler(event, data)

        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)

        redis = get_redis()
        key = REDIS_KEY_THROTTLE.format(user_id=tg_user.id)
        acquired = await redis.set(key, "1", nx=True, ex=THROTTLE_TTL_SECONDS)
        if not acquired:
            logger.debug("throttled", user_id=tg_user.id)
            return None

        return await handler(event, data)
