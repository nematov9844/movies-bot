"""Broadcast send worker: the rate-limited ``copy_message`` loop over a
broadcast's target audience.

Started via ``schedule_broadcast`` (``asyncio.create_task`` under the hood)
from the confirm handler in ``app/bot/handlers/admin/broadcast.py``. Runs
independently of any single Telegram update and can live for minutes to
hours, so it opens its own short-lived DB session per write (mirroring
``bot_main._ensure_owner_seeded``'s standalone-session pattern) instead of
reusing the handler's request-scoped session, which is closed the moment
the handler returns.

Task-lifetime pitfall: an ``asyncio.Task`` with no retained reference can be
garbage-collected mid-run. ``_IN_FLIGHT_TASKS`` keeps a strong reference to
every broadcast task for as long as it runs, dropping it via
``add_done_callback`` the moment it finishes.
"""

import asyncio
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter

from app.bot.keyboards.broadcast import broadcast_progress_keyboard, format_progress_text
from app.core.constants import BROADCAST_MESSAGES_PER_SECOND
from app.core.constants import REDIS_KEY_BROADCAST_LOCK as _LOCK_KEY
from app.core.logger import get_logger
from app.database.redis_client import get_redis
from app.database.repositories.user_repository import UserRepository
from app.database.session import async_session_factory
from app.services.broadcast.broadcast_service import BroadcastService

logger = get_logger(__name__)

# Safety-net TTL for the single-in-flight lock: released explicitly on
# completion/cancellation/crash (see the `finally` block below), this only
# guards against a lock surviving a process kill that skips even `finally`.
LOCK_TTL_SECONDS = 60 * 60 * 6
PROGRESS_INTERVAL_SECONDS = 10.0
RATE_WINDOW_SECONDS = 1.0

_IN_FLIGHT_TASKS: set[asyncio.Task[None]] = set()


def schedule_broadcast(
    bot: Bot,
    broadcast_id: int,
    message_chat_id: int,
    message_id: int,
    progress_chat_id: int,
    progress_message_id: int,
    target_user_ids: list[int],
) -> asyncio.Task[None]:
    """Starts ``run_broadcast`` as a tracked background task and returns it.

    Callers (the confirm handler) don't need the returned task for
    anything themselves — retaining it here in ``_IN_FLIGHT_TASKS`` is what
    prevents the garbage-collection pitfall described in the module
    docstring; the return value only exists so callers/tests can await it
    if they want to.
    """
    task = asyncio.create_task(
        run_broadcast(
            bot=bot,
            broadcast_id=broadcast_id,
            message_chat_id=message_chat_id,
            message_id=message_id,
            progress_chat_id=progress_chat_id,
            progress_message_id=progress_message_id,
            target_user_ids=target_user_ids,
        )
    )
    _IN_FLIGHT_TASKS.add(task)
    task.add_done_callback(_IN_FLIGHT_TASKS.discard)
    return task


async def _mark_running(broadcast_id: int) -> None:
    async with async_session_factory() as session:
        await BroadcastService(session).mark_running(broadcast_id)
        await session.commit()


async def _mark_user_blocked(user_id: int) -> None:
    async with async_session_factory() as session:
        await UserRepository(session).update(user_id, is_active=False)
        await session.commit()


async def _persist_progress(broadcast_id: int, sent: int, failed: int, blocked: int) -> None:
    async with async_session_factory() as session:
        await BroadcastService(session).update_progress(broadcast_id, sent=sent, failed=failed, blocked=blocked)
        await session.commit()


async def _is_cancel_requested(broadcast_id: int) -> bool:
    async with async_session_factory() as session:
        return await BroadcastService(session).is_cancel_requested(broadcast_id)


async def _finalize(broadcast_id: int, cancelled: bool) -> None:
    async with async_session_factory() as session:
        service = BroadcastService(session)
        if cancelled:
            await service.mark_cancelled(broadcast_id)
        else:
            await service.mark_done(broadcast_id)
        await service.clear_cancel_flag(broadcast_id)
        await session.commit()


async def _edit_progress(
    bot: Bot, chat_id: int, message_id: int, broadcast_id: int, text: str, *, final: bool
) -> None:
    try:
        await bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None if final else broadcast_progress_keyboard(broadcast_id),
        )
    except TelegramAPIError as exc:
        # The admin may have deleted/navigated away from the progress
        # message, blocked the bot, or the text is unchanged (duplicate
        # edit) — none of these are worth crashing the broadcast over.
        logger.debug("broadcast_progress_edit_skipped", error=str(exc))


async def run_broadcast(
    bot: Bot,
    broadcast_id: int,
    message_chat_id: int,
    message_id: int,
    progress_chat_id: int,
    progress_message_id: int,
    target_user_ids: list[int],
) -> None:
    """Sends ``message_id`` (from ``message_chat_id``) to every id in ``target_user_ids``.

    Rate-limited to an average of ``BROADCAST_MESSAGES_PER_SECOND`` via a
    rolling 1-second window: send up to that many, then sleep out whatever
    remains of the second (never oversleep if sends themselves were slow).
    ``TelegramRetryAfter`` pauses for the server-given duration and retries
    the *same* recipient; ``TelegramForbiddenError`` (bot blocked) flips
    that user's ``is_active`` to ``False`` and counts as ``blocked``; any
    other ``TelegramAPIError`` (or unexpected exception) counts as
    ``failed`` and moves on — one bad recipient must never abort the run.
    """
    redis = get_redis()
    lock_acquired = await redis.set(_LOCK_KEY, str(broadcast_id), nx=True, ex=LOCK_TTL_SECONDS)
    if not lock_acquired:
        # Defensive only: the confirm handler already peeked the lock
        # before creating this task. Reaching here means a genuine race
        # against another in-flight broadcast — bail out without touching
        # that other broadcast's lock or DB row.
        logger.warning("broadcast_worker_lock_race", broadcast_id=broadcast_id)
        return

    total = len(target_user_ids)
    sent = 0
    failed = 0
    blocked = 0
    cancelled = False

    try:
        await _mark_running(broadcast_id)
        last_progress_at = time.monotonic()
        index = 0

        while index < total:
            window_start = time.monotonic()
            batch_sent = 0

            while index < total and batch_sent < BROADCAST_MESSAGES_PER_SECOND:
                user_id = target_user_ids[index]
                try:
                    await bot.copy_message(chat_id=user_id, from_chat_id=message_chat_id, message_id=message_id)
                    sent += 1
                    index += 1
                except TelegramRetryAfter as exc:
                    await asyncio.sleep(exc.retry_after)
                    continue  # retry the same user_id — don't advance, don't count as failed
                except TelegramForbiddenError:
                    await _mark_user_blocked(user_id)
                    blocked += 1
                    index += 1
                except TelegramAPIError as exc:
                    logger.warning(
                        "broadcast_send_failed", broadcast_id=broadcast_id, user_id=user_id, error=str(exc)
                    )
                    failed += 1
                    index += 1
                except Exception as exc:  # noqa: BLE001 - one bad recipient must never crash the broadcast
                    logger.warning(
                        "broadcast_send_unexpected_error",
                        broadcast_id=broadcast_id,
                        user_id=user_id,
                        error=str(exc),
                    )
                    failed += 1
                    index += 1
                batch_sent += 1

                now = time.monotonic()
                if now - last_progress_at >= PROGRESS_INTERVAL_SECONDS:
                    last_progress_at = now
                    await _persist_progress(broadcast_id, sent, failed, blocked)
                    await _edit_progress(
                        bot,
                        progress_chat_id,
                        progress_message_id,
                        broadcast_id,
                        format_progress_text(sent, total, failed, blocked),
                        final=False,
                    )
                    if await _is_cancel_requested(broadcast_id):
                        cancelled = True
                        break

            if cancelled:
                break

            # Only pace out the rest of the window if there's another batch
            # coming — no reason to delay finishing the broadcast by up to
            # ~1s just because the final (possibly partial) batch landed
            # early.
            if index < total:
                elapsed = time.monotonic() - window_start
                remaining = RATE_WINDOW_SECONDS - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)
    except Exception:
        # Logged here (in addition to each per-recipient except clause
        # above) only for genuinely unexpected crashes outside the send
        # loop's own error handling — re-raised after cleanup below so it
        # still surfaces in the process logs / crash reporting.
        logger.exception("broadcast_worker_crashed", broadcast_id=broadcast_id)
        raise
    finally:
        # Each cleanup step is individually guarded so a failure in one
        # (e.g. a DB hiccup persisting the final counters) can never skip
        # the next — the Redis lock release in particular is the one thing
        # that absolutely must run, since a stuck lock would block every
        # future broadcast forever. The `ex=LOCK_TTL_SECONDS` set at
        # acquire time is the last-resort safety net if even this block
        # can't run to completion (e.g. the process is killed outright).
        try:
            try:
                await _persist_progress(broadcast_id, sent, failed, blocked)
            except Exception:
                logger.exception("broadcast_finalize_persist_failed", broadcast_id=broadcast_id)

            try:
                await _finalize(broadcast_id, cancelled)
            except Exception:
                logger.exception("broadcast_finalize_status_failed", broadcast_id=broadcast_id)

            try:
                status_line = "⏹ Bekor qilindi." if cancelled else "✅ Yakunlandi."
                await _edit_progress(
                    bot,
                    progress_chat_id,
                    progress_message_id,
                    broadcast_id,
                    f"{format_progress_text(sent, total, failed, blocked)}\n\n{status_line}",
                    final=True,
                )
            except Exception:
                logger.exception("broadcast_finalize_edit_failed", broadcast_id=broadcast_id)
        finally:
            await redis.delete(_LOCK_KEY)

        logger.info(
            "broadcast_finished",
            broadcast_id=broadcast_id,
            total=total,
            sent=sent,
            failed=failed,
            blocked=blocked,
            cancelled=cancelled,
        )
