"""Admin series/season/episode management: /panel -> "📺 Seriallar".

New serial -> new season (fasl raqami + shu faslning barcha qismlari
premiummi) -> bulk episode forward: admin forwards videos one after another
and each one is auto-numbered/auto-coded (``SeriesService.add_episode``) —
no per-video prompts — until "✅ Tugatish" is tapped. Mirrors
``movie_add.py``'s storage-channel-copy step (re-send into
``STORAGE_CHANNEL_ID`` to get a channel-owned ``file_id``/message id).
"""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import HasPermission
from app.bot.handlers.admin.panel import PANEL_TEXT
from app.bot.keyboards.admin_panel import admin_panel_keyboard
from app.bot.keyboards.movie import skip_keyboard, yes_no_keyboard
from app.bot.keyboards.series import (
    FINISH_FORWARDING_CALLBACK,
    delete_confirm_keyboard,
    forwarding_active_keyboard,
    season_card_keyboard,
    series_card_keyboard,
    series_list_keyboard,
    series_menu_keyboard,
)
from app.bot.states.series import SeriesManageStates
from app.core.config import settings
from app.core.logger import get_logger
from app.core.permissions import Permission
from app.database.repositories.admin_repository import AdminRepository
from app.services.audit.audit_service import AuditService
from app.services.series.series_service import SeriesService

router = Router(name="admin_series_manage")
logger = get_logger(__name__)

SERIES_MENU_TEXT = "📺 <b>Seriallar</b>\n\nKerakli amalni tanlang:"
NO_SERIES_TEXT = "ℹ️ Hozircha seriallar mavjud emas."
SERIES_TITLE_PROMPT = "📺 Serial nomini kiriting (masalan: Naruto):"
TITLE_EMPTY_TEXT = "❌ Nom bo'sh bo'lishi mumkin emas. Qayta kiriting:"
SERIES_DESCRIPTION_PROMPT = "📄 Serial tavsifini kiriting (yoki o'tkazib yuboring):"
_DESCRIPTION_SKIP_CALLBACK = "series:desc_skip"
SEASON_NUMBER_PROMPT = "🔢 Fasl raqamini kiriting (masalan: 1):"
SEASON_NUMBER_INVALID_TEXT = "❌ Musbat butun son kiriting:"
SEASON_NUMBER_TAKEN_TEXT = "❌ Bu raqamli fasl allaqachon mavjud. Boshqa raqam kiriting:"
SEASON_PREMIUM_PROMPT = "⭐ Ushbu faslning barcha qismlari premium foydalanuvchilar uchunmi?"
_SEASON_PREMIUM_YES = "series:season_prem:yes"
_SEASON_PREMIUM_NO = "series:season_prem:no"
FORWARD_PROMPT = (
    "🎬 Endi ushbu faslga tegishli video(lar)ni birma-bir forward qiling.\n"
    "Har bir video avtomatik ravishda navbatdagi qism sifatida qo'shiladi.\n"
    "Tugagach — \"✅ Tugatish\" tugmasini bosing."
)
NOT_VIDEO_DURING_FORWARD_TEXT = "❌ Bu video emas. Video yuboring yoki \"✅ Tugatish\" tugmasini bosing."
NOT_FOUND_TEXT = "❌ Topilmadi."
DELETE_SERIES_CONFIRM_TEXT = "🗑 Rostdan ham ushbu serialni butunlay o'chirmoqchimisiz? (Fasllar ham o'chadi)"
DELETE_SEASON_CONFIRM_TEXT = (
    "🗑 Rostdan ham ushbu faslni o'chirmoqchimisiz? (Qismlar oddiy kino sifatida qoladi)"
)
DELETED_TEXT = "✅ O'chirildi."


def _series_card_text(title: str, description: str | None, season_count: int) -> str:
    return (
        f"📺 <b>{title}</b>\n\n"
        f"📄 Tavsif: {description or 'yo‘q'}\n"
        f"🗂 Fasllar soni: {season_count}"
    )


def _season_card_text(series_title: str, season_number: int, episode_count: int) -> str:
    return (
        f"📺 <b>{series_title} — {season_number}-fasl</b>\n\n"
        f"🎬 Qismlar soni: {episode_count}"
    )


@router.callback_query(F.data == "series_menu", HasPermission(Permission.MANAGE_MOVIES))
async def open_series_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(SERIES_MENU_TEXT, reply_markup=series_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "series:panel", HasPermission(Permission.MANAGE_MOVIES))
async def back_to_admin_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(PANEL_TEXT, reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "series:menu", HasPermission(Permission.MANAGE_MOVIES))
async def back_to_series_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(SERIES_MENU_TEXT, reply_markup=series_menu_keyboard())
    await callback.answer()


# --- New series -------------------------------------------------------------


@router.callback_query(F.data == "series:new", HasPermission(Permission.MANAGE_MOVIES))
async def start_new_series(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SeriesManageStates.waiting_for_series_title)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(SERIES_TITLE_PROMPT)
    await callback.answer()


@router.message(SeriesManageStates.waiting_for_series_title, HasPermission(Permission.MANAGE_MOVIES))
async def receive_series_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer(TITLE_EMPTY_TEXT)
        return

    await state.update_data(series_title=title)
    await state.set_state(SeriesManageStates.waiting_for_series_description)
    await message.answer(SERIES_DESCRIPTION_PROMPT, reply_markup=skip_keyboard(_DESCRIPTION_SKIP_CALLBACK))


async def _create_series_and_show_card(
    message: Message, state: FSMContext, session: AsyncSession, description: str | None
) -> None:
    data = await state.get_data()
    series = await SeriesService(session).create_series(data["series_title"], description)
    await state.clear()
    await message.answer(
        _series_card_text(series.title, series.description, 0),
        reply_markup=series_card_keyboard(series.id, []),
    )
    logger.info("series_added", series_id=series.id, title=series.title)


@router.message(SeriesManageStates.waiting_for_series_description, HasPermission(Permission.MANAGE_MOVIES))
async def receive_series_description(message: Message, state: FSMContext, session: AsyncSession) -> None:
    description = (message.text or "").strip() or None
    await _create_series_and_show_card(message, state, session, description)


@router.callback_query(
    SeriesManageStates.waiting_for_series_description,
    F.data == _DESCRIPTION_SKIP_CALLBACK,
    HasPermission(Permission.MANAGE_MOVIES),
)
async def skip_series_description(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if isinstance(callback.message, Message):
        await _create_series_and_show_card(callback.message, state, session, None)
    await callback.answer()


# --- List / view series ------------------------------------------------------


@router.callback_query(F.data == "series:list", HasPermission(Permission.MANAGE_MOVIES))
async def list_series(callback: CallbackQuery, session: AsyncSession) -> None:
    series_list = await SeriesService(session).list_all_series()
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    if not series_list:
        await callback.message.edit_text(NO_SERIES_TEXT, reply_markup=series_menu_keyboard())
    else:
        await callback.message.edit_text(SERIES_MENU_TEXT, reply_markup=series_list_keyboard(series_list))
    await callback.answer()


@router.callback_query(F.data.startswith("series:view:"), HasPermission(Permission.MANAGE_MOVIES))
async def view_series(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    series_id = int(callback.data.removeprefix("series:view:"))
    service = SeriesService(session)
    series = await service.get_series_with_seasons(series_id)
    if series is None:
        await callback.answer(NOT_FOUND_TEXT, show_alert=True)
        return

    await callback.message.edit_text(
        _series_card_text(series.title, series.description, len(series.seasons)),
        reply_markup=series_card_keyboard(series.id, series.seasons),
    )
    await callback.answer()


# --- New season ---------------------------------------------------------


@router.callback_query(F.data.startswith("series:season_new:"), HasPermission(Permission.MANAGE_MOVIES))
async def start_new_season(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data is None:
        await callback.answer()
        return

    series_id = int(callback.data.removeprefix("series:season_new:"))
    await state.set_state(SeriesManageStates.waiting_for_season_number)
    await state.update_data(series_id=series_id)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(SEASON_NUMBER_PROMPT)
    await callback.answer()


@router.message(SeriesManageStates.waiting_for_season_number, HasPermission(Permission.MANAGE_MOVIES))
async def receive_season_number(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(SEASON_NUMBER_INVALID_TEXT)
        return

    number = int(raw)
    data = await state.get_data()
    series_id: int = data["series_id"]

    if await SeriesService(session).season_number_taken(series_id, number):
        await message.answer(SEASON_NUMBER_TAKEN_TEXT)
        return

    await state.update_data(season_number=number)
    await state.set_state(SeriesManageStates.waiting_for_season_premium_choice)
    await message.answer(SEASON_PREMIUM_PROMPT, reply_markup=yes_no_keyboard(_SEASON_PREMIUM_YES, _SEASON_PREMIUM_NO))


@router.callback_query(
    SeriesManageStates.waiting_for_season_premium_choice,
    F.data.in_({_SEASON_PREMIUM_YES, _SEASON_PREMIUM_NO}),
    HasPermission(Permission.MANAGE_MOVIES),
)
async def receive_season_premium_choice(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    is_premium = callback.data == _SEASON_PREMIUM_YES
    data = await state.get_data()
    series_id: int = data["series_id"]
    season_number: int = data["season_number"]

    service = SeriesService(session)
    series = await service.get_series(series_id)
    if series is None:
        await state.clear()
        await callback.answer(NOT_FOUND_TEXT, show_alert=True)
        return

    season = await service.create_season(series_id, season_number)

    admin = await AdminRepository(session).get_by_user_id(callback.from_user.id)
    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action="season_add",
        entity="season",
        entity_id=str(season.id),
        payload={"series_id": series_id, "number": season_number},
    )

    await state.update_data(
        season_id=season.id,
        is_premium=is_premium,
        series_title=series.title,
        season_number=season_number,
    )
    await state.set_state(SeriesManageStates.waiting_for_episode_forward)
    await callback.message.edit_text(FORWARD_PROMPT, reply_markup=forwarding_active_keyboard())
    await callback.answer()
    logger.info("season_added", season_id=season.id, series_id=series_id, number=season_number)


# --- Bulk episode forward -------------------------------------------------


@router.message(SeriesManageStates.waiting_for_episode_forward, HasPermission(Permission.MANAGE_MOVIES))
async def receive_episode_forward(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.video is None:
        await message.answer(NOT_VIDEO_DURING_FORWARD_TEXT, reply_markup=forwarding_active_keyboard())
        return

    data = await state.get_data()
    season_id: int = data["season_id"]
    is_premium: bool = data["is_premium"]
    series_title: str = data["series_title"]
    season_number: int = data["season_number"]

    sent = await bot.send_video(
        chat_id=settings.storage_channel_id,
        video=message.video.file_id,
        caption=message.caption,
    )
    if sent.video is None:
        await message.answer(NOT_VIDEO_DURING_FORWARD_TEXT, reply_markup=forwarding_active_keyboard())
        return

    admin = await AdminRepository(session).get_by_user_id(message.from_user.id)
    episode = await SeriesService(session).add_episode(
        season_id=season_id,
        series_title=series_title,
        season_number=season_number,
        file_id=sent.video.file_id,
        file_unique_id=sent.video.file_unique_id,
        storage_message_id=sent.message_id,
        duration=sent.video.duration,
        file_size=sent.video.file_size,
        is_premium=is_premium,
        created_by=admin.id if admin is not None else None,
    )

    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action="episode_add",
        entity="movie",
        entity_id=episode.code,
        payload={"season_id": season_id, "episode_number": episode.episode_number},
    )

    await message.answer(
        f"✅ {episode.episode_number}-qism qo'shildi (kod: <code>{episode.code}</code>).\n"
        "Keyingi videoni yuboring yoki \"✅ Tugatish\" tugmasini bosing.",
        reply_markup=forwarding_active_keyboard(),
    )
    logger.info("episode_added", movie_code=episode.code, season_id=season_id)


@router.callback_query(
    SeriesManageStates.waiting_for_episode_forward,
    F.data == FINISH_FORWARDING_CALLBACK,
    HasPermission(Permission.MANAGE_MOVIES),
)
async def finish_forwarding(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    season_id: int = data["season_id"]
    series_title: str = data["series_title"]
    season_number: int = data["season_number"]
    await state.clear()

    service = SeriesService(session)
    season = await service.get_season(season_id)
    if season is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    episode_count = await service.count_episodes(season_id)
    await callback.message.edit_text(
        _season_card_text(series_title, season_number, episode_count),
        reply_markup=season_card_keyboard(season_id, season.series_id),
    )
    await callback.answer("✅ Tugallandi")


@router.callback_query(F.data.startswith("series:forward_start:"), HasPermission(Permission.MANAGE_MOVIES))
async def resume_forwarding_existing_season(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Resumes bulk-forward mode on a season that already has episodes (e.g. adding 101-220 next week).

    Re-derives the premium default from an existing episode instead of
    asking again — see ``SeriesService.get_season_default_premium``.
    """
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    season_id = int(callback.data.removeprefix("series:forward_start:"))
    service = SeriesService(session)
    season = await service.get_season(season_id)
    if season is None:
        await callback.answer(NOT_FOUND_TEXT, show_alert=True)
        return

    series = await service.get_series(season.series_id)
    is_premium = await service.get_season_default_premium(season_id)

    await state.update_data(
        season_id=season_id,
        is_premium=is_premium,
        series_title=series.title if series is not None else "?",
        season_number=season.number,
    )
    await state.set_state(SeriesManageStates.waiting_for_episode_forward)
    await callback.message.edit_text(FORWARD_PROMPT, reply_markup=forwarding_active_keyboard())
    await callback.answer()


# --- View season ---------------------------------------------------------


@router.callback_query(F.data.startswith("series:season:"), HasPermission(Permission.MANAGE_MOVIES))
async def view_season(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    season_id = int(callback.data.removeprefix("series:season:"))
    service = SeriesService(session)
    season = await service.get_season(season_id)
    if season is None:
        await callback.answer(NOT_FOUND_TEXT, show_alert=True)
        return

    series = await service.get_series(season.series_id)
    episode_count = await service.count_episodes(season_id)
    await callback.message.edit_text(
        _season_card_text(series.title if series else "?", season.number, episode_count),
        reply_markup=season_card_keyboard(season_id, season.series_id),
    )
    await callback.answer()


# --- Delete series / season -----------------------------------------------


@router.callback_query(F.data.startswith("series:delete:"), HasPermission(Permission.MANAGE_MOVIES))
async def confirm_delete_series(callback: CallbackQuery) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    series_id = callback.data.removeprefix("series:delete:")
    await callback.message.edit_text(
        DELETE_SERIES_CONFIRM_TEXT,
        reply_markup=delete_confirm_keyboard(
            f"series:delete_confirm:{series_id}", f"series:view:{series_id}"
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("series:delete_confirm:"), HasPermission(Permission.MANAGE_MOVIES))
async def do_delete_series(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    series_id = int(callback.data.removeprefix("series:delete_confirm:"))

    admin = await AdminRepository(session).get_by_user_id(callback.from_user.id)
    await SeriesService(session).delete_series(series_id)
    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action="series_delete",
        entity="series",
        entity_id=str(series_id),
    )

    await callback.message.edit_text(DELETED_TEXT, reply_markup=series_menu_keyboard())
    await callback.answer()
    logger.info("series_deleted", series_id=series_id)


@router.callback_query(F.data.startswith("series:season_delete:"), HasPermission(Permission.MANAGE_MOVIES))
async def confirm_delete_season(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    season_id = int(callback.data.removeprefix("series:season_delete:"))
    season = await SeriesService(session).get_season(season_id)
    if season is None:
        await callback.answer(NOT_FOUND_TEXT, show_alert=True)
        return

    await callback.message.edit_text(
        DELETE_SEASON_CONFIRM_TEXT,
        reply_markup=delete_confirm_keyboard(
            f"series:season_delete_confirm:{season_id}", f"series:view:{season.series_id}"
        ),
    )
    await callback.answer()


@router.callback_query(
    F.data.startswith("series:season_delete_confirm:"), HasPermission(Permission.MANAGE_MOVIES)
)
async def do_delete_season(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    season_id = int(callback.data.removeprefix("series:season_delete_confirm:"))

    service = SeriesService(session)
    season = await service.get_season(season_id)
    series_id = season.series_id if season is not None else None

    admin = await AdminRepository(session).get_by_user_id(callback.from_user.id)
    await service.delete_season(season_id)
    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action="season_delete",
        entity="season",
        entity_id=str(season_id),
    )

    if series_id is not None:
        series = await service.get_series_with_seasons(series_id)
        if series is not None:
            await callback.message.edit_text(
                _series_card_text(series.title, series.description, len(series.seasons)),
                reply_markup=series_card_keyboard(series.id, series.seasons),
            )
            await callback.answer(DELETED_TEXT)
            return

    await callback.message.edit_text(DELETED_TEXT, reply_markup=series_menu_keyboard())
    await callback.answer()
    logger.info("season_deleted", season_id=season_id)
