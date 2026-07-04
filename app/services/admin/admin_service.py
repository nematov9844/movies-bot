from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.constants import AdminRole
from app.core.permissions import Permission
from app.core.permissions import has_permission as _permission_granted
from app.database.models import Admin, User
from app.database.repositories.admin_repository import AdminRepository


class AdminService:
    """Admin lookups plus the owner/admin/moderator role & permission system.

    Phase 3 only needed "is this user an admin" for the maintenance-mode
    gate (``is_admin``). Phase 4 adds role lookups, permission checks,
    password auth for the web panel, and idempotent owner seeding on top of
    this same class.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AdminRepository(session)

    async def is_admin(self, user_id: int) -> bool:
        admin = await self._repo.get_by_user_id(user_id)
        return admin is not None and admin.is_active

    async def get_by_user_id(self, user_id: int) -> Admin | None:
        """Raw admin row lookup (active or not), for callers that need the full row.

        Used by the API's ``get_current_admin`` dependency (resolve the JWT
        subject to an ``Admin``) and by audit logging (resolve ``admins.id``
        for the FK) — keeps those callers going through the service layer
        instead of importing ``AdminRepository`` directly.
        """
        return await self._repo.get_by_user_id(user_id)

    async def list_active(self) -> list[Admin]:
        """All currently-active admin rows (any role).

        Used by the premium purchase-intent flow to notify every active
        admin's Telegram DM, and available to any future caller needing the
        same "who can I ping" list.
        """
        return await self._repo.get_many(is_active=True)

    async def list_all(self) -> list[Admin]:
        """Every admin row (active or not) — the web panel's Admins page."""
        return await self._repo.get_many()

    async def get(self, id: int) -> Admin | None:
        return await self._repo.get(id)

    async def create(self, user_id: int, role: AdminRole, password: str) -> Admin:
        """Web panel Admins page "qo'shish": owner-only, per the TZ role table.

        Ensures ``user_id`` has a placeholder ``users`` row first (same
        ``ON CONFLICT DO NOTHING`` idempotent insert ``ensure_owner_seeded``
        uses) since ``admins.user_id`` FKs to it and the target admin may
        never have pressed /start.
        """
        user_stmt = pg_insert(User).values(id=user_id).on_conflict_do_nothing(index_elements=[User.id])
        await self._session.execute(user_stmt)

        return await self._repo.create(
            user_id=user_id,
            role=role.value,
            password_hash=security.hash_password(password),
            is_active=True,
        )

    async def delete(self, id: int) -> bool:
        """Web panel Admins page "o'chirish": a real row delete, not a soft-disable.

        The caller (the API route) is responsible for the two safety
        checks that don't belong in this generic service method — refusing
        to delete the ``owner`` role and refusing to let an admin delete
        their own row — since both need the *acting* admin's identity,
        which this method doesn't take.
        """
        return await self._repo.delete(id)

    async def get_role(self, user_id: int) -> AdminRole | None:
        """The active admin's role for ``user_id``, or ``None`` if not an active admin."""
        admin = await self._repo.get_by_user_id(user_id)
        if admin is None or not admin.is_active:
            return None
        return AdminRole(admin.role)

    async def has_permission(self, user_id: int, permission: Permission) -> bool:
        role = await self.get_role(user_id)
        if role is None:
            return False
        return _permission_granted(role, permission)

    async def ensure_owner_seeded(self) -> None:
        """Guarantee ``settings.owner_id`` has a ``users`` row and an active owner admin.

        Idempotent and safe to call concurrently from multiple processes
        (the bot and API both call this at startup): the user row is
        created with ``INSERT ... ON CONFLICT DO NOTHING`` and the admin row
        with ``INSERT ... ON CONFLICT DO UPDATE``, both single atomic
        statements at the database level, so two processes racing to seed at
        the same time converge on one row each rather than erroring or
        duplicating. If an admin row already exists for the owner with a
        different role (or inactive), it is upgraded in place to
        ``owner``/``is_active=True`` — the owner configured via ``.env`` must
        always end up as owner.
        """
        owner_id = settings.owner_id

        user_stmt = (
            pg_insert(User).values(id=owner_id).on_conflict_do_nothing(index_elements=[User.id])
        )
        await self._session.execute(user_stmt)

        admin_stmt = (
            pg_insert(Admin)
            .values(user_id=owner_id, role=AdminRole.OWNER.value, is_active=True)
            .on_conflict_do_update(
                index_elements=[Admin.user_id],
                set_={"role": AdminRole.OWNER.value, "is_active": True},
            )
        )
        await self._session.execute(admin_stmt)
        await self._session.flush()

    async def set_password(self, user_id: int, password: str) -> bool:
        """Hash and store ``password`` for the active admin at ``user_id``.

        Returns ``False`` (no-op) if there is no active admin row for that
        user_id.
        """
        admin = await self._repo.get_by_user_id(user_id)
        if admin is None or not admin.is_active:
            return False
        admin.password_hash = security.hash_password(password)
        await self._session.flush()
        return True

    async def authenticate(self, user_id: int, password: str) -> Admin | None:
        """Verify web-panel login credentials, returning the ``Admin`` row on success.

        Returns ``None`` for any failure mode (no such admin, inactive,
        no password set yet, wrong password) — callers must not distinguish
        between these to avoid leaking whether a user_id exists.
        """
        admin = await self._repo.get_by_user_id(user_id)
        if admin is None or not admin.is_active or admin.password_hash is None:
            return None
        if not security.verify_password(password, admin.password_hash):
            return None
        return admin
