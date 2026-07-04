"""Web panel Broadcast page: history + a stop button.

Per the TZ, composing a new broadcast stays bot-only (the message being
broadcast is authored by forwarding/sending it to the bot) — this router
only exposes the history list and ``POST /{id}/cancel``, which sets the
same Redis cancel flag ``broadcast_worker.run_broadcast`` already polls.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies.auth import CurrentAdmin, require_permission
from app.api.dependencies.db import DbSession
from app.api.dependencies.pagination import Pagination
from app.api.schemas.broadcast import BroadcastResponse
from app.api.schemas.common import Page
from app.core.constants import BroadcastStatus
from app.core.permissions import Permission
from app.database.models import Admin
from app.services.audit.audit_service import AuditService
from app.services.broadcast.broadcast_service import BroadcastService

router = APIRouter(prefix="/api/broadcasts", tags=["broadcasts"])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broadcast topilmadi")

BroadcastAdmin = Annotated[Admin, Depends(require_permission(Permission.BROADCAST))]


@router.get("", response_model=Page[BroadcastResponse])
async def list_broadcasts(
    session: DbSession, _current_admin: CurrentAdmin, pagination: Pagination
) -> Page[BroadcastResponse]:
    broadcasts, total = await BroadcastService(session).list_recent(pagination.limit, pagination.offset)
    return Page(
        items=[BroadcastResponse.model_validate(b) for b in broadcasts],
        total=total,
        page=pagination.page,
        size=pagination.size,
    )


@router.post("/{broadcast_id}/cancel", response_model=BroadcastResponse)
async def cancel_broadcast(
    broadcast_id: int, request: Request, session: DbSession, current_admin: BroadcastAdmin
) -> BroadcastResponse:
    service = BroadcastService(session)
    broadcast = await service.get(broadcast_id)
    if broadcast is None:
        raise _NOT_FOUND
    if broadcast.status != BroadcastStatus.RUNNING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Faqat ishlayotgan broadcast to'xtatiladi"
        )

    await service.request_cancel(broadcast_id)
    await AuditService(session).log(
        admin_id=current_admin.id,
        action="broadcast_cancel",
        entity="broadcast",
        entity_id=str(broadcast_id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return BroadcastResponse.model_validate(broadcast)
