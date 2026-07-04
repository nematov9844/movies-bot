from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import SettingType
from app.database.models import Setting
from app.database.repositories.base import BaseRepository


class SettingRepository(BaseRepository[Setting]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Setting)

    async def get_by_key(self, key: str) -> Setting | None:
        return await self.session.get(Setting, key)

    async def set_value(self, key: str, value: str) -> Setting:
        """Update the value of an existing setting, or create a new one.

        Newly created settings default to ``SettingType.STR`` — creating a
        setting with a non-string type should go through a dedicated
        create call once one exists.
        """
        setting = await self.get_by_key(key)
        if setting is None:
            setting = Setting(key=key, value=value, type=SettingType.STR.value)
            self.session.add(setting)
        else:
            setting.value = value
        await self.session.flush()
        # `updated_at`'s `onupdate=func.now()` marks it expired after this
        # flush (same MissingGreenlet trap as MovieService.update_movie) —
        # refreshed now, still inside an awaited context, so callers can
        # safely serialize the returned row without a second query of
        # their own.
        await self.session.refresh(setting)
        return setting
