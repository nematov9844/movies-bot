from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PremiumUser
from app.database.repositories.base import BaseRepository


class PremiumUserRepository(BaseRepository[PremiumUser]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PremiumUser)

    async def get_active_for_user(self, user_id: int) -> PremiumUser | None:
        stmt = (
            select(PremiumUser)
            .where(
                PremiumUser.user_id == user_id,
                PremiumUser.is_active.is_(True),
                PremiumUser.expires_at > datetime.now(UTC),
            )
            .order_by(PremiumUser.expires_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def find_expiring(self, now: datetime, until: datetime) -> list[PremiumUser]:
        """Active rows whose ``expires_at`` falls in ``(now, until]`` — the 24h-warning scheduler's source query."""
        stmt = select(PremiumUser).where(
            PremiumUser.is_active.is_(True),
            PremiumUser.expires_at > now,
            PremiumUser.expires_at <= until,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_expired(self, now: datetime) -> list[PremiumUser]:
        """Active rows whose ``expires_at`` has already passed — ``PremiumService.deactivate_expired``'s source query."""
        stmt = select(PremiumUser).where(
            PremiumUser.is_active.is_(True),
            PremiumUser.expires_at <= now,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
