"""Fine-grained admin permissions layered on top of ``AdminRole``.

Each ``Permission`` has a minimum role required to perform it
(``PERMISSION_MIN_ROLE``). ``has_permission`` compares roles via
``ROLE_HIERARCHY`` so any role at or above the minimum is allowed — e.g. an
``owner`` can do everything an ``admin`` or ``moderator`` can.
"""

from enum import StrEnum

from app.core.constants import ROLE_HIERARCHY, AdminRole


class Permission(StrEnum):
    MANAGE_ADMINS = "manage_admins"
    MANAGE_SETTINGS = "manage_settings"
    MANAGE_MOVIES = "manage_movies"
    BROADCAST = "broadcast"
    MANAGE_CHANNELS = "manage_channels"
    GRANT_PREMIUM = "grant_premium"
    VIEW_STATS = "view_stats"


PERMISSION_MIN_ROLE: dict[Permission, AdminRole] = {
    Permission.MANAGE_ADMINS: AdminRole.OWNER,
    Permission.MANAGE_SETTINGS: AdminRole.ADMIN,
    Permission.MANAGE_MOVIES: AdminRole.MODERATOR,
    Permission.BROADCAST: AdminRole.ADMIN,
    Permission.MANAGE_CHANNELS: AdminRole.ADMIN,
    Permission.GRANT_PREMIUM: AdminRole.ADMIN,
    Permission.VIEW_STATS: AdminRole.MODERATOR,
}


def has_permission(role: AdminRole, permission: Permission) -> bool:
    """Whether ``role`` meets or exceeds the minimum role required for ``permission``."""
    min_role = PERMISSION_MIN_ROLE[permission]
    return ROLE_HIERARCHY[role] >= ROLE_HIERARCHY[min_role]
