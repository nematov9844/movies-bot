from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.audit_log_repository import AuditLogRepository


class AuditService:
    """Thin write-only wrapper over ``AuditLogRepository`` for admin-action logging.

    Phase 4 only calls this for web-panel login/login-failure and the bot's
    ``/setpassword`` command. Later phases (movies, channels, broadcast,
    premium, settings, admins CRUD) call the same ``log`` method for their
    own admin actions rather than writing to ``audit_logs`` directly.
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
