from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import REDIS_KEY_PREMIUM
from app.database.redis_client import get_redis
from app.database.repositories.premium_plan_repository import PremiumPlanRepository
from app.database.repositories.premium_user_repository import PremiumUserRepository
from app.database.repositories.user_repository import UserRepository
from app.services.premium.premium_service import PremiumService

_TEST_USER_ID = 900001
_TEST_USER_ID_2 = 900002


@pytest.fixture(autouse=True)
async def _cleanup_premium_cache():
    yield
    redis = get_redis()
    for user_id in (_TEST_USER_ID, _TEST_USER_ID_2):
        await redis.delete(REDIS_KEY_PREMIUM.format(user_id=user_id))


async def _make_plan(session: AsyncSession, days: int = 30):
    return await PremiumPlanRepository(session).create(name="Test Plan", days=days, price=10000)


async def test_is_premium_false_without_subscription(session: AsyncSession) -> None:
    await UserRepository(session).create(id=_TEST_USER_ID)
    service = PremiumService(session)

    assert await service.is_premium(_TEST_USER_ID) is False


async def test_is_premium_true_after_grant(session: AsyncSession) -> None:
    await UserRepository(session).create(id=_TEST_USER_ID)
    plan = await _make_plan(session)
    service = PremiumService(session)

    await service.grant(user_id=_TEST_USER_ID, plan_id=plan.id, granted_by=None)

    assert await service.is_premium(_TEST_USER_ID) is True


async def test_is_premium_cache_is_actually_used(session: AsyncSession) -> None:
    """Directly flipping the DB row (bypassing the service) must not change a cached result."""
    await UserRepository(session).create(id=_TEST_USER_ID)
    plan = await _make_plan(session)
    service = PremiumService(session)
    premium_user = await service.grant(user_id=_TEST_USER_ID, plan_id=plan.id, granted_by=None)
    await session.commit()

    assert await service.is_premium(_TEST_USER_ID) is True  # populates the cache

    # Bypass the service (no cache invalidation) and deactivate directly.
    await PremiumUserRepository(session).update(premium_user.id, is_active=False)
    await session.commit()

    assert await service.is_premium(_TEST_USER_ID) is True  # still cached


async def test_grant_creates_new_active_row(session: AsyncSession) -> None:
    await UserRepository(session).create(id=_TEST_USER_ID_2)
    plan = await _make_plan(session, days=30)
    service = PremiumService(session)

    premium_user = await service.grant(user_id=_TEST_USER_ID_2, plan_id=plan.id, granted_by=None)

    assert premium_user.is_active is True
    assert premium_user.plan_id == plan.id


async def test_grant_extends_existing_subscription_instead_of_stacking(session: AsyncSession) -> None:
    await UserRepository(session).create(id=_TEST_USER_ID_2)
    plan = await _make_plan(session, days=30)
    service = PremiumService(session)

    first = await service.grant(user_id=_TEST_USER_ID_2, plan_id=plan.id, granted_by=None)
    first_expiry = first.expires_at

    second = await service.grant(user_id=_TEST_USER_ID_2, plan_id=plan.id, granted_by=None)

    # Same row extended, not a second overlapping one.
    assert second.id == first.id
    assert second.expires_at == first_expiry + timedelta(days=30)

    rows = await PremiumUserRepository(session).get_many(user_id=_TEST_USER_ID_2)
    assert len(rows) == 1


async def test_get_active_returns_none_when_expired(session: AsyncSession) -> None:
    await UserRepository(session).create(id=_TEST_USER_ID)
    plan = await _make_plan(session, days=30)
    repo = PremiumUserRepository(session)
    now = datetime.now(UTC)
    await repo.create(
        user_id=_TEST_USER_ID,
        plan_id=plan.id,
        starts_at=now - timedelta(days=40),
        expires_at=now - timedelta(days=10),
        is_active=True,
    )

    service = PremiumService(session)
    assert await service.get_active(_TEST_USER_ID) is None
