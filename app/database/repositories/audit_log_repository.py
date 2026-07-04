from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditLog
from app.database.repositories.base import BaseRepository

_TASHKENT_TZ = ZoneInfo("Asia/Tashkent")


class AuditLogRepository(BaseRepository[AuditLog]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AuditLog)

    async def search(
        self,
        *,
        admin_id: int | None,
        action: str | None,
        day: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AuditLog], int]:
        """Web panel Logs page: filter by admin/action/day, most recent first.

        ``day`` filters to that single calendar day in Asia/Tashkent (per the
        TZ's "filter: admin, action, sana" — a date picker, not a range),
        converted to the UTC range ``created_at`` is actually stored in.
        """
        filters = []
        if admin_id is not None:
            filters.append(AuditLog.admin_id == admin_id)
        if action is not None:
            filters.append(AuditLog.action == action)
        if day is not None:
            start = datetime.combine(day, time.min, tzinfo=_TASHKENT_TZ)
            end = datetime.combine(day, time.max, tzinfo=_TASHKENT_TZ)
            filters.append(AuditLog.created_at.between(start, end))

        total = await self.session.scalar(select(func.count()).select_from(AuditLog).where(*filters))

        stmt = (
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total or 0
