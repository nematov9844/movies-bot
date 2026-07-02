from enum import StrEnum


class AdminRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MODERATOR = "moderator"


ROLE_HIERARCHY: dict[AdminRole, int] = {
    AdminRole.MODERATOR: 1,
    AdminRole.ADMIN: 2,
    AdminRole.OWNER: 3,
}


class BroadcastTarget(StrEnum):
    ALL = "all"
    PREMIUM = "premium"
    FREE = "free"


class BroadcastStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"


class SettingType(StrEnum):
    STR = "str"
    INT = "int"
    BOOL = "bool"
    JSON = "json"


DEFAULT_LANGUAGE = "uz"
SUPPORTED_LANGUAGES = ("uz", "ru")

REDIS_KEY_MOVIE_CODE = "movie:code:{code}"
REDIS_KEY_FORCE_SUB = "fs:{user_id}:{channel_id}"
REDIS_KEY_CHANNEL_JOINED = "fs:joined:{channel_id}"
REDIS_KEY_SETTING = "setting:{key}"
REDIS_KEY_PREMIUM = "premium:{user_id}"
REDIS_KEY_BROADCAST_LOCK = "broadcast:lock"
REDIS_KEY_STATS_TODAY = "stats:today:{metric}"

BROADCAST_MESSAGES_PER_SECOND = 25
