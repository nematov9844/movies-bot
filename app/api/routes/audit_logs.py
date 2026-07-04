"""Web panel Logs page: ``audit_logs`` table, filterable by admin/action/day."""

from datetime import date

from fastapi import APIRouter

from app.api.dependencies.auth import CurrentAdmin
from app.api.dependencies.db import DbSession
from app.api.dependencies.pagination import Pagination
from app.api.schemas.audit_log import AuditLogResponse
from app.api.schemas.common import Page
from app.services.audit.audit_service import AuditService

router = APIRouter(prefix="/api/audit-logs", tags=["audit-logs"])


@router.get("", response_model=Page[AuditLogResponse])
async def list_audit_logs(
    session: DbSession,
    _current_admin: CurrentAdmin,
    pagination: Pagination,
    admin_id: int | None = None,
    action: str | None = None,
    day: date | None = None,
) -> Page[AuditLogResponse]:
    logs, total = await AuditService(session).search(
        admin_id=admin_id, action=action, day=day, limit=pagination.limit, offset=pagination.offset
    )
    return Page(
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )
