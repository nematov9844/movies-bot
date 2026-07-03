"""Admin add-channel wizard: /panel -> "📢 Kanallar" -> "Kanal qo'shish" (`channel_add`).

Forward-or-@username/-id -> priority -> join limit -> dates -> daily window
-> confirm, each step advancing ``AddChannelStates``. Gated by
``HasPermission`` (MANAGE_CHANNELS is admin+, per the TZ role table) rather
than bare ``IsAdmin``.

``parse_admin_date``/``parse_admin_time`` are reused by ``channel_manage.py``
for the equivalent single-field edit flow, mirroring how ``movie_manage.py``
imports ``PANEL_TEXT`` from ``panel.py``.
"""

from datetime import UTC, datetime, time
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Chat, ChatFullInfo, Message, MessageOriginChannel
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import HasPermission
from app.bot.keyboards.movie import confirm_keyboard, skip_keyboard
from app.bot.states.channel import AddChannelStates
from app.core.logger import get_logger
from app.core.permissions import Permission
from app.database.repositories.admin_repository import AdminRepository
from app.database.repositories.channel_repository import ChannelRepository
from app.services.audit.audit_service import AuditService
from app.services.channel.channel_service import ChannelService

router = Router(name="admin_channel_add")
logger = get_logger(__name__)

_SKIP_PRIORITY = "chadd:skip:priority"
_SKIP_JOIN_LIMIT = "chadd:skip:join_limit"
_SKIP_DATES = "chadd:skip:dates"
_SKIP_DAILY_WINDOW = "chadd:skip:daily_window"
_CONFIRM = "chadd:confirm"
_CANCEL = "chadd:cancel"

CHANNEL_PROMPT = "📢 Kanaldan istalgan postni forward qiling, yoki @username / -100... ID yuboring."
RESOLVE_FAILED_TEXT = "❌ Kanal topilmadi. Qaytadan yuboring."
NOT_CHANNEL_TEXT = "❌ Bu kanal emas. Qaytadan yuboring."
ALREADY_EXISTS_TEXT = "❌ Bu kanal allaqachon ro'yxatda mavjud. Boshqa kanal yuboring."
NOT_ADMIN_TEXT = "❌ Avval botni kanalga admin qiling, so'ng qayta yuboring."
NO_INVITE_PERMISSION_TEXT = (
    "❌ Botga kanalda \"Foydalanuvchilarni taklif qilish\" (invite users) admin huquqini bering, "
    "so'ng qayta yuboring."
)
PRIORITY_PROMPT = "🔢 Ustuvorlik raqamini kiriting (standart: 0, kichigi birinchi ko'rsatiladi):"
PRIORITY_INVALID_TEXT = "❌ Butun son kiriting:"
JOIN_LIMIT_PROMPT = "👥 Obunachilar chegarasini kiriting (standart: cheksiz):"
JOIN_LIMIT_INVALID_TEXT = "❌ Musbat butun son kiriting:"
DATES_PROMPT = (
    "📅 Boshlanish va tugash sanasini kiriting (masalan: 2026-01-01 2026-02-01), "
    "standart: hoziroq boshlanadi, muddatsiz:"
)
DATES_INVALID_TEXT = "❌ Format noto'g'ri. Masalan: 2026-01-01 2026-02-01. Qayta kiriting:"
DAILY_WINDOW_PROMPT = "🕐 Kunlik vaqt oralig'ini kiriting (masalan: 08:00-22:00), standart: doim faol:"
DAILY_WINDOW_INVALID_TEXT = "❌ Format noto'g'ri. Masalan: 08:00-22:00. Qayta kiriting:"
CANCELLED_TEXT = "❌ Bekor qilindi."
CHANNEL_ADDED_TEXT = "✅ Kanal qo'shildi va yoqildi."


def parse_admin_date(raw: str) -> datetime | None:
    """Parses an admin-entered ``YYYY-MM-DD`` date as UTC midnight, or ``None`` if invalid."""
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_admin_time(raw: str) -> time | None:
    """Parses an admin-entered ``HH:MM`` time, or ``None`` if invalid."""
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError:
        return None


def _confirm_text(data: dict[str, Any]) -> str:
    username = data.get("username")
    invite_link = data.get("invite_link")
    link_text = f"@{username}" if username else (invite_link or "yo'q")
    join_limit = data.get("join_limit")
    join_limit_text = str(join_limit) if join_limit is not None else "cheksiz"
    start_date = data.get("start_date")
    expire_date = data.get("expire_date")
    daily_start = data.get("daily_start_time")
    daily_end = data.get("daily_end_time")
    daily_text = f"{daily_start}-{daily_end}" if daily_start and daily_end else "doim faol"
    return (
        "📢 <b>Kanal ma'lumotlarini tasdiqlang:</b>\n\n"
        f"📌 Nomi: {data['title']}\n"
        f"🔗 Havola: {link_text}\n"
        f"🔢 Ustuvorlik: {data.get('priority', 0)}\n"
        f"👥 Chegara: {join_limit_text}\n"
        f"📅 Muddat: {(start_date or 'hoziroq').split('T')[0]} — {(expire_date or 'muddatsiz').split('T')[0]}\n"
        f"🕐 Kunlik oraliq: {daily_text}"
    )


async def _resolve_channel_chat(message: Message, bot: Bot) -> Chat | ChatFullInfo | None:
    if message.forward_origin is not None and isinstance(message.forward_origin, MessageOriginChannel):
        return message.forward_origin.chat

    text = (message.text or "").strip()
    if not text:
        return None

    chat_id: int | str
    if text.startswith("@"):
        chat_id = text
    else:
        try:
            chat_id = int(text)
        except ValueError:
            return None

    try:
        return await bot.get_chat(chat_id)
    except TelegramAPIError:
        return None


@router.callback_query(F.data == "channel_add", HasPermission(Permission.MANAGE_CHANNELS))
async def start_add_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddChannelStates.waiting_for_channel)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(CHANNEL_PROMPT)
    await callback.answer()


@router.message(AddChannelStates.waiting_for_channel, HasPermission(Permission.MANAGE_CHANNELS))
async def receive_channel(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    chat = await _resolve_channel_chat(message, bot)
    if chat is None:
        await message.answer(RESOLVE_FAILED_TEXT)
        return
    if chat.type != ChatType.CHANNEL:
        await message.answer(NOT_CHANNEL_TEXT)
        return
    if await ChannelRepository(session).get_by_channel_id(chat.id) is not None:
        await message.answer(ALREADY_EXISTS_TEXT)
        return

    try:
        member = await bot.get_chat_member(chat.id, bot.id)
    except TelegramAPIError:
        await message.answer(NOT_ADMIN_TEXT)
        return
    if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
        await message.answer(NOT_ADMIN_TEXT)
        return

    username = chat.username
    invite_link: str | None = None
    if username is None:
        try:
            invite_link = await bot.export_chat_invite_link(chat.id)
        except TelegramAPIError:
            await message.answer(NO_INVITE_PERMISSION_TEXT)
            return

    await state.update_data(
        channel_id=chat.id,
        title=chat.title or str(chat.id),
        username=username,
        invite_link=invite_link,
    )
    await state.set_state(AddChannelStates.waiting_for_priority)
    await message.answer(PRIORITY_PROMPT, reply_markup=skip_keyboard(_SKIP_PRIORITY))


async def _advance_to_join_limit(message: Message, state: FSMContext) -> None:
    await state.set_state(AddChannelStates.waiting_for_join_limit)
    await message.answer(JOIN_LIMIT_PROMPT, reply_markup=skip_keyboard(_SKIP_JOIN_LIMIT))


@router.message(AddChannelStates.waiting_for_priority, HasPermission(Permission.MANAGE_CHANNELS))
async def receive_priority(message: Message, state: FSMContext) -> None:
    try:
        priority = int((message.text or "").strip())
    except ValueError:
        await message.answer(PRIORITY_INVALID_TEXT)
        return
    await state.update_data(priority=priority)
    await _advance_to_join_limit(message, state)


@router.callback_query(
    AddChannelStates.waiting_for_priority, F.data == _SKIP_PRIORITY, HasPermission(Permission.MANAGE_CHANNELS)
)
async def skip_priority(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(priority=0)
    if isinstance(callback.message, Message):
        await _advance_to_join_limit(callback.message, state)
    await callback.answer()


async def _advance_to_dates(message: Message, state: FSMContext) -> None:
    await state.set_state(AddChannelStates.waiting_for_dates)
    await message.answer(DATES_PROMPT, reply_markup=skip_keyboard(_SKIP_DATES))


@router.message(AddChannelStates.waiting_for_join_limit, HasPermission(Permission.MANAGE_CHANNELS))
async def receive_join_limit(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        join_limit = int(raw)
        if join_limit <= 0:
            raise ValueError
    except ValueError:
        await message.answer(JOIN_LIMIT_INVALID_TEXT)
        return
    await state.update_data(join_limit=join_limit)
    await _advance_to_dates(message, state)


@router.callback_query(
    AddChannelStates.waiting_for_join_limit, F.data == _SKIP_JOIN_LIMIT, HasPermission(Permission.MANAGE_CHANNELS)
)
async def skip_join_limit(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(join_limit=None)
    if isinstance(callback.message, Message):
        await _advance_to_dates(callback.message, state)
    await callback.answer()


async def _advance_to_daily_window(message: Message, state: FSMContext) -> None:
    await state.set_state(AddChannelStates.waiting_for_daily_window)
    await message.answer(DAILY_WINDOW_PROMPT, reply_markup=skip_keyboard(_SKIP_DAILY_WINDOW))


@router.message(AddChannelStates.waiting_for_dates, HasPermission(Permission.MANAGE_CHANNELS))
async def receive_dates(message: Message, state: FSMContext) -> None:
    parts = (message.text or "").strip().split()
    if len(parts) != 2:
        await message.answer(DATES_INVALID_TEXT)
        return
    start_date = parse_admin_date(parts[0])
    expire_date = parse_admin_date(parts[1])
    if start_date is None or expire_date is None:
        await message.answer(DATES_INVALID_TEXT)
        return
    await state.update_data(start_date=start_date.isoformat(), expire_date=expire_date.isoformat())
    await _advance_to_daily_window(message, state)


@router.callback_query(
    AddChannelStates.waiting_for_dates, F.data == _SKIP_DATES, HasPermission(Permission.MANAGE_CHANNELS)
)
async def skip_dates(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(start_date=None, expire_date=None)
    if isinstance(callback.message, Message):
        await _advance_to_daily_window(callback.message, state)
    await callback.answer()


async def _advance_to_confirm(message: Message, state: FSMContext) -> None:
    await state.set_state(AddChannelStates.waiting_for_confirm)
    data = await state.get_data()
    await message.answer(_confirm_text(data), reply_markup=confirm_keyboard(_CONFIRM, _CANCEL))


@router.message(AddChannelStates.waiting_for_daily_window, HasPermission(Permission.MANAGE_CHANNELS))
async def receive_daily_window(message: Message, state: FSMContext) -> None:
    parts = (message.text or "").strip().split("-")
    if len(parts) != 2:
        await message.answer(DAILY_WINDOW_INVALID_TEXT)
        return
    start_time = parse_admin_time(parts[0].strip())
    end_time = parse_admin_time(parts[1].strip())
    if start_time is None or end_time is None:
        await message.answer(DAILY_WINDOW_INVALID_TEXT)
        return
    await state.update_data(
        daily_start_time=start_time.isoformat(timespec="minutes"),
        daily_end_time=end_time.isoformat(timespec="minutes"),
    )
    await _advance_to_confirm(message, state)


@router.callback_query(
    AddChannelStates.waiting_for_daily_window,
    F.data == _SKIP_DAILY_WINDOW,
    HasPermission(Permission.MANAGE_CHANNELS),
)
async def skip_daily_window(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(daily_start_time=None, daily_end_time=None)
    if isinstance(callback.message, Message):
        await _advance_to_confirm(callback.message, state)
    await callback.answer()


@router.callback_query(
    AddChannelStates.waiting_for_confirm, F.data == _CONFIRM, HasPermission(Permission.MANAGE_CHANNELS)
)
async def confirm_add_channel(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    start_date = datetime.fromisoformat(data["start_date"]) if data.get("start_date") else None
    expire_date = datetime.fromisoformat(data["expire_date"]) if data.get("expire_date") else None
    daily_start_time = time.fromisoformat(data["daily_start_time"]) if data.get("daily_start_time") else None
    daily_end_time = time.fromisoformat(data["daily_end_time"]) if data.get("daily_end_time") else None

    channel = await ChannelService(session).create_channel(
        channel_id=data["channel_id"],
        title=data["title"],
        username=data.get("username"),
        invite_link=data.get("invite_link"),
        priority=data.get("priority", 0),
        join_limit=data.get("join_limit"),
        start_date=start_date,
        expire_date=expire_date,
        daily_start_time=daily_start_time,
        daily_end_time=daily_end_time,
    )

    admin = await AdminRepository(session).get_by_user_id(callback.from_user.id)
    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action="channel_add",
        entity="channel",
        entity_id=str(channel.channel_id),
    )

    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(CHANNEL_ADDED_TEXT)
    await callback.answer()
    logger.info("channel_added", channel_id=channel.channel_id, admin_user_id=callback.from_user.id)


@router.callback_query(
    AddChannelStates.waiting_for_confirm, F.data == _CANCEL, HasPermission(Permission.MANAGE_CHANNELS)
)
async def cancel_add_channel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(CANCELLED_TEXT)
    await callback.answer()
