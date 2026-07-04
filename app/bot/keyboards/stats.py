"""Inline keyboard for the admin `/panel` -> "📊 Statistika" screen.

One row of period tabs (bugun/hafta/oy), the active one marked with dot
bullets so the admin can see at a glance which window they're looking at,
plus a back-to-panel row.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

_PERIODS = (("today", "Bugun"), ("week", "Hafta"), ("month", "Oy"))


def stats_period_keyboard(active_period: str) -> InlineKeyboardMarkup:
    def label(period: str, text: str) -> str:
        return f"• {text} •" if period == active_period else text

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label(period, text), callback_data=f"stats_period:{period}"
                )
                for period, text in _PERIODS
            ],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="stats_panel")],
        ]
    )
