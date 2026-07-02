from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.database.models import User
from app.database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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
