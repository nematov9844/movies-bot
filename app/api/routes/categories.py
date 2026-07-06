"""Web panel Categories management: create/rename/toggle/delete the tags assigned
during add/edit-movie (bot's ``madd:cat:``/``mmg:cat:`` picker). Previously these
could only be *assigned* from existing rows — nothing created them.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies.auth import CurrentAdmin, require_permission
from app.api.dependencies.db import DbSession
from app.api.schemas.category import CategoryCreateRequest, CategoryResponse, CategoryUpdateRequest
from app.core.permissions import Permission
from app.database.models import Admin
from app.services.audit.audit_service import AuditService
from app.services.category.category_service import CategoryService

router = APIRouter(prefix="/api/categories", tags=["categories"])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kategoriya topilmadi")

ManageMoviesAdmin = Annotated[Admin, Depends(require_permission(Permission.MANAGE_MOVIES))]


@router.get("", response_model=list[CategoryResponse])
async def list_categories(session: DbSession, _current_admin: CurrentAdmin) -> list[CategoryResponse]:
    categories = await CategoryService(session).list_all()
    return [CategoryResponse.model_validate(c) for c in categories]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreateRequest, request: Request, session: DbSession, current_admin: ManageMoviesAdmin
) -> CategoryResponse:
    service = CategoryService(session)
    if await service.name_taken(body.name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bu nomli kategoriya allaqachon mavjud")

    category = await service.create_category(body.name)
    await AuditService(session).log(
        admin_id=current_admin.id,
        action="category_create",
        entity="category",
        entity_id=str(category.id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return CategoryResponse.model_validate(category)


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    body: CategoryUpdateRequest,
    request: Request,
    session: DbSession,
    current_admin: ManageMoviesAdmin,
) -> CategoryResponse:
    service = CategoryService(session)
    if body.name is not None and await service.name_taken(body.name, exclude_category_id=category_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bu nomli kategoriya allaqachon mavjud")

    fields = body.model_dump(exclude_unset=True)
    category = await service.update_category(category_id, **fields)
    if category is None:
        raise _NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="category_update",
        entity="category",
        entity_id=str(category_id),
        payload=fields,
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return CategoryResponse.model_validate(category)


@router.post("/{category_id}/toggle", response_model=CategoryResponse)
async def toggle_category(
    category_id: int, request: Request, session: DbSession, current_admin: ManageMoviesAdmin
) -> CategoryResponse:
    category = await CategoryService(session).toggle_active(category_id)
    if category is None:
        raise _NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="category_toggle",
        entity="category",
        entity_id=str(category_id),
        payload={"is_active": category.is_active},
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return CategoryResponse.model_validate(category)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int, request: Request, session: DbSession, current_admin: ManageMoviesAdmin
) -> None:
    deleted = await CategoryService(session).delete_category(category_id)
    if not deleted:
        raise _NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="category_delete",
        entity="category",
        entity_id=str(category_id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
