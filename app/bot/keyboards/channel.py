"""Inline keyboards for the force-subscribe module: user-facing block screen
plus the admin `/panel` -> "📢 Kanallar" add/list/manage flow.

Kept in one file mirroring ``app/bot/keyboards/movie.py``'s convention —
callback-data namespaces (``fs:`` user-facing, ``channel_*``/``chn:`` admin)
already keep the two sides apart.
"""

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.logger import get_logger
from app.database.models import Channel

logger = get_logger(__name__)

VERIFY_BUTTON_TEXT = "✅ Tekshirish"
VERIFY_CALLBACK = "fs:verify"


def _channel_join_url(channel: Channel) -> str | None:
    if channel.invite_link:
        return channel.invite_link
    if channel.username:
        return f"https://t.me/{channel.username}"
    return None


def force_subscribe_keyboard(channels: Sequence[Channel]) -> InlineKeyboardMarkup:
    """One join-link button per blocking channel, plus a final "Tekshirish" row.

    A channel with neither ``invite_link`` nor ``username`` has no way for a
    user to join it from this keyboard — skipped defensively (logged as a
    misconfiguration for the admin to fix) rather than crashing the whole
    force-sub screen.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for channel in channels:
        url = _channel_join_url(channel)
        if url is None:
            logger.warning("channel_missing_join_link", channel_id=channel.channel_id)
            continue
        rows.append([InlineKeyboardButton(text=channel.title, url=url)])
    rows.append([InlineKeyboardButton(text=VERIFY_BUTTON_TEXT, callback_data=VERIFY_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --- Admin: channel menu / list / card -----------------------------------


def channel_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="channel_add")],
            [InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="channel_list")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="chn:panel")],
        ]
    )


def channel_list_keyboard(channels: Sequence[Channel]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'🔛' if channel.is_active else '🔴'} {channel.title}",
                callback_data=f"chn:open:{channel.id}",
            )
        ]
        for channel in channels
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="channel_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channel_card_keyboard(channel: Channel) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Faolsizlantirish" if channel.is_active else "🔛 Faollashtirish"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=f"chn:toggle:{channel.id}")],
            [InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"chn:edit:{channel.id}")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data=f"chn:stats:{channel.id}")],
            [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"chn:delete:{channel.id}")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="channel_list")],
        ]
    )


def channel_edit_field_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔢 Ustuvorlik", callback_data=f"chn:editf:{channel_id}:priority")],
            [
                InlineKeyboardButton(
                    text="👥 Obunachilar chegarasi", callback_data=f"chn:editf:{channel_id}:join_limit"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 Boshlanish/tugash sanasi", callback_data=f"chn:editf:{channel_id}:dates"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🕐 Kunlik vaqt oralig'i", callback_data=f"chn:editf:{channel_id}:daily_window"
                )
            ],
            [InlineKeyboardButton(text="❗️ Majburiylik", callback_data=f"chn:editf:{channel_id}:required")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"chn:open:{channel_id}")],
        ]
    )


def channel_back_to_card_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"chn:open:{channel_id}")]]
    )
