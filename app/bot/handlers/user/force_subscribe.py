"""The "✅ Tekshirish" callback: re-checks force-subscribe status and, once
clear, replays whatever update was originally blocked.

Deliberately *not* ``content_gate``-flagged — this handler must always be
reachable regardless of the user's subscription state, otherwise a blocked
user would have no way to ever retry.
"""

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, Update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.channel import force_subscribe_keyboard
from app.bot.middlewares.force_subscribe import FORCE_SUBSCRIBE_TEXT
from app.core.constants import REDIS_KEY_PENDING_UPDATE, REDIS_KEY_THROTTLE
from app.core.logger import get_logger
from app.database.redis_client import get_redis
from app.services.force_subscribe.force_subscribe_service import ForceSubscribeService

router = Router(name="user_force_subscribe")
logger = get_logger(__name__)

VERIFIED_ALERT_TEXT = "✅ Obuna tasdiqlandi!"
PENDING_EXPIRED_TEXT = "✅ Obuna tasdiqlandi. Endi so'rovingizni qayta yuboring."


async def _safe_edit_text(message: Message, text: str, **kwargs: object) -> None:
    """``edit_text`` that swallows "message to edit not found".

    A duplicate/overlapping "✅ Tekshirish" tap can reach this handler after
    an earlier tap already deleted the same block message (successful
    verify+replay) — nothing meaningful is left to show at that point, so
    this is a no-op rather than an unhandled error.
    """
    try:
        await message.edit_text(text, **kwargs)  # type: ignore[arg-type]
    except TelegramBadRequest as exc:
        logger.debug("force_subscribe_verify_edit_skipped", error=str(exc))


@router.callback_query(F.data == "fs:verify")
async def verify_subscription(
    callback: CallbackQuery, session: AsyncSession, bot: Bot, dispatcher: Dispatcher
) -> None:
    user = callback.from_user
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    service = ForceSubscribeService(session, bot)

    # Invalidate the 60s membership cache for every currently-enforceable
    # required channel *before* re-checking, so a just-completed join is
    # picked up immediately instead of possibly up to 60s stale.
    candidates = await service.get_enforceable_channels()
    await service.clear_membership_cache(user.id, candidates)

    blocking = await service.check(user.id)
    if blocking:
        # Still missing some — re-render the same block screen in place
        # (edit, don't spam a new message) with the current state. No
        # scolding copy; the user just needs to see what's left.
        await _safe_edit_text(callback.message, FORCE_SUBSCRIBE_TEXT, reply_markup=force_subscribe_keyboard(blocking))
        await callback.answer()
        return

    # check() came back empty, which means the user is now confirmed
    # subscribed to every currently-enforceable required channel — safe to
    # credit all of them. mark_joined is idempotent (Redis SADD-backed), so
    # channels the user was already credited for in a previous verify tap
    # are silently skipped rather than double-counted.
    for channel in candidates:
        await service.mark_joined(user.id, channel.channel_id)

    await callback.answer(VERIFIED_ALERT_TEXT)

    redis = get_redis()
    pending_key = REDIS_KEY_PENDING_UPDATE.format(user_id=user.id)
    raw_update = await redis.get(pending_key)
    if raw_update is None:
        await _safe_edit_text(callback.message, PENDING_EXPIRED_TEXT)
        return

    await redis.delete(pending_key)
    stored_update = Update.model_validate_json(raw_update)
    try:
        await callback.message.delete()
    except TelegramBadRequest as exc:
        logger.debug("force_subscribe_verify_delete_skipped", error=str(exc))

    # feed_update() re-runs the *full* outer middleware chain, including
    # ThrottlingMiddleware — which the "✅ Tekshirish" tap itself just
    # consumed the 1-second slot for. Without clearing it here, the replay
    # would be silently dropped as a throttled duplicate a moment after
    # being unblocked.
    await redis.delete(REDIS_KEY_THROTTLE.format(user_id=user.id))

    # Commit and release this handler's own transaction *before* triggering
    # the replay. DbSessionMiddleware won't commit `session` until this
    # handler returns, but feed_update() below opens a brand-new session for
    # the replayed update whose own UserUpsertMiddleware needs to write the
    # same `users` row this transaction already touched (upserting the same
    # acting user) — without an early commit here, that write blocks on a
    # lock this transaction is still holding, and this transaction never
    # proceeds to commit because it's awaiting the replay: a guaranteed
    # self-deadlock. Committing early releases the lock so the replay's
    # session can proceed normally; DbSessionMiddleware's own commit after
    # this handler returns is then a no-op on an empty transaction.
    await session.commit()

    logger.info("force_subscribe_replay", user_id=user.id, update_id=stored_update.update_id)
    await dispatcher.feed_update(bot=bot, update=stored_update)
