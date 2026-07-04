"""Job functions for Phase 11's in-process APScheduler.

Every job opens its own DB session and always logs+swallows its own
exceptions — the TZ's "bitta job yiqilsa boshqalari ishlashda davom
etadi" (one job failing must never take the others down with it) — so
``app.scheduler.create_scheduler`` doesn't need any job-level error
handling of its own.
"""

import asyncio
from datetime import date, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.core.constants import (
    PREMIUM_WARNED_TTL_SECONDS,
    PREMIUM_WARNING_HOURS,
    REDIS_KEY_PREMIUM_WARNED,
)
from app.core.logger import get_logger
from app.database.redis_client import get_redis
from app.database.repositories.channel_repository import ChannelRepository
from app.database.session import async_session_factory
from app.services.channel.channel_service import ChannelService
from app.services.premium.premium_service import PremiumService
from app.services.stats.stats_service import StatsService

logger = get_logger(__name__)


async def deactivate_expired_channels() -> None:
    try:
        async with async_session_factory() as session:
            flipped = await ChannelService(session).deactivate_expired_and_over_limit()
            await session.commit()
        if flipped:
            logger.info("channels_deactivated", channel_ids=[c.id for c in flipped])
    except Exception:
        logger.exception("channel_expiry_job_failed")


async def process_premium_expiry(bot: Bot) -> None:
    """Deactivates expired premium rows (DM'ing each user) and DMs a one-time 24h warning to the rest.

    The warning uses a Redis ``SET NX`` per ``premium_user.id`` so a
    subscription expiring within the window only gets DM'd once across
    however many 30-minute runs fall inside that window, instead of every
    run re-notifying the same user.
    """
    try:
        async with async_session_factory() as session:
            service = PremiumService(session)
            expired = await service.deactivate_expired()
            expiring_soon = await service.find_expiring_within(PREMIUM_WARNING_HOURS)
            await session.commit()

        for premium_user in expired:
            try:
                await bot.send_message(
                    premium_user.user_id, "⌛️ Sizning premium obunangiz muddati tugadi."
                )
            except TelegramAPIError as exc:
                logger.warning("premium_expiry_dm_failed", user_id=premium_user.user_id, error=str(exc))

        redis = get_redis()
        warned_count = 0
        for premium_user in expiring_soon:
            warned_key = REDIS_KEY_PREMIUM_WARNED.format(premium_user_id=premium_user.id)
            first_warning = await redis.set(warned_key, "1", nx=True, ex=PREMIUM_WARNED_TTL_SECONDS)
            if not first_warning:
                continue
            warned_count += 1
            try:
                await bot.send_message(
                    premium_user.user_id,
                    "⏰ Sizning premium obunangiz 24 soatdan keyin tugaydi.",
                )
            except TelegramAPIError as exc:
                logger.warning("premium_warning_dm_failed", user_id=premium_user.user_id, error=str(exc))

        if expired or warned_count:
            logger.info("premium_expiry_processed", expired=len(expired), warned=warned_count)
    except Exception:
        logger.exception("premium_expiry_job_failed")


async def flush_daily_statistics() -> None:
    """Flushes yesterday's live Redis counters into the ``statistics`` table.

    Runs at 00:05 — yesterday, not today, since it's the day that just
    ended a few minutes ago that needs its final snapshot recorded.
    """
    try:
        yesterday = date.today() - timedelta(days=1)
        async with async_session_factory() as session:
            row = await StatsService(session).flush_today(yesterday)
            await session.commit()
        logger.info("statistics_flushed", date=str(row.date))
    except Exception:
        logger.exception("statistics_flush_job_failed")


async def run_database_backup() -> None:
    """Shells out to ``scripts/backup.sh`` (pg_dump + gzip + 7-day rotation)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash",
            "scripts/backup.sh",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(
                "backup_job_failed",
                returncode=proc.returncode,
                stderr=stderr.decode(errors="replace").strip(),
            )
        else:
            logger.info("backup_job_done", output=stdout.decode(errors="replace").strip())
    except Exception:
        logger.exception("backup_job_crashed")


async def cleanup_stale_redis_keys() -> None:
    """Deletes ``fs:joined:{channel_id}`` sets whose channel no longer exists.

    Every other application-managed Redis key already carries an explicit
    TTL (movie/premium/force-sub/setting caches, the per-user throttle key,
    the premium-warning marker above) and self-expires on its own; the
    force-subscribe join-dedup set is the one durable, TTL-less structure
    that can outlive its row after a hard delete
    (``ChannelService.delete_channel``), so it's the only thing this hourly
    job needs to sweep. Uses ``SCAN`` (not ``KEYS``) so it never blocks
    Redis while walking the keyspace.
    """
    try:
        redis = get_redis()
        deleted = 0
        async with async_session_factory() as session:
            repo = ChannelRepository(session)
            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor, match="fs:joined:*", count=100)
                for key in keys:
                    channel_id = int(key.removeprefix("fs:joined:"))
                    if await repo.get_by_channel_id(channel_id) is None:
                        await redis.delete(key)
                        deleted += 1
                if cursor == 0:
                    break
        if deleted:
            logger.info("stale_redis_keys_cleaned", count=deleted)
    except Exception:
        logger.exception("redis_cleanup_job_failed")
