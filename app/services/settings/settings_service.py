from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.setting_repository import SettingRepository

_TRUE_VALUES = {"1", "true", "yes", "on"}


class SettingsService:
    """Read access to runtime settings.

    Phase 3 is a plain DB read through ``SettingRepository``. Phase 12 will
    add Redis caching (see ``REDIS_KEY_SETTING``) and invalidation on top of
    this same class — callers only ever go through ``get``/``get_bool``, so
    that later change stays internal to this file.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SettingRepository(session)

    async def get(self, key: str) -> str | None:
        setting = await self._repo.get_by_key(key)
        return setting.value if setting is not None else None

    async def get_bool(self, key: str, default: bool = False) -> bool:
        value = await self.get(key)
        if value is None:
            return default
        return value.strip().lower() in _TRUE_VALUES
