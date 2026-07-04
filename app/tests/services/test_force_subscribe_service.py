"""Per the TZ: each of ForceSubscribeService's 5 "aktiv kanal" conditions gets its own test.

``is_channel_enforceable`` is a pure function (no DB/Redis), so these
don't need the ``session``/``client`` fixtures at all.
"""

from datetime import UTC, datetime, time, timedelta

from app.database.models import Channel
from app.services.force_subscribe.force_subscribe_service import is_channel_enforceable

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


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
