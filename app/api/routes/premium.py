"""Web panel Premium page: plan CRUD + active-subscriptions list + manual grant.

Plan mutations and manual grants require ``GRANT_PREMIUM`` (admin+, per the
TZ role table) — the same permission the bot's premium-grant wizard gates
behind.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.dependencies.auth import CurrentAdmin, require_permission
from app.api.dependencies.db import DbSession
from app.api.dependencies.pagination import Pagination
from app.api.schemas.common import Page
from app.api.schemas.premium import (
    PremiumGrantRequest,
    PremiumPlanCreateRequest,
    PremiumPlanResponse,
    PremiumPlanUpdateRequest,
    PremiumUserResponse,
)
from app.core.permissions import Permission
from app.database.models import Admin
from app.services.audit.audit_service import AuditService
from app.services.premium.premium_service import PremiumService
from app.services.user.user_service import UserService

router = APIRouter(prefix="/api/premium", tags=["premium"])

_PLAN_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarif topilmadi")

GrantPremiumAdmin = Annotated[Admin, Depends(require_permission(Permission.GRANT_PREMIUM))]


@router.get("/plans", response_model=list[PremiumPlanResponse])
async def list_plans(session: DbSession, _current_admin: CurrentAdmin) -> list[PremiumPlanResponse]:
    plans = await PremiumService(session).list_all_plans()
    return [PremiumPlanResponse.model_validate(p) for p in plans]


@router.post("/plans", response_model=PremiumPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    body: PremiumPlanCreateRequest, request: Request, session: DbSession, current_admin: GrantPremiumAdmin
) -> PremiumPlanResponse:
    plan = await PremiumService(session).create_plan(name=body.name, days=body.days, price=body.price)
    await AuditService(session).log(
        admin_id=current_admin.id,
        action="premium_plan_create",
        entity="premium_plan",
        entity_id=str(plan.id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return PremiumPlanResponse.model_validate(plan)


@router.patch("/plans/{plan_id}", response_model=PremiumPlanResponse)
async def update_plan(
    plan_id: int,
    body: PremiumPlanUpdateRequest,
    request: Request,
    session: DbSession,
    current_admin: GrantPremiumAdmin,
) -> PremiumPlanResponse:
    fields = body.model_dump(exclude_unset=True)
    plan = await PremiumService(session).update_plan(plan_id, **fields)
    if plan is None:
        raise _PLAN_NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="premium_plan_update",
        entity="premium_plan",
        entity_id=str(plan_id),
        payload=fields,
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return PremiumPlanResponse.model_validate(plan)


@router.delete("/plans/{plan_id}", response_model=PremiumPlanResponse)
async def deactivate_plan(
    plan_id: int, request: Request, session: DbSession, current_admin: GrantPremiumAdmin
) -> PremiumPlanResponse:
    plan = await PremiumService(session).deactivate_plan(plan_id)
    if plan is None:
        raise _PLAN_NOT_FOUND

    await AuditService(session).log(
        admin_id=current_admin.id,
        action="premium_plan_deactivate",
        entity="premium_plan",
        entity_id=str(plan_id),
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    return PremiumPlanResponse.model_validate(plan)


@router.get("/subscriptions", response_model=Page[PremiumUserResponse])
async def list_subscriptions(
    session: DbSession, _current_admin: CurrentAdmin, pagination: Pagination
) -> Page[PremiumUserResponse]:
    subscriptions, total = await PremiumService(session).list_active_subscriptions(
        pagination.limit, pagination.offset
    )
    items = [
        PremiumUserResponse(
            id=pu.id,
            user_id=pu.user_id,
            username=pu.user.username,
            plan_id=pu.plan_id,
            plan_name=pu.plan.name,
            starts_at=pu.starts_at,
            expires_at=pu.expires_at,
            payment_method=pu.payment_method,
        )
        for pu in subscriptions
    ]
    return Page(items=items, total=total, page=pagination.page, size=pagination.size)


@router.post("/grant", response_model=PremiumUserResponse, status_code=status.HTTP_201_CREATED)
async def grant_premium(
    body: PremiumGrantRequest, request: Request, session: DbSession, current_admin: GrantPremiumAdmin
) -> PremiumUserResponse:
    service = PremiumService(session)
    plan = await service.get_plan(body.plan_id)
    if plan is None:
        raise _PLAN_NOT_FOUND

    premium_user = await service.grant(
        user_id=body.user_id,
        plan_id=body.plan_id,
        granted_by=current_admin.id,
        payment_method=body.payment_method,
    )
    await AuditService(session).log(
        admin_id=current_admin.id,
        action="premium_grant",
        entity="premium_user",
        entity_id=str(body.user_id),
        payload={"plan_id": body.plan_id},
        ip=request.client.host if request.client else None,
    )
    await session.commit()
    target_user = await UserService(session).get(premium_user.user_id)
    return PremiumUserResponse(
        id=premium_user.id,
        user_id=premium_user.user_id,
        username=target_user.username if target_user is not None else None,
        plan_id=premium_user.plan_id,
        plan_name=plan.name,
        starts_at=premium_user.starts_at,
        expires_at=premium_user.expires_at,
        payment_method=premium_user.payment_method,
    )
