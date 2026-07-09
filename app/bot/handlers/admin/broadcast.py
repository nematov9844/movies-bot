"""Admin broadcast compose/target/confirm wizard: /panel -> "📣 Broadcast".

Message (any type) -> target audience -> confirmation card -> send, each
step advancing ``BroadcastStates``, mirroring ``premium_grant.py``/
``channel_add.py``'s wizard style. Gated by ``HasPermission
(Permission.BROADCAST)`` (admin+, per the TZ role table).

The actual send is a rate-limited ``copy_message`` loop that can run for
minutes to hours — ``confirm_broadcast`` only creates the ``Broadcast`` row
and hands off to ``broadcast_worker.schedule_broadcast``, which runs the
loop as a tracked background task independent of this handler call.
``bc:cancel:<id>`` (a different callback namespace from this wizard's own
``bc:cancel_setup``) requests that a *running* broadcast stop early; the
worker notices within its ~10s polling cadence.
"""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import HasPermission
from app.bot.handlers.admin.panel import PANEL_TEXT
from app.bot.keyboards.admin_panel import admin_panel_keyboard
from app.bot.keyboards.broadcast import (
    TARGET_LABELS,
    broadcast_confirm_keyboard,
    broadcast_progress_keyboard,
    broadcast_target_keyboard,
    format_progress_text,
)
from app.bot.states.broadcast import BroadcastStates
from app.core.constants import REDIS_KEY_BROADCAST_LOCK, BroadcastTarget
from app.core.logger import get_logger
from app.core.permissions import Permission
from app.database.redis_client import get_redis
from app.database.repositories.admin_repository import AdminRepository
from app.services.audit.audit_service import AuditService
from app.services.broadcast.broadcast_service import BroadcastService
from app.services.broadcast.broadcast_worker import schedule_broadcast

router = Router(name="admin_broadcast")
logger = get_logger(__name__)

MESSAGE_PROMPT = "📣 Yubormoqchi bo'lgan xabaringizni yuboring (matn, rasm, video va h.k.)."
TARGET_PROMPT = "🎯 Qabul qiluvchilarni tanlang:"
CANCELLED_TEXT = "❌ Bekor qilindi."
ALREADY_RUNNING_TEXT = "⏳ Hozir boshqa broadcast ishlamoqda. Avval uni tugating yoki to'xtating."
CANCEL_REQUESTED_TEXT = "⏹ Bekor qilish so'rovi yuborildi. Bir necha soniyada to'xtaydi."
NOT_ADMIN_TEXT = "❌ Admin topilmadi."


def _confirm_text(target: BroadcastTarget, total: int) -> str:
    return (
        "📣 <b>Broadcast yuborishni tasdiqlang:</b>\n\n"
        f"🎯 Qabul qiluvchilar: {TARGET_LABELS[target]}\n"
        f"👤 Soni: {total}"
    )


@router.callback_query(F.data == "broadcast_menu", HasPermission(Permission.BROADCAST))
async def start_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BroadcastStates.waiting_for_message)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            MESSAGE_PROMPT,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="bc:cancel_setup")]]
            ),
        )
    await callback.answer()


@router.message(BroadcastStates.waiting_for_message, HasPermission(Permission.BROADCAST))
async def receive_broadcast_message(message: Message, state: FSMContext) -> None:
    # copy_message replicates whatever content type the source message is,
    # so no branching on it is needed here — only chat_id/message_id, its
    # address, need recording.
    await state.update_data(message_chat_id=message.chat.id, message_id=message.message_id)
    await state.set_state(BroadcastStates.waiting_for_target)
    await message.answer(TARGET_PROMPT, reply_markup=broadcast_target_keyboard())


@router.callback_query(
    BroadcastStates.waiting_for_target, F.data.startswith("bc:target:"), HasPermission(Permission.BROADCAST)
)
async def receive_broadcast_target(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    target = BroadcastTarget(callback.data.removeprefix("bc:target:"))
    total = len(await BroadcastService(session).get_target_user_ids(target))

    await state.update_data(target=target.value)
    await state.set_state(BroadcastStates.waiting_for_confirm)
    await callback.message.edit_text(_confirm_text(target, total), reply_markup=broadcast_confirm_keyboard())
    await callback.answer()


@router.callback_query(
    BroadcastStates.waiting_for_confirm, F.data == "bc:confirm", HasPermission(Permission.BROADCAST)
)
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    # Peek only — the worker itself acquires the lock (SET NX) right before
    # it starts looping, which is the real single-in-flight guarantee. This
    # check just avoids creating a DB row + background task for a broadcast
    # that would immediately no-op against an already-held lock.
    if await get_redis().exists(REDIS_KEY_BROADCAST_LOCK):
        await state.clear()
        await callback.message.edit_text(ALREADY_RUNNING_TEXT)
        await callback.answer()
        return

    data = await state.get_data()
    message_chat_id: int = data["message_chat_id"]
    message_id: int = data["message_id"]
    target = BroadcastTarget(data["target"])

    admin = await AdminRepository(session).get_by_user_id(callback.from_user.id)
    if admin is None:
        await state.clear()
        await callback.message.edit_text(NOT_ADMIN_TEXT)
        await callback.answer()
        return

    broadcast_service = BroadcastService(session)
    target_user_ids = await broadcast_service.get_target_user_ids(target)
    broadcast = await broadcast_service.create(
        admin_id=admin.id,
        message_chat_id=message_chat_id,
        message_id=message_id,
        target=target,
        total=len(target_user_ids),
    )

    await AuditService(session).log(
        admin_id=admin.id,
        action="broadcast_start",
        entity="broadcast",
        entity_id=str(broadcast.id),
        payload={"target": target.value, "total": len(target_user_ids)},
    )

    progress_chat_id = callback.message.chat.id
    progress_message_id = callback.message.message_id
    await callback.message.edit_text(
        format_progress_text(0, len(target_user_ids), 0, 0),
        reply_markup=broadcast_progress_keyboard(broadcast.id),
    )
    await state.clear()
    await callback.answer()

    # Retain the task via schedule_broadcast's module-level registry — an
    # unreferenced asyncio.Task can be garbage-collected mid-run.
    schedule_broadcast(
        bot=bot,
        broadcast_id=broadcast.id,
        message_chat_id=message_chat_id,
        message_id=message_id,
        progress_chat_id=progress_chat_id,
        progress_message_id=progress_message_id,
        target_user_ids=target_user_ids,
    )
    logger.info(
        "broadcast_started",
        broadcast_id=broadcast.id,
        target=target.value,
        total=len(target_user_ids),
        admin_user_id=callback.from_user.id,
    )


@router.callback_query(
    BroadcastStates.waiting_for_confirm, F.data == "bc:cancel_setup", HasPermission(Permission.BROADCAST)
)
async def cancel_broadcast_setup(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(f"{CANCELLED_TEXT}\n\n{PANEL_TEXT}", reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("bc:cancel:"), HasPermission(Permission.BROADCAST))
async def request_cancel_running_broadcast(callback: CallbackQuery, session: AsyncSession) -> None:
    """Requests early stop of a *running* broadcast (distinct from the wizard's own cancel).

    Just flips the Redis flag the worker polls on its ~10s cadence — the
    actual stop, lock release, and status finalization all happen inside
    the worker itself.
    """
    if callback.data is None:
        await callback.answer()
        return

    broadcast_id = int(callback.data.removeprefix("bc:cancel:"))
    await BroadcastService(session).request_cancel(broadcast_id)
    await callback.answer(CANCEL_REQUESTED_TEXT, show_alert=True)
