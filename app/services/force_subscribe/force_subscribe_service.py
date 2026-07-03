"""Business logic for the "majburiy obuna" (force-subscribe) gate.

``ForceSubscribeService.check`` is what ``ForceSubscribeMiddleware``
(``app/bot/middlewares/force_subscribe.py``) calls in front of every
``content_gate``-flagged handler. Bypass rules (settings toggle, premium,
admin) are checked first and short-circuit before any Telegram API call is
made; the remaining "is this channel enforceable right now" logic is kept as
a standalone pure function (``is_channel_enforceable``) so it can be
exercised directly in tests without a database or Redis, per the TZ's call
for individual coverage of each of its 5 conditions.
"""

from collections.abc import Iterable
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    FORCE_SUB_CACHE_TTL_SECONDS,
    REDIS_KEY_CHANNEL_JOINED,
    REDIS_KEY_FORCE_SUB,
)
from app.core.logger import get_logger
from app.database.models import Channel
from app.database.redis_client import get_redis
from app.database.repositories.channel_repository import ChannelRepository
from app.services.admin.admin_service import AdminService
from app.services.premium.premium_service import PremiumService
from app.services.settings.settings_service import SettingsService

logger = get_logger(__name__)

_TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

# Membership statuses that count as "still in the channel" for force-sub
# purposes. ``restricted`` is included per Telegram's semantics: the user is
# still a chat member with some permissions removed, not someone who left.
_SUBSCRIBED_STATUSES = frozenset(
    {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.RESTRICTED,
    }
)


def _within_daily_window(start: time | None, end: time | None, now_utc: datetime) -> bool:
    """Condition 4: no configured window, or the Tashkent wall-clock time is inside it.

    ``start > end`` is an overnight window wrapping past midnight (e.g.
    22:00-06:00 means "now >= 22:00 OR now < 06:00"), not simply always-false.
    """
    if start is None or end is None:
        return True

    local_now = now_utc.astimezone(_TASHKENT_TZ).time()
    if start <= end:
        return start <= local_now < end
    return local_now >= start or local_now < end


def is_channel_enforceable(channel: Channel, now_utc: datetime) -> bool:
    """Pure 5-condition check for whether ``channel`` is "aktiv" (enforceable) right now.

    Each condition is a separate, individually-readable early return so it
    can be unit-tested independently (TZ Phase 17 note):

    1. ``is_active`` is true.
    2. ``start_date`` is NULL or already in the past.
    3. ``expire_date`` is NULL or still in the future.
    4. the current Tashkent time falls inside the daily window (or none is set).
    5. ``join_limit`` is NULL or hasn't been reached yet.
    """
    if not channel.is_active:
        return False
    if channel.start_date is not None and now_utc < channel.start_date:
        return False
    if channel.expire_date is not None and now_utc >= channel.expire_date:
        return False
    if not _within_daily_window(channel.daily_start_time, channel.daily_end_time, now_utc):
        return False
    return channel.join_limit is None or channel.current_joins < channel.join_limit


class ForceSubscribeService:
    """Decides which required channels (if any) are currently blocking a user."""

    def __init__(self, session: AsyncSession, bot: Bot) -> None:
        self._session = session
        self._bot = bot
        self._channel_repo = ChannelRepository(session)
        self._premium_service = PremiumService(session)
        self._admin_service = AdminService(session)
        self._settings_service = SettingsService(session)

    async def check(self, user_id: int) -> list[Channel]:
        """Active, required channels ``user_id`` is not yet subscribed to, priority ascending.

        Empty list means nothing is blocking them — either a bypass rule
        applied, no required channel is currently enforceable, or they're
        already subscribed to all of them.
        """
        if not await self._settings_service.get_bool("force_subscribe_enabled", default=True):
            return []
        if await self._premium_service.is_premium(user_id):
            return []
        if await self._admin_service.is_admin(user_id):
            return []

        blocking: list[Channel] = []
        for channel in await self.get_enforceable_channels():
            subscribed = await self._is_member(user_id, channel)
            if subscribed is False:
                blocking.append(channel)
        return blocking

    async def get_enforceable_channels(self) -> list[Channel]:
        """Required channels that are "aktiv" right now, ordered by priority ascending.

        User-independent, so it's reused by the ``fs:verify`` handler to know
        exactly which channels' 60s membership cache to invalidate before
        re-running ``check`` (see ``app/bot/handlers/user/force_subscribe.py``).
        """
        channels = await self._channel_repo.get_many(is_required=True)
        now_utc = datetime.now(UTC)
        active = [channel for channel in channels if is_channel_enforceable(channel, now_utc)]
        active.sort(key=lambda channel: channel.priority)
        return active

    async def _is_member(self, user_id: int, channel: Channel) -> bool | None:
        """Whether ``user_id`` is a member of ``channel`` right now.

        Returns ``None`` (rather than raising) if the live Telegram check
        itself fails — typically because the bot isn't actually an admin in
        a misconfigured channel — so the caller can skip that channel
        instead of breaking force-sub for every other channel/user.
        """
        redis = get_redis()
        cache_key = REDIS_KEY_FORCE_SUB.format(user_id=user_id, channel_id=channel.channel_id)

        cached = await redis.get(cache_key)
        if cached is not None:
            return cached == "1"

        try:
            member = await self._bot.get_chat_member(channel.channel_id, user_id)
        except TelegramAPIError as exc:
            logger.warning(
                "force_sub_member_check_failed",
                channel_id=channel.channel_id,
                user_id=user_id,
                error=str(exc),
            )
            return None

        subscribed = member.status in _SUBSCRIBED_STATUSES
        await redis.set(cache_key, "1" if subscribed else "0", ex=FORCE_SUB_CACHE_TTL_SECONDS)
        return subscribed

    async def clear_membership_cache(self, user_id: int, channels: Iterable[Channel]) -> None:
        """Invalidate the 60s cached membership result for ``user_id`` across ``channels``.

        Called by the verify handler before re-running ``check`` so a
        just-completed join is picked up immediately instead of possibly up
        to 60s stale.
        """
        keys = [REDIS_KEY_FORCE_SUB.format(user_id=user_id, channel_id=channel.channel_id) for channel in channels]
        if keys:
            await get_redis().delete(*keys)

    async def mark_joined(self, user_id: int, channel_id: int) -> None:
        """Idempotently credit ``user_id`` toward ``channel_id``'s ``current_joins``.

        Uses a Redis set (``REDIS_KEY_CHANNEL_JOINED``) as the source of
        truth for "has this user already been counted for this channel" —
        ``SADD`` only reports the member as newly added once, so
        ``current_joins`` increments exactly once per user no matter how
        many times the verify flow re-triggers for them.
        """
        redis = get_redis()
        added = await redis.sadd(REDIS_KEY_CHANNEL_JOINED.format(channel_id=channel_id), user_id)
        if not added:
            return

        channel = await self._channel_repo.get_by_channel_id(channel_id)
        if channel is not None:
            channel.current_joins += 1
            await self._session.flush()
