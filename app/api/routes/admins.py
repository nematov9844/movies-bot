"""Web panel Admins page: owner-only, per the TZ role table ("Admin qo'shish/o'chirish: faqat owner")."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies.auth import require_permission
from app.api.dependencies.db import DbSession
from app.api.schemas.admin import AdminCreateRequest, AdminResponse
from app.core.constants import AdminRole
from app.core.permissions import Permission
from app.database.models import Admin
from app.services.admin.admin_service import AdminService
from app.services.audit.audit_service import AuditService

router = APIRouter(prefix="/api/admins", tags=["admins"])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin topilmadi")

ManageAdminsAdmin = Annotated[Admin, Depends(require_permission(Permission.MANAGE_ADMINS))]


@router.get("", response_model=list[AdminResponse])
async def list_admins(session: DbSession, _current_admin: ManageAdminsAdmin) -> list[AdminResponse]:
    admins = await AdminService(session).list_all()
    return [AdminResponse.model_validate(a) for a in admins]


@router.post("", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
async def create_admin(
    body: AdminCreateRequest, request: Request, session: DbSession, current_admin: ManageAdminsAdmin
) -> AdminResponse:
    admin = await AdminService(session).create(body.user_id, body.role, body.password)
    await AuditService(session).log(
        admin_id=current_admin.id,
        action="admin_create",
        entity="admin",
        entity_id=str(admin.id),
        payload={"role": body.role.value},
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return AdminResponse.model_validate(admin)


@router.delete("/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin(
    admin_id: int, request: Request, session: DbSession, current_admin: ManageAdminsAdmin
) -> None:
    service = AdminService(session)
    target = await service.get(admin_id)
    if target is None:
        raise _NOT_FOUND
    if target.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="O'zingizni o'chira olmaysiz"
        )
    if AdminRole(target.role) == AdminRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Owner'ni o'chirib bo'lmaydi"
        )

    await service.delete(admin_id)
    await AuditService(session).log(
        admin_id=current_admin.id,
        action="admin_delete",
        entity="admin",
        entity_id=str(admin_id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
