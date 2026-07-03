"""Business logic for admin broadcast (mass-message) campaigns.

Composes ``BroadcastRepository`` + ``UserRepository`` behind one service.
Deliberately has no ``Bot``/Telegram I/O dependency — that belongs to
``broadcast_worker.run_broadcast`` (the actual ``copy_message`` send loop),
keeping this service pure DB/Redis business logic: testable without
Telegram I/O, and independent of whichever worker implementation ends up
driving the send.

Cancellation is checked by the worker on a ~10s cadence while looping over
what can be thousands of recipients, so ``is_cancel_requested`` reads a
Redis flag (``REDIS_KEY_BROADCAST_CANCEL``) rather than round-tripping to
the database on every poll.
"""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import REDIS_KEY_BROADCAST_CANCEL, BroadcastStatus, BroadcastTarget
from app.database.models import Broadcast
from app.database.redis_client import get_redis
from app.database.repositories.broadcast_repository import BroadcastRepository
from app.database.repositories.user_repository import UserRepository

# Generous safety net only — the worker clears this key itself as soon as a
# cancel is observed. A broadcast run realistically never takes this long;
# this just guarantees the flag can't outlive some unforeseeable stuck run.
CANCEL_FLAG_TTL_SECONDS = 60 * 60 * 6

_TARGET_PREMIUM_ONLY: dict[BroadcastTarget, bool | None] = {
    BroadcastTarget.ALL: None,
    BroadcastTarget.PREMIUM: True,
    BroadcastTarget.FREE: False,
}


class BroadcastService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BroadcastRepository(session)
        self._user_repo = UserRepository(session)

    async def create(
        self,
        admin_id: int,
        message_chat_id: int,
        message_id: int,
        target: BroadcastTarget,
        total: int,
    ) -> Broadcast:
        return await self._repo.create(
            admin_id=admin_id,
            message_chat_id=message_chat_id,
            message_id=message_id,
            target=target.value,
            status=BroadcastStatus.PENDING.value,
            total=total,
        )

    async def get_target_user_ids(self, target: BroadcastTarget) -> list[int]:
        return await self._user_repo.list_broadcastable_ids(premium_only=_TARGET_PREMIUM_ONLY[target])

    async def mark_running(self, id: int) -> None:
        await self._repo.update(id, status=BroadcastStatus.RUNNING.value, started_at=datetime.now(UTC))

    async def update_progress(self, id: int, sent: int, failed: int, blocked: int) -> None:
        await self._repo.update(id, sent=sent, failed=failed, blocked=blocked)

    async def mark_done(self, id: int) -> None:
        await self._repo.update(id, status=BroadcastStatus.DONE.value, finished_at=datetime.now(UTC))

    async def mark_cancelled(self, id: int) -> None:
        await self._repo.update(id, status=BroadcastStatus.CANCELLED.value, finished_at=datetime.now(UTC))

    async def is_cancel_requested(self, id: int) -> bool:
        redis = get_redis()
        return await redis.exists(REDIS_KEY_BROADCAST_CANCEL.format(id=id)) > 0

    async def request_cancel(self, id: int) -> None:
        redis = get_redis()
        await redis.set(REDIS_KEY_BROADCAST_CANCEL.format(id=id), "1", ex=CANCEL_FLAG_TTL_SECONDS)

    async def clear_cancel_flag(self, id: int) -> None:
        redis = get_redis()
        await redis.delete(REDIS_KEY_BROADCAST_CANCEL.format(id=id))
