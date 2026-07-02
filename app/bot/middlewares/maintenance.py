from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.services.admin.admin_service import AdminService
from app.services.settings.settings_service import SettingsService

logger = get_logger(__name__)

MAINTENANCE_TEXT = "🛠 Texnik ishlar olib borilmoqda. Iltimos, birozdan so'ng qayta urinib ko'ring."


class MaintenanceMiddleware(BaseMiddleware):
    """Blocks non-admin updates while ``maintenance_mode`` setting is on.

    Runs after ``DbSessionMiddleware`` and ``UserUpsertMiddleware`` (needs
    both ``data["session"]`` and the user already upserted so
    ``AdminService`` lookups are meaningful).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        session: AsyncSession = data["session"]
        if not await SettingsService(session).get_bool("maintenance_mode", default=False):
            return await handler(event, data)

        tg_user = data.get("event_from_user")
        if tg_user is not None and await AdminService(session).is_admin(tg_user.id):
            return await handler(event, data)

        logger.info("maintenance_block", user_id=tg_user.id if tg_user else None)

        if event.message is not None:
            await event.message.answer(MAINTENANCE_TEXT)
        elif event.callback_query is not None:
            await event.callback_query.answer(MAINTENANCE_TEXT, show_alert=True)

        return None
