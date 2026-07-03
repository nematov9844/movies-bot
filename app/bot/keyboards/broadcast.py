"""Inline keyboards for the admin broadcast module: /panel -> "📣 Broadcast".

Kept in its own file mirroring ``app/bot/keyboards/premium.py``'s
convention — ``bc:`` is this module's callback-data namespace end to end
(target picker, cancel-setup, cancel-running-broadcast).
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.constants import BroadcastTarget

TARGET_LABELS: dict[BroadcastTarget, str] = {
    BroadcastTarget.ALL: "👥 Hammaga",
    BroadcastTarget.PREMIUM: "⭐ Premium",
    BroadcastTarget.FREE: "🆓 Bepul (Premium emas)",
}

CANCEL_SETUP = "bc:cancel_setup"


def broadcast_target_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"bc:target:{target.value}")]
        for target, label in TARGET_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yuborish", callback_data="bc:confirm"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=CANCEL_SETUP),
            ]
        ]
    )


def broadcast_progress_keyboard(broadcast_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⏹ To'xtatish", callback_data=f"bc:cancel:{broadcast_id}")]]
    )


def format_progress_text(sent: int, total: int, failed: int, blocked: int) -> str:
    return f"Yuborildi: {sent}/{total} | Xato: {failed} | Blok: {blocked}"
