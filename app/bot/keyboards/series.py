"""Inline keyboards for the admin `/panel` -> "📺 Seriallar" flow, plus the user-facing browse keyboards below."""

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import Movie, Season, Series

FINISH_FORWARDING_CALLBACK = "series:forward_done"


def series_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Yangi serial", callback_data="series:new")],
            [InlineKeyboardButton(text="📋 Seriallar ro'yxati", callback_data="series:list")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="series:panel")],
        ]
    )


def series_list_keyboard(series_list: Sequence[Series]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=series.title, callback_data=f"series:view:{series.id}")]
        for series in series_list
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="series:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def series_card_keyboard(series_id: int, seasons: Sequence[Season]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{season.number}-fasl", callback_data=f"series:season:{season.id}"
            )
        ]
        for season in seasons
    ]
    rows.append([InlineKeyboardButton(text="➕ Fasl qo'shish", callback_data=f"series:season_new:{series_id}")])
    rows.append([InlineKeyboardButton(text="🗑 Serialni o'chirish", callback_data=f"series:delete:{series_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="series:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def season_card_keyboard(season_id: int, series_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Qismlar qo'shish", callback_data=f"series:forward_start:{season_id}")],
            [InlineKeyboardButton(text="🗑 Faslni o'chirish", callback_data=f"series:season_delete:{season_id}")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"series:view:{series_id}")],
        ]
    )


def forwarding_active_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Tugatish", callback_data=FINISH_FORWARDING_CALLBACK)]]
    )


def delete_confirm_keyboard(confirm_callback: str, cancel_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Ha, o'chirish", callback_data=confirm_callback),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=cancel_callback),
            ]
        ]
    )


# --- User-facing browse (search "Naruto" -> seasons -> episodes) -----------
# Own "mv:" prefix (not "series:") so an admin casually browsing as a user
# can never accidentally trigger the admin-only handlers above, which key
# off the "series:" prefix and HasPermission — same namespace convention
# ``movie.py`` already uses for every other user-facing browse callback.


def series_results_keyboard(series_list: Sequence[Series]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📺 {series.title}", callback_data=f"mv:series:{series.id}")]
            for series in series_list
        ]
    )


def season_list_keyboard(seasons: Sequence[Season]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{season.number}-fasl", callback_data=f"mv:season:{season.id}")]
            for season in seasons
        ]
    )


def episode_list_keyboard(
    episodes: Sequence[Movie],
    season_id: int,
    *,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Tap-to-deliver episode list, reusing the existing ``mv:deliver:{code}`` delivery callback."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"{episode.episode_number}-qism", callback_data=f"mv:deliver:{episode.code}"
            )
        ]
        for episode in episodes
    ]
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(
                InlineKeyboardButton(text="⬅️", callback_data=f"mv:ep_page:{season_id}:{page - 1}")
            )
        if page < total_pages:
            nav_row.append(
                InlineKeyboardButton(text="➡️", callback_data=f"mv:ep_page:{season_id}:{page + 1}")
            )
        if nav_row:
            rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)
