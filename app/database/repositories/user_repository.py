from datetime import UTC, datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.database.models import PremiumUser, User
from app.database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_broadcastable_ids(self, premium_only: bool | None = None) -> list[int]:
        """User ids eligible for a broadcast send, per ``BroadcastTarget``.

        Always excludes ``is_blocked=True`` (self-blocked in-bot) and
        ``is_active=False`` (bot-blocked, per ``TelegramForbiddenError``
        handling in the broadcast worker) users — there is no point ever
        targeting either. ``premium_only=None`` returns every remaining user
        (the ``ALL`` target); ``True``/``False`` further filter to users
        with/without a currently-active ``PremiumUser`` row, via the same
        ``EXISTS`` condition (``is_active=True AND expires_at > now(UTC)``)
        as ``PremiumUserRepository.get_active_for_user``, so segmentation
        stays consistent with what "active premium" means everywhere else.
        """
        stmt = select(User.id).where(User.is_blocked.is_(False), User.is_active.is_(True))

        if premium_only is not None:
            has_active_premium = exists(
                select(PremiumUser.id).where(
                    PremiumUser.user_id == User.id,
                    PremiumUser.is_active.is_(True),
                    PremiumUser.expires_at > datetime.now(UTC),
                )
            )
            stmt = stmt.where(has_active_premium if premium_only else ~has_active_premium)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(self, id: int, **fields: Any) -> User:
        """Insert a user, or update the given fields if it already exists.

        Used on every bot update to keep telegram-sourced fields (username,
        first/last name, last_seen_at, ...) in sync without a read-then-write
        round trip.
        """
        stmt = (
            pg_insert(User)
            .values(id=id, **fields)
            .on_conflict_do_update(
                index_elements=[User.id],
                set_={**fields, "updated_at": func.now()},
            )
            .returning(User)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
