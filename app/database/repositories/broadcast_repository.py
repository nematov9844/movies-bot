from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Broadcast
from app.database.repositories.base import BaseRepository


class BroadcastRepository(BaseRepository[Broadcast]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Broadcast)

    async def list_recent(self, limit: int, offset: int) -> tuple[list[Broadcast], int]:
        """Broadcast history for the web panel, most recently created first."""
        total = await self.session.scalar(select(func.count()).select_from(Broadcast))

        stmt = select(Broadcast).order_by(Broadcast.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total or 0
