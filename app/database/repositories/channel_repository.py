from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Channel
from app.database.repositories.base import BaseRepository


class ChannelRepository(BaseRepository[Channel]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Channel)

    async def get_by_channel_id(self, channel_id: int) -> Channel | None:
        stmt = select(Channel).where(Channel.channel_id == channel_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Channel]:
        stmt = select(Channel).where(Channel.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
