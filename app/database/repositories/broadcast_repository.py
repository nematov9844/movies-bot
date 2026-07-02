from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Broadcast
from app.database.repositories.base import BaseRepository


class BroadcastRepository(BaseRepository[Broadcast]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Broadcast)
