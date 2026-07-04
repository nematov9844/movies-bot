"""Business logic for admin channel management (Phase 7's force-subscribe channels).

Mirrors ``MovieService``'s shape: a thin service composing
``ChannelRepository`` for the `/panel` -> "📢 Kanallar" add/list/edit/delete
flows. All lookups/mutations here operate on the ``channels.id`` primary
key (not the Telegram ``channel_id``) since that's what the admin UI's
callback-data addresses — ``ForceSubscribeService`` is the one that works in
terms of the Telegram ``channel_id``.
"""

from datetime import UTC, datetime, time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Channel
from app.database.repositories.channel_repository import ChannelRepository

# Sentinel distinguishing "leave this field alone" from "clear it to None" in
# ``update_channel`` — plain ``None`` can't be the default since several
# fields (join_limit, start_date, ...) legitimately need to be clearable.
_UNSET: Any = object()


class ChannelService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ChannelRepository(session)

    async def create_channel(
        self,
        *,
        channel_id: int,
        title: str,
        username: str | None,
        invite_link: str | None,
        priority: int = 0,
        join_limit: int | None = None,
        start_date: datetime | None = None,
        expire_date: datetime | None = None,
        daily_start_time: time | None = None,
        daily_end_time: time | None = None,
    ) -> Channel:
        return await self._repo.create(
            channel_id=channel_id,
            title=title,
            username=username,
            invite_link=invite_link,
            priority=priority,
            join_limit=join_limit,
            start_date=start_date,
            expire_date=expire_date,
            daily_start_time=daily_start_time,
            daily_end_time=daily_end_time,
            is_active=True,
            is_required=True,
        )

    async def list_all(self) -> list[Channel]:
        return await self._repo.get_many()

    async def get(self, id: int) -> Channel | None:
        return await self._repo.get(id)

    async def toggle_active(self, id: int) -> Channel | None:
        channel = await self._repo.get(id)
        if channel is None:
            return None
        channel.is_active = not channel.is_active
        await self._session.flush()
        return channel

    async def update_channel(
        self,
        id: int,
        *,
        priority: int | None = _UNSET,
        join_limit: int | None = _UNSET,
        start_date: datetime | None = _UNSET,
        expire_date: datetime | None = _UNSET,
        daily_start_time: time | None = _UNSET,
        daily_end_time: time | None = _UNSET,
        is_required: bool | None = _UNSET,
    ) -> Channel | None:
        """Apply the given field(s) — anything left as ``_UNSET`` is untouched."""
        channel = await self._repo.get(id)
        if channel is None:
            return None

        if priority is not _UNSET:
            channel.priority = priority
        if join_limit is not _UNSET:
            channel.join_limit = join_limit
        if start_date is not _UNSET:
            channel.start_date = start_date
        if expire_date is not _UNSET:
            channel.expire_date = expire_date
        if daily_start_time is not _UNSET:
            channel.daily_start_time = daily_start_time
        if daily_end_time is not _UNSET:
            channel.daily_end_time = daily_end_time
        if is_required is not _UNSET:
            channel.is_required = is_required

        await self._session.flush()
        return channel

    async def delete_channel(self, id: int) -> bool:
        """Hard-delete: unlike movies, channels have no soft-delete — the ON/OFF
        toggle (``toggle_active``) is the reversible lever, this is for
        actually removing a misconfigured/no-longer-needed entry."""
        return await self._repo.delete(id)

    async def deactivate_expired_and_over_limit(self) -> list[Channel]:
        """Flip ``is_active`` off for channels whose ``expire_date`` has passed or whose ``join_limit`` is full.

        Extension point for Phase 11's 5-minute scheduler job. Non-destructive,
        like every other state change here — an admin can push out
        ``expire_date`` or raise ``join_limit`` and toggle the channel back on
        with ``toggle_active``, so this never touches ``delete_channel``'s
        actual-removal path.
        """
        now = datetime.now(UTC)
        flipped = []
        for channel in await self._repo.get_many():
            if not channel.is_active:
                continue
            expired = channel.expire_date is not None and channel.expire_date <= now
            over_limit = channel.join_limit is not None and channel.current_joins >= channel.join_limit
            if expired or over_limit:
                channel.is_active = False
                flipped.append(channel)

        if flipped:
            await self._session.flush()
        return flipped
