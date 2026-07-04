"""Web panel Settings page: list every runtime setting, edit one by key.

Goes through the same ``SettingsService`` (Phase 12's cache-aside +
invalidate-on-write) the bot's `/panel` -> "⚙️ Sozlamalar" screen uses, so a
change from either side is immediately visible to the other.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies.auth import CurrentAdmin, require_permission
from app.api.dependencies.db import DbSession
from app.api.schemas.settings import SettingResponse, SettingUpdateRequest
from app.core.permissions import Permission
from app.database.models import Admin
from app.services.audit.audit_service import AuditService
from app.services.settings.settings_service import SettingsService

router = APIRouter(prefix="/api/settings", tags=["settings"])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sozlama topilmadi")

ManageSettingsAdmin = Annotated[Admin, Depends(require_permission(Permission.MANAGE_SETTINGS))]


@router.get("", response_model=list[SettingResponse])
async def list_settings(session: DbSession, _current_admin: CurrentAdmin) -> list[SettingResponse]:
    settings = await SettingsService(session).list_all()
    return [SettingResponse.model_validate(s) for s in settings]


@router.patch("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    body: SettingUpdateRequest,
    request: Request,
    session: DbSession,
    current_admin: ManageSettingsAdmin,
) -> SettingResponse:
    service = SettingsService(session)
    existing = await service.get_setting(key)
    if existing is None:
        raise _NOT_FOUND

    await service.set(key, body.value)
    await AuditService(session).log(
        admin_id=current_admin.id,
        action="setting_update",
        entity="setting",
        entity_id=key,
        payload={"value": body.value},
        ip=request.client.host if request.client else None,
    )
    await session.commit()

    updated = await service.get_setting(key)
    if updated is None:
        raise _NOT_FOUND
    return SettingResponse.model_validate(updated)
