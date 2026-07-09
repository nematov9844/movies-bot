"""Resumes a video the auto-parser (``channel_ingest.py``) couldn't confidently
save on its own, straight from the failure DM's buttons — the video is
already sitting in the storage channel, so both paths re-fetch it there by
message id (a forward, not a re-upload) instead of asking the admin to go
find and forward it manually.

- "Film sifatida qo'shish" drops straight into ``movie_add.py``'s existing
  wizard at ``waiting_for_code`` (video step already done).
- "Serial qismi sifatida" needs the admin to still pick/create the
  series+season first (information the parser never had), so the pending
  file is parked in Redis — not FSM state, which ``series_manage.py``'s
  ``view_season`` clears on the way there — and consumed once that
  navigation reaches ``waiting_for_episode_forward``.
"""

import json

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import HasPermission
from app.bot.handlers.admin.movie_add import CODE_PROMPT, DUPLICATE_WARNING_TEXT
from app.bot.keyboards.movie import yes_no_keyboard
from app.bot.keyboards.series import series_list_keyboard
from app.bot.states.movie import AddMovieStates
from app.core.config import settings
from app.core.logger import get_logger
from app.core.permissions import Permission
from app.database.redis_client import get_redis
from app.database.repositories.admin_repository import AdminRepository
from app.database.repositories.movie_repository import MovieRepository
from app.services.audit.audit_service import AuditService
from app.services.series.series_service import SeriesService

router = Router(name="admin_resume_ingest")
logger = get_logger(__name__)

PENDING_RESUME_TTL_SECONDS = 24 * 60 * 60
_PENDING_RESUME_KEY = "pending_resume:{user_id}"

_DUPLICATE_CONTINUE_CALLBACK = "resume:dup:continue"
_DUPLICATE_CANCEL_CALLBACK = "resume:dup:cancel"

NOT_FOUND_TEXT = "❌ Bu video saqlash kanalida topilmadi (o'chirilgan bo'lishi mumkin)."
NO_SERIES_TEXT = "ℹ️ Hozircha seriallar mavjud emas. Avval \"➕ Yangi serial\" orqali yarating."
CHOOSE_SERIES_TEXT = "📺 Ushbu qism qaysi serialga tegishli?"


async def _fetch_from_storage(bot: Bot, user_id: int, storage_message_id: int) -> Message | None:
    try:
        forwarded = await bot.forward_message(
            chat_id=user_id, from_chat_id=settings.storage_channel_id, message_id=storage_message_id
        )
    except Exception:
        logger.warning("resume_fetch_failed", storage_message_id=storage_message_id)
        return None
    return forwarded if forwarded.video is not None else None


@router.callback_query(F.data.startswith("resume:movie:"), HasPermission(Permission.MANAGE_MOVIES))
async def resume_as_movie(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if callback.data is None:
        await callback.answer()
        return

    storage_message_id = int(callback.data.removeprefix("resume:movie:"))
    forwarded = await _fetch_from_storage(bot, callback.from_user.id, storage_message_id)
    if forwarded is None or forwarded.video is None:
        await callback.answer(NOT_FOUND_TEXT, show_alert=True)
        return

    await state.clear()
    await state.update_data(
        file_id=forwarded.video.file_id,
        file_unique_id=forwarded.video.file_unique_id,
        storage_message_id=storage_message_id,
        duration=forwarded.video.duration,
        file_size=forwarded.video.file_size,
        suggested_title=None,
        quality=None,
        year=None,
    )

    duplicate = (
        await MovieRepository(session).get_by_file_unique_id(forwarded.video.file_unique_id)
        if forwarded.video.file_unique_id
        else None
    )
    if duplicate is not None:
        await state.set_state(AddMovieStates.waiting_for_duplicate_confirm)
        await bot.send_message(
            callback.from_user.id,
            DUPLICATE_WARNING_TEXT.format(code=duplicate.code, title=duplicate.title),
            reply_markup=yes_no_keyboard(_DUPLICATE_CONTINUE_CALLBACK, _DUPLICATE_CANCEL_CALLBACK),
        )
        await callback.answer()
        return

    await state.set_state(AddMovieStates.waiting_for_code)
    await bot.send_message(callback.from_user.id, CODE_PROMPT)
    await callback.answer()


@router.callback_query(
    AddMovieStates.waiting_for_duplicate_confirm, F.data == _DUPLICATE_CONTINUE_CALLBACK,
    HasPermission(Permission.MANAGE_MOVIES),
)
async def resume_continue_after_duplicate(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(AddMovieStates.waiting_for_code)
    await bot.send_message(callback.from_user.id, CODE_PROMPT)
    await callback.answer()


@router.callback_query(
    AddMovieStates.waiting_for_duplicate_confirm, F.data == _DUPLICATE_CANCEL_CALLBACK,
    HasPermission(Permission.MANAGE_MOVIES),
)
async def resume_cancel_after_duplicate(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()


@router.callback_query(F.data.startswith("resume:series:"), HasPermission(Permission.MANAGE_MOVIES))
async def resume_as_series(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    storage_message_id = int(callback.data.removeprefix("resume:series:"))
    forwarded = await _fetch_from_storage(bot, callback.from_user.id, storage_message_id)
    if forwarded is None or forwarded.video is None:
        await callback.answer(NOT_FOUND_TEXT, show_alert=True)
        return

    # Redis, not FSM state: the series/season picker the admin is about to
    # navigate (series_manage.py's view_season) clears FSM state on the way,
    # so anything stored there wouldn't survive to waiting_for_episode_forward.
    await get_redis().set(
        _PENDING_RESUME_KEY.format(user_id=callback.from_user.id),
        json.dumps(
            {
                "file_id": forwarded.video.file_id,
                "file_unique_id": forwarded.video.file_unique_id,
                "storage_message_id": storage_message_id,
                "duration": forwarded.video.duration,
                "file_size": forwarded.video.file_size,
            }
        ),
        ex=PENDING_RESUME_TTL_SECONDS,
    )

    series_list = await SeriesService(session).list_all_series()
    if not series_list:
        await bot.send_message(callback.from_user.id, NO_SERIES_TEXT)
    else:
        await bot.send_message(
            callback.from_user.id, CHOOSE_SERIES_TEXT, reply_markup=series_list_keyboard(series_list)
        )
    await callback.answer()


async def consume_pending_resume(
    bot: Bot,
    session: AsyncSession,
    user_id: int,
    *,
    season_id: int,
    is_premium: bool,
    series_title: str,
    season_number: int,
) -> str | None:
    """Called by series_manage.py right after a series/season is picked —
    finishes adding the video the "Serial qismi sifatida" button parked
    earlier, so the admin's *next* forward (if any) starts a fresh episode
    instead of this one being silently expected but never arriving.
    Returns a confirmation line to show alongside the normal forward prompt,
    or None if there was nothing pending."""
    redis = get_redis()
    key = _PENDING_RESUME_KEY.format(user_id=user_id)
    raw = await redis.get(key)
    if raw is None:
        return None
    await redis.delete(key)
    pending = json.loads(raw)

    admin = await AdminRepository(session).get_by_user_id(user_id)
    episode = await SeriesService(session).add_episode(
        season_id=season_id,
        series_title=series_title,
        season_number=season_number,
        file_id=pending["file_id"],
        file_unique_id=pending["file_unique_id"],
        storage_message_id=pending["storage_message_id"],
        duration=pending["duration"],
        file_size=pending["file_size"],
        is_premium=is_premium,
        created_by=admin.id if admin is not None else None,
    )
    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action="episode_add",
        entity="movie",
        entity_id=episode.code,
        payload={"season_id": season_id, "episode_number": episode.episode_number, "source": "resume"},
    )
    logger.info("pending_resume_consumed", movie_code=episode.code, season_id=season_id)
    await bot.send_message(
        user_id, f"✅ {episode.episode_number}-qism qo'shildi (kod: <code>{episode.code}</code>)."
    )
    return episode.code
