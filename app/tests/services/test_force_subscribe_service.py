"""Per the TZ: each of ForceSubscribeService's 5 "aktiv kanal" conditions gets its own test.

``is_channel_enforceable`` is a pure function (no DB/Redis), so these
don't need the ``session``/``client`` fixtures at all.

The tests at the bottom of this file cover ``ForceSubscribeService.check``
itself end-to-end (bypass rules + live membership check) — a gap found
while investigating a real "force-subscribe isn't blocking anyone" report
that turned out to be the premium/admin bypass working exactly as designed
for the two accounts being tested with, not a bug. Nothing here was broken,
but the integration behavior had no direct test before.
"""

from datetime import UTC, datetime, time, timedelta
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import ChatMemberLeft, ChatMemberMember
from aiogram.types import User as TgUser

from app.core.constants import REDIS_KEY_FORCE_SUB, REDIS_KEY_SETTING
from app.database.models import Channel
from app.database.redis_client import get_redis
from app.database.repositories.channel_repository import ChannelRepository
from app.services.force_subscribe.force_subscribe_service import (
    ForceSubscribeService,
    is_channel_enforceable,
)
from app.services.settings.settings_service import SettingsService

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)

# Redis isn't rolled back by the `session` fixture's SAVEPOINT the way DB
# rows are, so the 60s-TTL "fs:{user}:{channel}" membership cache from one
# run of these tests can still be warm on the next run within that window —
# a real flake this suite hit. Clean up every key these tests touch.
_TEST_USER_CHANNEL_PAIRS = [(700001, -100999001), (700002, -100999002), (700003, -100999003)]


@pytest.fixture(autouse=True)
async def _cleanup_force_sub_cache():
    yield
    redis = get_redis()
    for user_id, channel_id in _TEST_USER_CHANNEL_PAIRS:
        await redis.delete(REDIS_KEY_FORCE_SUB.format(user_id=user_id, channel_id=channel_id))
    await redis.delete(REDIS_KEY_SETTING.format(key="force_subscribe_enabled"))


def _channel(**overrides: object) -> Channel:
    defaults: dict[str, object] = {
        "id": 1,
        "channel_id": -100123,
        "title": "Test Channel",
        "is_active": True,
        "is_required": True,
        "priority": 0,
        "start_date": None,
        "expire_date": None,
        "daily_start_time": None,
        "daily_end_time": None,
        "join_limit": None,
        "current_joins": 0,
    }
    defaults.update(overrides)
    return Channel(**defaults)


def test_condition_1_is_active_false_blocks() -> None:
    assert is_channel_enforceable(_channel(is_active=False), NOW) is False


def test_condition_1_is_active_true_passes() -> None:
    assert is_channel_enforceable(_channel(is_active=True), NOW) is True


def test_condition_2_start_date_in_future_blocks() -> None:
    channel = _channel(start_date=NOW + timedelta(days=1))
    assert is_channel_enforceable(channel, NOW) is False


def test_condition_2_start_date_in_past_passes() -> None:
    channel = _channel(start_date=NOW - timedelta(days=1))
    assert is_channel_enforceable(channel, NOW) is True


def test_condition_3_expire_date_in_past_blocks() -> None:
    channel = _channel(expire_date=NOW - timedelta(days=1))
    assert is_channel_enforceable(channel, NOW) is False


def test_condition_3_expire_date_in_future_passes() -> None:
    channel = _channel(expire_date=NOW + timedelta(days=1))
    assert is_channel_enforceable(channel, NOW) is True


def test_condition_4_outside_daily_window_blocks() -> None:
    # NOW is 12:00 UTC = 17:00 Asia/Tashkent (UTC+5) — outside 08:00-16:00.
    channel = _channel(daily_start_time=time(8, 0), daily_end_time=time(16, 0))
    assert is_channel_enforceable(channel, NOW) is False


def test_condition_4_inside_daily_window_passes() -> None:
    # 17:00 Tashkent time is inside 08:00-22:00.
    channel = _channel(daily_start_time=time(8, 0), daily_end_time=time(22, 0))
    assert is_channel_enforceable(channel, NOW) is True


def test_condition_4_overnight_window_wraps_past_midnight() -> None:
    # start > end means an overnight window: "now >= start OR now < end".
    # 17:00 Tashkent falls inside 16:00-06:00 (i.e. after 16:00).
    channel = _channel(daily_start_time=time(16, 0), daily_end_time=time(6, 0))
    assert is_channel_enforceable(channel, NOW) is True


def test_condition_4_overnight_window_excludes_daytime_gap() -> None:
    # 17:00 Tashkent does NOT fall inside 22:00-06:00.
    channel = _channel(daily_start_time=time(22, 0), daily_end_time=time(6, 0))
    assert is_channel_enforceable(channel, NOW) is False


def test_condition_5_join_limit_reached_blocks() -> None:
    channel = _channel(join_limit=10, current_joins=10)
    assert is_channel_enforceable(channel, NOW) is False


def test_condition_5_join_limit_not_reached_passes() -> None:
    channel = _channel(join_limit=10, current_joins=9)
    assert is_channel_enforceable(channel, NOW) is True


def test_condition_5_join_limit_none_never_blocks() -> None:
    channel = _channel(join_limit=None, current_joins=999999)
    assert is_channel_enforceable(channel, NOW) is True


def test_all_conditions_pass_together() -> None:
    channel = _channel(
        is_active=True,
        start_date=NOW - timedelta(days=1),
        expire_date=NOW + timedelta(days=1),
        daily_start_time=time(0, 0),
        daily_end_time=time(23, 59),
        join_limit=100,
        current_joins=5,
    )
    assert is_channel_enforceable(channel, NOW) is True


# --- ForceSubscribeService.check end-to-end (bypass rules + live membership) ---


def _mock_bot(member_status_cls: type) -> AsyncMock:
    bot = AsyncMock(spec=Bot)
    bot.get_chat_member.return_value = member_status_cls(user=TgUser(id=1, is_bot=True, first_name="x"))
    return bot


async def test_check_blocks_a_plain_user_not_subscribed(session) -> None:
    await ChannelRepository(session).create(
        channel_id=-100999001, title="Required Channel", is_active=True, is_required=True, priority=0
    )
    await session.flush()

    bot = _mock_bot(ChatMemberLeft)
    blocking = await ForceSubscribeService(session, bot).check(user_id=700001)

    assert [c.channel_id for c in blocking] == [-100999001]
    bot.get_chat_member.assert_awaited_once_with(-100999001, 700001)


async def test_check_does_not_block_a_subscribed_user(session) -> None:
    await ChannelRepository(session).create(
        channel_id=-100999002, title="Required Channel 2", is_active=True, is_required=True, priority=0
    )
    await session.flush()

    bot = _mock_bot(ChatMemberMember)
    blocking = await ForceSubscribeService(session, bot).check(user_id=700002)

    assert blocking == []


async def test_check_bypassed_when_force_subscribe_disabled(session) -> None:
    await ChannelRepository(session).create(
        channel_id=-100999003, title="Required Channel 3", is_active=True, is_required=True, priority=0
    )
    await SettingsService(session).set("force_subscribe_enabled", "false")
    await session.flush()

    bot = _mock_bot(ChatMemberLeft)
    blocking = await ForceSubscribeService(session, bot).check(user_id=700003)

    assert blocking == []
    bot.get_chat_member.assert_not_awaited()
