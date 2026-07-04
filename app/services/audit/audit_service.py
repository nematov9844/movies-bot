from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditLog
from app.database.repositories.audit_log_repository import AuditLogRepository


class AuditService:
    """Wrapper over ``AuditLogRepository`` for admin-action logging (write) and the Logs page (read).

    Phase 4 only needed ``log`` — web-panel login/login-failure and the
    bot's ``/setpassword`` command. Every later mutating admin action
    (movies, channels, broadcast, premium, settings, admins CRUD) calls the
    same method rather than writing to ``audit_logs`` directly. Phase 13
    adds ``search`` for the web panel's Logs page on top of the same class.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = AuditLogRepository(session)

    async def log(
        self,
        admin_id: int | None,
        action: str,
        entity: str,
        entity_id: str | None,
        payload: dict[str, Any] | None = None,
        ip: str | None = None,
    ) -> None:
        await self._repo.create(
            admin_id=admin_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            payload=payload,
            ip=ip,
        )

    async def search(
        self,
        *,
        admin_id: int | None,
        action: str | None,
        day: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AuditLog], int]:
        return await self._repo.search(admin_id=admin_id, action=action, day=day, limit=limit, offset=offset)
