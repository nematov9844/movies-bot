import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from app.bot.middlewares import (
    DbSessionMiddleware,
    ForceSubscribeMiddleware,
    MaintenanceMiddleware,
    ThrottlingMiddleware,
    UserUpsertMiddleware,
)
from app.bot.routers import main_router
from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from app.database.session import async_session_factory
from app.services.admin.admin_service import AdminService

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

    # Inner (not outer) middleware: per-handler flags like `content_gate` are
    # only resolvable once aiogram has matched a specific handler, which
    # only happens inside the message/callback_query observers, not on the
    # shared dp.update observer used above. See ForceSubscribeMiddleware's
    # docstring for the full reasoning.
    force_subscribe_middleware = ForceSubscribeMiddleware()
    dp.message.middleware(force_subscribe_middleware)
    dp.callback_query.middleware(force_subscribe_middleware)


async def _ensure_owner_seeded() -> None:
    async with async_session_factory() as session:
        await AdminService(session).ensure_owner_seeded()
        await session.commit()


async def main() -> None:
    setup_logging()
    await _ensure_owner_seeded()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # Redis-backed FSM storage: the add-movie wizard (Phase 6) is the first
    # flow needing multi-step state, and the TZ designates Redis as the
    # bot's FSM store, so state survives bot restarts/redeploys instead of
    # living only in process memory.
    dp = Dispatcher(storage=RedisStorage.from_url(settings.redis_url))
    _setup_middlewares(dp)
    dp.include_router(main_router)

    logger.info("bot_starting", environment=settings.environment)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
