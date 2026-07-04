"""Web panel Channels page: force-subscribe channel CRUD, mirroring the bot's `/panel` -> "📢 Kanallar" flow.

All mutations require ``MANAGE_CHANNELS`` (admin+, per the TZ role table).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies.auth import CurrentAdmin, require_permission
from app.api.dependencies.db import DbSession
from app.api.schemas.channel import ChannelCreateRequest, ChannelResponse, ChannelUpdateRequest
from app.core.permissions import Permission
from app.database.models import Admin
from app.services.audit.audit_service import AuditService
from app.services.channel.channel_service import ChannelService

router = APIRouter(prefix="/api/channels", tags=["channels"])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kanal topilmadi")

ManageChannelsAdmin = Annotated[Admin, Depends(require_permission(Permission.MANAGE_CHANNELS))]


@router.get("", response_model=list[ChannelResponse])
async def list_channels(session: DbSession, _current_admin: CurrentAdmin) -> list[ChannelResponse]:
    channels = await ChannelService(session).list_all()
    return [ChannelResponse.model_validate(c) for c in channels]


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: int, session: DbSession, _current_admin: CurrentAdmin) -> ChannelResponse:
    channel = await ChannelService(session).get(channel_id)
    if channel is None:
        raise _NOT_FOUND
    return ChannelResponse.model_validate(channel)


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreateRequest, request: Request, session: DbSession, current_admin: ManageChannelsAdmin
) -> ChannelResponse:
    channel = await ChannelService(session).create_channel(**body.model_dump())
    await AuditService(session).log(
        admin_id=current_admin.id,
        action="channel_create",
        entity="channel",
        entity_id=str(channel.id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return ChannelResponse.model_validate(channel)


@router.patch("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    body: ChannelUpdateRequest,
    request: Request,
    session: DbSession,
    current_admin: ManageChannelsAdmin,
) -> ChannelResponse:
    fields = body.model_dump(exclude_unset=True)
    channel = await ChannelService(session).update_channel(channel_id, **fields)
    if channel is None:
        raise _NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="channel_update",
        entity="channel",
        entity_id=str(channel_id),
        payload=fields,
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return ChannelResponse.model_validate(channel)


@router.post("/{channel_id}/toggle", response_model=ChannelResponse)
async def toggle_channel(
    channel_id: int, request: Request, session: DbSession, current_admin: ManageChannelsAdmin
) -> ChannelResponse:
    channel = await ChannelService(session).toggle_active(channel_id)
    if channel is None:
        raise _NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="channel_toggle",
        entity="channel",
        entity_id=str(channel_id),
        payload={"is_active": channel.is_active},
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return ChannelResponse.model_validate(channel)


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: int, request: Request, session: DbSession, current_admin: ManageChannelsAdmin
) -> None:
    deleted = await ChannelService(session).delete_channel(channel_id)
    if not deleted:
        raise _NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="channel_delete",
        entity="channel",
        entity_id=str(channel_id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
