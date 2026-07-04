from datetime import UTC, datetime
from typing import Any

from sqlalchemy import exists, func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def search(self, query: str | None, limit: int, offset: int) -> tuple[list[User], int]:
        """Admin-panel Users page search: by exact numeric ``id`` or ``username`` substring.

        ``query=None`` (or blank) lists every user, most-recently-seen
        first. A numeric query matches the Telegram ``id`` exactly (it's
        the primary key, not worth a substring scan); anything else does an
        ``ILIKE`` substring match against ``username``.
        """
        filters = ()
        if query:
            query = query.strip()
            try:
                # int(), not str.isdigit() — Telegram ids are always
                # positive, but isdigit() rejects a leading "-" and would
                # silently misroute any negative-id lookup to the
                # username-substring branch instead of erroring or matching.
                user_id = int(query)
            except ValueError:
                filters = (User.username.ilike(f"%{query}%"),)
            else:
                filters = (User.id == user_id,)

        total = await self.session.scalar(select(func.count()).select_from(User).where(*filters))

        stmt = (
            select(User)
            .where(*filters)
            .order_by(User.last_seen_at.desc().nulls_last())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total or 0

    async def upsert(self, id: int, **fields: Any) -> tuple[User, bool]:
        """Insert a user, or update the given fields if it already exists.

        Used on every bot update to keep telegram-sourced fields (username,
        first/last name, last_seen_at, ...) in sync without a read-then-write
        round trip.

        Returns ``(user, is_new)``. ``is_new`` is read off Postgres's
        ``xmax`` system column, which is ``0`` only for a row inserted by
        the current command and non-zero once ``ON CONFLICT DO UPDATE``
        touches an existing row — the standard trick for telling an insert
        from an update apart within a single upsert statement, without a
        separate existence check. Phase 10's stats counters use it to tell
        new signups from returning users.
        """
        stmt = (
            pg_insert(User)
            .values(id=id, **fields)
            .on_conflict_do_update(
                index_elements=[User.id],
                set_={**fields, "updated_at": func.now()},
            )
            .returning(User, literal_column("(xmax = 0)").label("is_new"))
        )
        result = await self.session.execute(stmt)
        user, is_new = result.one()
        return user, bool(is_new)
