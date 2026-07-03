"""Inline keyboards for the premium module: user-facing plan picker plus the
admin `/panel` -> "⭐ Premium" grant flow.

Kept in its own file mirroring ``app/bot/keyboards/channel.py``'s
convention — the user-facing plan picker (``premium:choose:`` prefix) and
the admin grant wizard's plan picker (``prmg:plan:`` prefix) both reuse
``premium_plans_keyboard`` with their own callback prefix, so this file
doesn't need to know which side is calling it.
"""

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import PremiumPlan


def format_price(price: int) -> str:
    """Renders an integer so'm amount with space-separated thousands, e.g. ``50000`` -> ``"50 000"``."""
    return f"{price:,}".replace(",", " ")


def premium_plans_keyboard(plans: Sequence[PremiumPlan], callback_prefix: str) -> InlineKeyboardMarkup:
    """One button per plan (``"<name> — <price> so'm"``), callback ``f"{callback_prefix}{plan.id}"``."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"{plan.name} — {format_price(plan.price)} so'm",
                callback_data=f"{callback_prefix}{plan.id}",
            )
        ]
        for plan in plans
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- Admin: premium menu ---------------------------------------------------


def premium_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Premium berish", callback_data="premium_grant")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="prm:panel")],
        ]
    )
