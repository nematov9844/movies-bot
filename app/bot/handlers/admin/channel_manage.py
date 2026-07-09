"""Admin channel menu/list/card/edit/delete flow: /panel -> "📢 Kanallar".

`channel_menu` -> ["Kanal qo'shish" (channel_add.py) | "Kanallar ro'yxati"
(here) | back to panel]. Gated by ``HasPermission`` (MANAGE_CHANNELS is
admin+, per the TZ role table) rather than bare ``IsAdmin``.
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import HasPermission
from app.bot.handlers.admin.channel_add import parse_admin_date, parse_admin_time
from app.bot.handlers.admin.panel import PANEL_TEXT
from app.bot.keyboards.admin_panel import admin_panel_keyboard
from app.bot.keyboards.channel import (
    channel_back_to_card_keyboard,
    channel_card_keyboard,
    channel_edit_field_keyboard,
    channel_list_keyboard,
    channel_menu_keyboard,
)
from app.bot.keyboards.movie import yes_no_keyboard
from app.bot.states.channel import ChannelManageStates
from app.core.logger import get_logger
from app.core.permissions import Permission
from app.database.models import Channel
from app.database.repositories.admin_repository import AdminRepository
from app.services.audit.audit_service import AuditService
from app.services.channel.channel_service import ChannelService

router = Router(name="admin_channel_manage")
logger = get_logger(__name__)

_TEXT_FIELDS = {"priority", "join_limit", "dates", "daily_window"}
_FIELD_PROMPTS: dict[str, str] = {
    "priority": "🔢 Yangi ustuvorlikni kiriting:",
    "join_limit": "👥 Yangi obunachilar chegarasini kiriting (cheklovni olib tashlash uchun \"-\" yuboring):",
    "dates": (
        "📅 Yangi boshlanish va tugash sanasini kiriting (masalan: 2026-01-01 2026-02-01), "
        "tozalash uchun \"-\" yuboring:"
    ),
    "daily_window": (
        "🕐 Yangi kunlik vaqt oralig'ini kiriting (masalan: 08:00-22:00), tozalash uchun \"-\" yuboring:"
    ),
}

CHANNEL_MENU_TEXT = "📢 <b>Kanallar</b>\n\nKerakli amalni tanlang:"
CHANNEL_LIST_TEXT = "📋 Kanallar ro'yxati:"
NO_CHANNELS_TEXT = "ℹ️ Hozircha kanallar mavjud emas."
NOT_FOUND_TEXT = "❌ Kanal topilmadi."
VALUE_EMPTY_TEXT = "❌ Qiymat bo'sh bo'lishi mumkin emas. Qayta kiriting:"
PRIORITY_INVALID_TEXT = "❌ Butun son kiriting:"
JOIN_LIMIT_INVALID_TEXT = "❌ Musbat butun son kiriting yoki tozalash uchun \"-\" yuboring:"
DATES_INVALID_TEXT = "❌ Format noto'g'ri. Masalan: 2026-01-01 2026-02-01. Qayta kiriting:"
DAILY_WINDOW_INVALID_TEXT = "❌ Format noto'g'ri. Masalan: 08:00-22:00. Qayta kiriting:"
DELETE_CONFIRM_TEXT = "🗑 Rostdan ham ushbu kanalni butunlay o'chirmoqchimisiz?"
DELETED_TEXT = "✅ Kanal o'chirildi."
EDIT_FIELD_PROMPT = "✏️ Nimani tahrirlaysiz?"
REQUIRED_PROMPT = "❗️ Majburiy obunami?"


def _channel_card_text(channel: Channel) -> str:
    link = f"@{channel.username}" if channel.username else (channel.invite_link or "yo'q")
    active = "🔛 Yoqilgan" if channel.is_active else "🔴 O'chirilgan"
    required = "Ha" if channel.is_required else "Yo'q"
    join_limit_text = str(channel.join_limit) if channel.join_limit is not None else "cheksiz"
    start = channel.start_date.strftime("%Y-%m-%d") if channel.start_date else "hoziroq"
    expire = channel.expire_date.strftime("%Y-%m-%d") if channel.expire_date else "muddatsiz"
    if channel.daily_start_time and channel.daily_end_time:
        daily = f"{channel.daily_start_time.strftime('%H:%M')}-{channel.daily_end_time.strftime('%H:%M')}"
    else:
        daily = "doim faol"
    return (
        "📢 <b>Kanal kartasi</b>\n\n"
        f"📌 Nomi: {channel.title}\n"
        f"🔗 Havola: {link}\n"
        f"{active}\n"
        f"❗️ Majburiy: {required}\n"
        f"🔢 Ustuvorlik: {channel.priority}\n"
        f"👥 Obunachilar: {channel.current_joins}/{join_limit_text}\n"
        f"📅 Muddat: {start} — {expire}\n"
        f"🕐 Kunlik oraliq: {daily}"
    )


async def _log_channel_action(session: AsyncSession, user_id: int, action: str, channel_tg_id: int) -> None:
    admin = await AdminRepository(session).get_by_user_id(user_id)
    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action=action,
        entity="channel",
        entity_id=str(channel_tg_id),
    )


@router.callback_query(F.data == "channel_menu", HasPermission(Permission.MANAGE_CHANNELS))
async def open_channel_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(CHANNEL_MENU_TEXT, reply_markup=channel_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "chn:panel", HasPermission(Permission.MANAGE_CHANNELS))
async def back_to_admin_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(PANEL_TEXT, reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "channel_list", HasPermission(Permission.MANAGE_CHANNELS))
async def show_channel_list(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    channels = await ChannelService(session).list_all()
    if not channels:
        await callback.message.edit_text(NO_CHANNELS_TEXT, reply_markup=channel_menu_keyboard())
    else:
        await callback.message.edit_text(CHANNEL_LIST_TEXT, reply_markup=channel_list_keyboard(channels))
    await callback.answer()


@router.callback_query(F.data.startswith("chn:open:"), HasPermission(Permission.MANAGE_CHANNELS))
async def open_channel_card(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    channel_id = int(callback.data.removeprefix("chn:open:"))
    channel = await ChannelService(session).get(channel_id)
    await state.clear()
    if channel is None:
        await callback.message.edit_text(NOT_FOUND_TEXT, reply_markup=channel_menu_keyboard())
    else:
        await callback.message.edit_text(_channel_card_text(channel), reply_markup=channel_card_keyboard(channel))
    await callback.answer()


@router.callback_query(F.data.startswith("chn:toggle:"), HasPermission(Permission.MANAGE_CHANNELS))
async def toggle_channel(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    channel_id = int(callback.data.removeprefix("chn:toggle:"))
    channel = await ChannelService(session).toggle_active(channel_id)
    if channel is None:
        await callback.message.edit_text(NOT_FOUND_TEXT, reply_markup=channel_menu_keyboard())
        await callback.answer()
        return

    await _log_channel_action(session, callback.from_user.id, "channel_toggle", channel.channel_id)
    await callback.message.edit_text(_channel_card_text(channel), reply_markup=channel_card_keyboard(channel))
    await callback.answer()


@router.callback_query(F.data.startswith("chn:stats:"), HasPermission(Permission.MANAGE_CHANNELS))
async def show_channel_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    channel_id = int(callback.data.removeprefix("chn:stats:"))
    channel = await ChannelService(session).get(channel_id)
    if channel is None:
        await callback.message.edit_text(NOT_FOUND_TEXT, reply_markup=channel_menu_keyboard())
        await callback.answer()
        return

    limit_text = str(channel.join_limit) if channel.join_limit is not None else "cheksiz"
    text = f"📊 <b>{channel.title}</b> statistikasi\n\n👥 Qo'shilganlar: {channel.current_joins}\n🎯 Chegara: {limit_text}"
    await callback.message.edit_text(text, reply_markup=channel_back_to_card_keyboard(channel_id))
    await callback.answer()


@router.callback_query(F.data.startswith("chn:edit:"), HasPermission(Permission.MANAGE_CHANNELS))
async def start_edit_channel(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    await state.clear()
    channel_id = int(callback.data.removeprefix("chn:edit:"))
    await callback.message.edit_text(EDIT_FIELD_PROMPT, reply_markup=channel_edit_field_keyboard(channel_id))
    await callback.answer()


@router.callback_query(F.data.startswith("chn:editf:"), HasPermission(Permission.MANAGE_CHANNELS))
async def choose_channel_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    channel_id_str, field = callback.data.removeprefix("chn:editf:").rsplit(":", maxsplit=1)
    channel_id = int(channel_id_str)

    if field in _TEXT_FIELDS:
        await state.set_state(ChannelManageStates.waiting_for_edit_value)
        await state.update_data(edit_channel_id=channel_id, edit_field=field)
        await callback.message.edit_text(_FIELD_PROMPTS[field])
    elif field == "required":
        await callback.message.edit_text(
            REQUIRED_PROMPT,
            reply_markup=yes_no_keyboard(
                f"chn:editval:{channel_id}:required:yes", f"chn:editval:{channel_id}:required:no"
            ),
        )
    await callback.answer()


@router.message(ChannelManageStates.waiting_for_edit_value, HasPermission(Permission.MANAGE_CHANNELS))
async def receive_channel_edit_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return

    data = await state.get_data()
    channel_id: int = data["edit_channel_id"]
    field: str = data["edit_field"]
    raw = (message.text or "").strip()
    if not raw:
        await message.answer(VALUE_EMPTY_TEXT)
        return

    service = ChannelService(session)
    if field == "priority":
        try:
            priority = int(raw)
        except ValueError:
            await message.answer(PRIORITY_INVALID_TEXT)
            return
        updated = await service.update_channel(channel_id, priority=priority)
    elif field == "join_limit":
        if raw == "-":
            updated = await service.update_channel(channel_id, join_limit=None)
        else:
            try:
                join_limit = int(raw)
                if join_limit <= 0:
                    raise ValueError
            except ValueError:
                await message.answer(JOIN_LIMIT_INVALID_TEXT)
                return
            updated = await service.update_channel(channel_id, join_limit=join_limit)
    elif field == "dates":
        if raw == "-":
            updated = await service.update_channel(channel_id, start_date=None, expire_date=None)
        else:
            parts = raw.split()
            if len(parts) != 2:
                await message.answer(DATES_INVALID_TEXT)
                return
            start_date = parse_admin_date(parts[0])
            expire_date = parse_admin_date(parts[1])
            if start_date is None or expire_date is None:
                await message.answer(DATES_INVALID_TEXT)
                return
            updated = await service.update_channel(channel_id, start_date=start_date, expire_date=expire_date)
    else:  # field == "daily_window"
        if raw == "-":
            updated = await service.update_channel(channel_id, daily_start_time=None, daily_end_time=None)
        else:
            parts = raw.split("-")
            if len(parts) != 2:
                await message.answer(DAILY_WINDOW_INVALID_TEXT)
                return
            start_time = parse_admin_time(parts[0].strip())
            end_time = parse_admin_time(parts[1].strip())
            if start_time is None or end_time is None:
                await message.answer(DAILY_WINDOW_INVALID_TEXT)
                return
            updated = await service.update_channel(channel_id, daily_start_time=start_time, daily_end_time=end_time)

    if updated is None:
        await state.clear()
        await message.answer(NOT_FOUND_TEXT, reply_markup=channel_menu_keyboard())
        return

    await _log_channel_action(session, user.id, "channel_edit", updated.channel_id)
    await state.clear()
    await message.answer(_channel_card_text(updated), reply_markup=channel_card_keyboard(updated))


@router.callback_query(F.data.startswith("chn:editval:"), HasPermission(Permission.MANAGE_CHANNELS))
async def receive_channel_toggle_value(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    channel_id_str, field, choice = callback.data.removeprefix("chn:editval:").split(":")
    channel_id = int(channel_id_str)
    value = choice == "yes"

    updated = None
    if field == "required":
        updated = await ChannelService(session).update_channel(channel_id, is_required=value)

    if updated is None:
        await callback.message.edit_text(NOT_FOUND_TEXT, reply_markup=channel_menu_keyboard())
        await callback.answer()
        return

    await _log_channel_action(session, callback.from_user.id, "channel_edit", updated.channel_id)
    await state.clear()
    await callback.message.edit_text(_channel_card_text(updated), reply_markup=channel_card_keyboard(updated))
    await callback.answer()


@router.callback_query(F.data.startswith("chn:delete:"), HasPermission(Permission.MANAGE_CHANNELS))
async def confirm_delete_channel(callback: CallbackQuery) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    channel_id = callback.data.removeprefix("chn:delete:")
    await callback.message.edit_text(
        DELETE_CONFIRM_TEXT,
        reply_markup=yes_no_keyboard(f"chn:delconfirm:{channel_id}", f"chn:delcancel:{channel_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("chn:delconfirm:"), HasPermission(Permission.MANAGE_CHANNELS))
async def do_delete_channel(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    channel_id = int(callback.data.removeprefix("chn:delconfirm:"))
    channel = await ChannelService(session).get(channel_id)
    if channel is None:
        await callback.message.edit_text(NOT_FOUND_TEXT, reply_markup=channel_menu_keyboard())
        await callback.answer()
        return

    tg_channel_id = channel.channel_id
    await ChannelService(session).delete_channel(channel_id)
    await _log_channel_action(session, callback.from_user.id, "channel_delete", tg_channel_id)

    await callback.message.edit_text(f"{DELETED_TEXT}\n\n{CHANNEL_MENU_TEXT}", reply_markup=channel_menu_keyboard())
    await callback.answer()
    logger.info("channel_deleted", channel_id=tg_channel_id, admin_user_id=callback.from_user.id)


@router.callback_query(F.data.startswith("chn:delcancel:"), HasPermission(Permission.MANAGE_CHANNELS))
async def cancel_delete_channel(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    channel_id = int(callback.data.removeprefix("chn:delcancel:"))
    channel = await ChannelService(session).get(channel_id)
    if channel is not None:
        await callback.message.edit_text(_channel_card_text(channel), reply_markup=channel_card_keyboard(channel))
    await callback.answer()
