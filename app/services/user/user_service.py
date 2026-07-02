from datetime import UTC, datetime

from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.database.repositories.user_repository import UserRepository


class UserService:
    """Business logic for the ``users`` table.

    Phase 3 only needs the telegram-upsert flow used on every bot update;
    later phases (profile, referrals, settings) extend this same class
    rather than duplicating it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UserRepository(session)

    async def upsert_from_telegram(self, tg_user: TelegramUser) -> User:
        """Insert-or-refresh a user row from an incoming Telegram user object."""
        return await self._repo.upsert(
            tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            last_seen_at=datetime.now(UTC),
        )
