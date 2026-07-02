from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.core.logger import get_logger
from app.database.session import async_session_factory

logger = get_logger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    """Opens one ``AsyncSession`` per update (session-per-update pattern).

    The session is exposed to downstream middlewares/handlers via
    ``data["session"]``. Committed on success, rolled back on exception,
    always closed. Must be the first outer middleware registered — every
    other middleware/handler that touches the database relies on
    ``data["session"]`` already being present.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with async_session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                logger.debug("db_session_rolled_back")
                raise
            else:
                await session.commit()
                return result
