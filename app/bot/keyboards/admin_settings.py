"""Inline keyboard/text for the admin `/panel` -> "⚙️ Sozlamalar" screen (Phase 12)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def _status(enabled: bool) -> str:
    return "🟢 Yoqilgan" if enabled else "🔴 O'chirilgan"


def settings_menu_text(
    *,
    maintenance: bool,
    force_subscribe: bool,
    premium: bool,
    welcome_text: str,
    support_username: str,
) -> str:
    return (
        "⚙️ <b>Sozlamalar</b>\n\n"
        f"🔧 Texnik xizmat rejimi: {_status(maintenance)}\n"
        f"📢 Majburiy obuna: {_status(force_subscribe)}\n"
        f"⭐ Premium tizimi: {_status(premium)}\n\n"
        f"💬 Salomlashuv matni:\n{welcome_text}\n\n"
        f"🆘 Qo'llab-quvvatlash: {support_username}"
    )


def settings_menu_keyboard(*, maintenance: bool, force_subscribe: bool, premium: bool) -> InlineKeyboardMarkup:
    def toggle_label(text: str, enabled: bool) -> str:
        action = "O'chirish" if enabled else "Yoqish"
        return f"{text}: {action}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=toggle_label("🔧 Texnik xizmat", maintenance),
                    callback_data="stg:toggle:maintenance_mode",
                )
            ],
            [
                InlineKeyboardButton(
                    text=toggle_label("📢 Majburiy obuna", force_subscribe),
                    callback_data="stg:toggle:force_subscribe_enabled",
                )
            ],
            [
                InlineKeyboardButton(
                    text=toggle_label("⭐ Premium", premium),
                    callback_data="stg:toggle:premium_enabled",
                )
            ],
            [InlineKeyboardButton(text="✏️ Salomlashuv matni", callback_data="stg:edit:welcome_text")],
            [InlineKeyboardButton(text="✏️ Support username", callback_data="stg:edit:support_username")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="stg:panel")],
        ]
    )
