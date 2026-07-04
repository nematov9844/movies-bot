from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.core.metrics import bot_updates_total


class MetricsMiddleware(BaseMiddleware):
    """Counts every update in ``bot_updates_total``, regardless of what any later middleware does.

    Registered first among the outer middlewares (before ``DbSessionMiddleware``)
    so it can't be skipped by something further down the chain
    short-circuiting (e.g. maintenance mode, throttling).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot_updates_total.inc()
        return await handler(event, data)
