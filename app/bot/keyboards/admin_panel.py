from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Root `/panel` menu.

    One row per feature area, each with its own callback-data namespace
    prefix (``movie_*`` here) so later phases can append their own rows —
    ``channel_*`` (7), ``premium_*`` (8), ``broadcast_*`` (9), ``stats_*``
    (10), ``settings_*`` (12) — without touching the existing rows.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Kino qo'shish", callback_data="movie_add")],
            [InlineKeyboardButton(text="📋 Kinolar ro'yxati", callback_data="movie_list_admin")],
            [InlineKeyboardButton(text="📢 Kanallar", callback_data="channel_menu")],
            [InlineKeyboardButton(text="⭐ Premium", callback_data="premium_menu")],
            [InlineKeyboardButton(text="📣 Broadcast", callback_data="broadcast_menu")],
            [InlineKeyboardButton(text="📊 Statistika", callback_data="stats_menu")],
        ]
    )
