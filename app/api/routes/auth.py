"""JWT login/refresh for the admin web panel.

``POST /api/auth/login`` and ``POST /api/auth/refresh`` are the only routes
here — Phase 13 builds the actual admin-management screens on top of
``get_current_admin``/``require_permission``. ``GET /api/auth/me`` is kept
as a small "who am I" endpoint since the web panel will want one anyway to
resolve its own session on load; it doubles as a live end-to-end check that
``get_current_admin`` works.
"""

from fastapi import APIRouter, HTTPException, Request, status

from app.api.dependencies.auth import CurrentAdmin
from app.api.dependencies.db import DbSession
from app.api.schemas.auth import LoginRequest, MeResponse, RefreshRequest, TokenResponse
from app.core import security
from app.services.admin.admin_service import AdminService
from app.services.audit.audit_service import AuditService

router = APIRouter(prefix="/api/auth", tags=["auth"])

_LOGIN_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Login yoki parol noto'g'ri",
)
_REFRESH_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Yaroqsiz yoki muddati o'tgan token",
)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, session: DbSession) -> TokenResponse:
    admin_service = AdminService(session)
    audit_service = AuditService(session)
    ip = request.client.host if request.client else None

    admin = await admin_service.authenticate(body.user_id, body.password)
    if admin is None:
        # Resolve an admin_id for the audit trail if one exists, but the
        # HTTP response below is identical either way — never leak whether
        # user_id belongs to a real admin.
        existing = await admin_service.get_by_user_id(body.user_id)
        await audit_service.log(
            admin_id=existing.id if existing is not None else None,
            action="login_failed",
            entity="admin",
            entity_id=str(body.user_id),
            ip=ip,
        )
        await session.commit()
        raise _LOGIN_ERROR

    await audit_service.log(
        admin_id=admin.id,
        action="login",
        entity="admin",
        entity_id=str(admin.user_id),
        ip=ip,
    )
    await session.commit()

    return TokenResponse(
        access_token=security.create_access_token(admin.user_id, admin.role),
        refresh_token=security.create_refresh_token(admin.user_id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, session: DbSession) -> TokenResponse:
    try:
        payload = security.decode_token(body.refresh_token, expected_type="refresh")
    except security.InvalidTokenError as exc:
        raise _REFRESH_ERROR from exc

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise _REFRESH_ERROR from exc

    # Re-fetch from DB rather than trusting the token: refresh tokens carry
    # no role claim, and the admin may have been deactivated since issuance.
    admin = await AdminService(session).get_by_user_id(user_id)
    if admin is None or not admin.is_active:
        raise _REFRESH_ERROR

    return TokenResponse(
        access_token=security.create_access_token(admin.user_id, admin.role),
        refresh_token=security.create_refresh_token(admin.user_id),
    )


@router.get("/me", response_model=MeResponse)
async def me(current_admin: CurrentAdmin) -> MeResponse:
    return MeResponse(user_id=current_admin.user_id, role=current_admin.role)
