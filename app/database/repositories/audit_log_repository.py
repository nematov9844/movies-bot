from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditLog
from app.database.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AuditLog)
