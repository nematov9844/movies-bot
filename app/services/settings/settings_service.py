from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import REDIS_KEY_SETTING
from app.database.models import Setting
from app.database.redis_client import get_redis
from app.database.repositories.setting_repository import SettingRepository

_TRUE_VALUES = {"1", "true", "yes", "on"}
SETTING_CACHE_TTL_SECONDS = 60

# Cached-miss marker, distinguishing "not cached yet" (``redis.get`` returns
# ``None``) from "cached, and the setting genuinely doesn't exist in the DB"
# — the latter needs its own sentinel so a missing key is cached too,
# instead of hitting the DB on every single call site that reads it.
_CACHED_MISS = "\x00missing"


class SettingsService:
    """Read/write access to runtime settings, Redis-cached in front of the DB.

    ``get`` is cache-aside (``REDIS_KEY_SETTING``, 60s TTL, per the TZ);
    ``set`` — the admin-panel/bot write path — updates the DB then
    invalidates the cache immediately, so a change is live right away
    rather than waiting out the TTL. This is what makes "Restart TALAB
    QILINMAYDI — hamma joy settings'ni service orqali o'qiydi" true: every
    consumer (``MaintenanceMiddleware``, ``ForceSubscribeService``,
    ``MovieService``, ...) only ever goes through this one class.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SettingRepository(session)

    async def get(self, key: str) -> str | None:
        redis = get_redis()
        cache_key = REDIS_KEY_SETTING.format(key=key)

        cached = await redis.get(cache_key)
        if cached is not None:
            return None if cached == _CACHED_MISS else cached

        setting = await self._repo.get_by_key(key)
        value = setting.value if setting is not None else None
        await redis.set(cache_key, value if value is not None else _CACHED_MISS, ex=SETTING_CACHE_TTL_SECONDS)
        return value

    async def get_bool(self, key: str, default: bool = False) -> bool:
        value = await self.get(key)
        if value is None:
            return default
        return value.strip().lower() in _TRUE_VALUES

    async def set(self, key: str, value: str) -> None:
        await self._repo.set_value(key, value)
        await get_redis().delete(REDIS_KEY_SETTING.format(key=key))

    async def get_setting(self, key: str) -> Setting | None:
        """The full DB row (type/description/updated_at included) — the web panel's Settings page.

        Bypasses the cache-aside ``get``, which only ever returns the bare
        value string; freshness matters more than caching for an admin
        actively looking at this page.
        """
        return await self._repo.get_by_key(key)

    async def list_all(self) -> list[Setting]:
        return await self._repo.get_many()
