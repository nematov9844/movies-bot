"""Phase 11: in-process APScheduler wiring.

Runs inside the bot process rather than as a separate service — per the
TZ, "Bot process ichida ishga tushadi". ``create_scheduler`` is called
once from ``bot_main.main()`` with the already-constructed ``Bot``
instance, since the premium-expiry job needs it to DM users.
"""

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.scheduler.jobs import (
    cleanup_stale_redis_keys,
    deactivate_expired_channels,
    export_settings_json,
    flush_daily_statistics,
    process_premium_expiry,
    run_database_backup,
)


def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    scheduler.add_job(
        deactivate_expired_channels, IntervalTrigger(minutes=5), id="channel_expiry"
    )
    scheduler.add_job(
        process_premium_expiry, IntervalTrigger(minutes=30), args=[bot], id="premium_expiry"
    )
    scheduler.add_job(flush_daily_statistics, CronTrigger(hour=0, minute=5), id="stats_flush")
    scheduler.add_job(run_database_backup, CronTrigger(hour=3, minute=0), id="db_backup")
    scheduler.add_job(cleanup_stale_redis_keys, IntervalTrigger(hours=1), id="redis_cleanup")
    # Phase 16: weekly settings JSON export, alongside the daily DB backup.
    scheduler.add_job(
        export_settings_json, CronTrigger(day_of_week="mon", hour=4, minute=0), id="settings_export"
    )

    return scheduler


__all__ = ["create_scheduler"]
