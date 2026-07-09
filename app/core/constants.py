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
REDIS_KEY_PENDING_UPDATE = "fs:pending:{user_id}"
REDIS_KEY_SETTING = "setting:{key}"
REDIS_KEY_PREMIUM = "premium:{user_id}"
REDIS_KEY_BROADCAST_LOCK = "broadcast:lock"
REDIS_KEY_BROADCAST_CANCEL = "broadcast:{id}:cancel"
REDIS_KEY_STATS_TODAY = "stats:today:{metric}"
REDIS_KEY_THROTTLE = "throttle:{user_id}"

BROADCAST_MESSAGES_PER_SECOND = 25

# Movie module (Phase 6)
MOVIE_CODE_CACHE_TTL_SECONDS = 3600
MOVIE_CODE_PATTERN = r"^[A-Za-z0-9_-]{1,32}$"
SEARCH_PAGE_SIZE = 10
TOP_MOVIES_LIMIT = 10
NEW_MOVIES_LIMIT = 10
POPULAR_MOVIES_LIMIT = 10

# Series/season episode picker: a compact numbered grid rather than one
# button per row, so a season with hundreds of episodes still fits on a
# handful of screens instead of one very tall list.
EPISODE_PAGE_SIZE = 15
EPISODE_GRID_COLUMNS = 5

# Season picker on a series card — same grid treatment as episodes, for
# shows with a large number of seasons.
SEASON_PAGE_SIZE = 15
SEASON_GRID_COLUMNS = 5
POPULAR_MOVIES_WINDOW_DAYS = 7

# Force-subscribe module (Phase 7)
FORCE_SUB_CACHE_TTL_SECONDS = 60
PENDING_UPDATE_TTL_SECONDS = 600
# A misconfigured/inaccessible required channel silently stops being
# enforced (see ForceSubscribeService._is_member) — this rate-limits the
# owner alert about it to at most once per channel per hour instead of once
# per failed membership check.
REDIS_KEY_FORCE_SUB_ALERT = "fs:alert:{channel_id}"
FORCE_SUB_ALERT_TTL_SECONDS = 3600

# Statistics module (Phase 10)
STATS_TOP_LIMIT = 10
STATS_WEEK_DAYS = 7
STATS_MONTH_DAYS = 30

# Scheduler module (Phase 11)
REDIS_KEY_PREMIUM_WARNED = "premium:warned:{premium_user_id}"
PREMIUM_WARNING_HOURS = 24
PREMIUM_WARNED_TTL_SECONDS = 93600  # 26h — covers the warning window with headroom
