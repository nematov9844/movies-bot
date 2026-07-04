"""Business logic for the premium subscription system.

Composes ``PremiumUserRepository``/``PremiumPlanRepository`` behind one
service. Per the TZ, ``is_premium`` is meant to become the *only* place
premium status is checked anywhere in the codebase — ``MovieService.
check_access`` and ``ForceSubscribeService.check`` are both refactored in
this same phase to call it instead of querying ``PremiumUserRepository``
directly. A Redis cache-aside layer (``REDIS_KEY_PREMIUM``, 5 minutes) sits
in front of it since it's now on the hot path of every premium-gated movie
delivery and every force-subscribe check.

Deliberately has no ``Bot`` dependency: this stays pure DB/Redis business
logic, testable without Telegram I/O. Phase 11's scheduler is expected to
compose this service together with a ``Bot`` to actually send the
notifications that ``find_expiring_within``/``deactivate_expired`` make
possible — this phase only provides those two as the extension point.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import REDIS_KEY_PREMIUM
from app.database.models import PremiumPlan, PremiumUser
from app.database.redis_client import get_redis
from app.database.repositories.premium_plan_repository import PremiumPlanRepository
from app.database.repositories.premium_user_repository import PremiumUserRepository

PREMIUM_CACHE_TTL_SECONDS = 300


class PremiumService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._user_repo = PremiumUserRepository(session)
        self._plan_repo = PremiumPlanRepository(session)

    async def is_premium(self, user_id: int) -> bool:
        """Whether ``user_id`` currently has active premium, Redis-cached for 5 minutes.

        Cache-aside: on a miss, reads the DB and stores the boolean result
        as ``"1"``/``"0"``. ``grant`` and ``deactivate_expired`` invalidate
        the key on write, so a just-granted (or just-expired) status is
        never stuck stale for the full TTL.
        """
        redis = get_redis()
        key = REDIS_KEY_PREMIUM.format(user_id=user_id)

        cached = await redis.get(key)
        if cached is not None:
            return cached == "1"

        active = await self._user_repo.get_active_for_user(user_id)
        result = active is not None
        await redis.set(key, "1" if result else "0", ex=PREMIUM_CACHE_TTL_SECONDS)
        return result

    async def get_active(self, user_id: int) -> PremiumUser | None:
        """The user's active ``PremiumUser`` row (with its real expiry), or ``None``.

        Unlike ``is_premium`` this is not cached — for callers (the Profil
        screen, the admin grant-confirmation card) that need the actual row
        rather than a boolean.
        """
        return await self._user_repo.get_active_for_user(user_id)

    async def list_active_plans(self) -> list[PremiumPlan]:
        return await self._plan_repo.get_many(is_active=True)

    async def list_all_plans(self) -> list[PremiumPlan]:
        """Every plan, active or not — the web panel's plan-management table."""
        return await self._plan_repo.get_many()

    async def get_plan(self, plan_id: int) -> PremiumPlan | None:
        return await self._plan_repo.get(plan_id)

    async def create_plan(self, *, name: str, days: int, price: int) -> PremiumPlan:
        return await self._plan_repo.create(name=name, days=days, price=price, is_active=True)

    async def update_plan(
        self,
        plan_id: int,
        *,
        name: str | None = None,
        days: int | None = None,
        price: int | None = None,
        is_active: bool | None = None,
    ) -> PremiumPlan | None:
        fields = {
            k: v
            for k, v in {"name": name, "days": days, "price": price, "is_active": is_active}.items()
            if v is not None
        }
        if not fields:
            return await self._plan_repo.get(plan_id)
        return await self._plan_repo.update(plan_id, **fields)

    async def deactivate_plan(self, plan_id: int) -> PremiumPlan | None:
        """Soft-delete: existing grants FK to ``plan_id``, so a plan is turned off, never hard-deleted."""
        return await self._plan_repo.update(plan_id, is_active=False)

    async def list_active_subscriptions(self, limit: int, offset: int) -> tuple[list[PremiumUser], int]:
        """Active subscriptions for the web panel's Premium page, with ``user``/``plan`` eager-loaded."""
        return await self._user_repo.list_active(limit, offset)

    async def _invalidate_cache(self, user_id: int) -> None:
        await get_redis().delete(REDIS_KEY_PREMIUM.format(user_id=user_id))

    async def grant(
        self,
        user_id: int,
        plan_id: int,
        granted_by: int | None,
        payment_method: str | None = None,
    ) -> PremiumUser:
        """Grant ``plan_id`` to ``user_id``, extending any existing active row rather than stacking.

        If the user already has an active ``PremiumUser`` row, its
        ``expires_at`` is pushed out by the new plan's ``days`` (not reset
        to ``now + days``), and its ``plan_id``/``payment_method``/
        ``granted_by`` are updated to reflect this latest grant — so a user
        10 days into a 30-day plan who buys another 30-day plan ends up
        with 50 days left, never a second overlapping active row. Otherwise
        a fresh row is created, starting now.

        Either way, the ``is_premium`` cache entry for ``user_id`` is
        invalidated immediately after the write, so the grant takes effect
        right away instead of waiting out the 5-minute TTL.
        """
        plan = await self._plan_repo.get(plan_id)
        if plan is None:
            raise ValueError(f"Unknown premium plan_id={plan_id}")

        existing = await self._user_repo.get_active_for_user(user_id)
        if existing is not None:
            existing.expires_at = existing.expires_at + timedelta(days=plan.days)
            existing.plan_id = plan_id
            if payment_method is not None:
                existing.payment_method = payment_method
            if granted_by is not None:
                existing.granted_by = granted_by
            await self._session.flush()
            premium_user = existing
        else:
            now = datetime.now(UTC)
            premium_user = await self._user_repo.create(
                user_id=user_id,
                plan_id=plan_id,
                starts_at=now,
                expires_at=now + timedelta(days=plan.days),
                is_active=True,
                payment_method=payment_method,
                granted_by=granted_by,
            )

        await self._invalidate_cache(user_id)
        return premium_user

    async def find_expiring_within(self, hours: int) -> list[PremiumUser]:
        """Active rows whose ``expires_at`` is between now and ``now + hours``.

        Extension point for the future 24h-warning scheduler job (Phase 11)
        — this phase only needs the query to exist and be correct.
        """
        now = datetime.now(UTC)
        return await self._user_repo.find_expiring(now, now + timedelta(hours=hours))

    async def deactivate_expired(self) -> list[PremiumUser]:
        """Deactivate every active row whose ``expires_at`` has passed, returning those rows.

        Sets ``is_active=False`` on each and invalidates its Redis cache
        entry, committing the change (via flush) within this call. The
        returned rows are what a future scheduler job (Phase 11) would
        notify about expiry.
        """
        now = datetime.now(UTC)
        expired = await self._user_repo.find_expired(now)
        for premium_user in expired:
            premium_user.is_active = False
        await self._session.flush()

        for premium_user in expired:
            await self._invalidate_cache(premium_user.user_id)

        return expired
