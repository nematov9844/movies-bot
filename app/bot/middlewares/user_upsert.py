from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.services.user.user_service import UserService

logger = get_logger(__name__)


class UserUpsertMiddleware(BaseMiddleware):
    """Keeps the ``users`` row for the acting Telegram user up to date.

    Runs after ``DbSessionMiddleware`` (needs ``data["session"]``) and
    relies on aiogram's built-in ``UserContextMiddleware`` having already
    populated ``data["event_from_user"]`` for the current update, so it
    works uniformly across messages, callback queries, and any other
    update type that carries a ``from_user``.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is not None:
            session: AsyncSession = data["session"]
            await UserService(session).upsert_from_telegram(tg_user)
            logger.debug("user_upserted", user_id=tg_user.id)

        return await handler(event, data)
