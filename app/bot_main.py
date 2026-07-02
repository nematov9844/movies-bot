import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.middlewares import (
    DbSessionMiddleware,
    MaintenanceMiddleware,
    ThrottlingMiddleware,
    UserUpsertMiddleware,
)
from app.bot.routers import main_router
from app.core.config import settings
from app.core.logger import get_logger, setup_logging

logger = get_logger(__name__)


def _setup_middlewares(dp: Dispatcher) -> None:
    # Order matters: DB session must exist before anything that touches the
    # database; the user must be upserted before maintenance/throttling look
    # it up. Registered on dp.update so they apply to every update type
    # (message, callback_query, ...), not just messages.
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(UserUpsertMiddleware())
    dp.update.outer_middleware(MaintenanceMiddleware())
    dp.update.outer_middleware(ThrottlingMiddleware())


async def main() -> None:
    setup_logging()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    _setup_middlewares(dp)
    dp.include_router(main_router)

    logger.info("bot_starting", environment=settings.environment)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
