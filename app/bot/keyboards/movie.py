"""Inline keyboards for the movie module: admin add/edit wizards and user browsing.

Kept in one file (rather than split admin/user) since callback-data
namespaces already keep the two sides apart (``madd:``/``mmg:`` for admin,
``mv:`` for the user-facing browse/search/delivery flow) and several
builders (the category checklist, the yes/no picker) are shared between them.
"""

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import Category, Movie

DONE_BUTTON_TEXT = "✅ Tayyor"


def skip_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⏭ O'tkazib yuborish", callback_data=callback_data)]]
    )


def yes_no_keyboard(yes_callback: str, no_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha", callback_data=yes_callback),
                InlineKeyboardButton(text="❌ Yo'q", callback_data=no_callback),
            ]
        ]
    )


def suggestion_keyboard(accept_callback: str) -> InlineKeyboardMarkup:
    """One button to accept an auto-parsed suggestion (e.g. a caption-derived title) — the
    suggested value itself is shown in the prompt text, not the (length-limited) button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Taklifni qabul qilish", callback_data=accept_callback)]]
    )


def confirm_keyboard(confirm_callback: str, cancel_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=confirm_callback),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=cancel_callback),
            ]
        ]
    )


def movie_detail_keyboard(code: str) -> InlineKeyboardMarkup:
    """The "🎬 Kinoni olish" card shown before actual delivery — see ``mv:detail:{code}``."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Kinoni olish", callback_data=f"mv:deliver:{code}")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="mv:browse")],
        ]
    )


def category_picker_keyboard(
    categories: Sequence[Category],
    selected_ids: set[int],
    toggle_callback: str,
    done_callback: str,
) -> InlineKeyboardMarkup:
    """Multi-select category checklist, re-rendered in place on every toggle.

    ``toggle_callback`` is a format string with an ``{id}`` placeholder
    (e.g. ``"madd:cat:{id}"``) — shared by the add-movie wizard and the edit
    flow's category step, which only differ in callback-data prefix.
    """
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅ ' if cat.id in selected_ids else ''}{cat.name}",
                callback_data=toggle_callback.format(id=cat.id),
            )
        ]
        for cat in categories
    ]
    rows.append([InlineKeyboardButton(text=DONE_BUTTON_TEXT, callback_data=done_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def movie_card_keyboard(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"mmg:edit:{code}")],
            [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"mmg:delete:{code}")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="mmg:back")],
        ]
    )


def edit_field_keyboard(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Nomi", callback_data=f"mmg:editf:{code}:title")],
            [InlineKeyboardButton(text="📄 Tavsif", callback_data=f"mmg:editf:{code}:description")],
            [InlineKeyboardButton(text="🖼 Poster", callback_data=f"mmg:editf:{code}:poster")],
            [InlineKeyboardButton(text="🗂 Kategoriyalar", callback_data=f"mmg:editf:{code}:categories")],
            [InlineKeyboardButton(text="⭐ Premium", callback_data=f"mmg:editf:{code}:premium")],
            [InlineKeyboardButton(text="✅ Faollik", callback_data=f"mmg:editf:{code}:active")],
            [InlineKeyboardButton(text="🔑 Kod", callback_data=f"mmg:editf:{code}:code")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"mmg:open:{code}")],
        ]
    )


def browse_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 Nom bo'yicha qidirish", callback_data="mv:search")],
            [InlineKeyboardButton(text="🏆 Top kinolar", callback_data="mv:top")],
            [InlineKeyboardButton(text="🆕 Yangi qo'shilganlar", callback_data="mv:new")],
            [InlineKeyboardButton(text="🔥 Mashhur (7 kun)", callback_data="mv:popular")],
            [InlineKeyboardButton(text="🗂 Kategoriyalar", callback_data="mv:cats")],
        ]
    )


def movie_list_keyboard(
    movies: Sequence[Movie],
    deliver_callback: str,
    *,
    page: int | None = None,
    total_pages: int | None = None,
    page_callback: str | None = None,
) -> InlineKeyboardMarkup:
    """Tap-to-deliver movie list, with an optional prev/next pagination row.

    ``deliver_callback``/``page_callback`` are format strings with
    ``{code}``/``{page}`` placeholders respectively. The pagination row is
    only added when ``total_pages`` is known and greater than 1.
    """
    rows = [
        [
            InlineKeyboardButton(
                text=f"{movie.title} ({movie.code})",
                callback_data=deliver_callback.format(code=movie.code),
            )
        ]
        for movie in movies
    ]
    if page is not None and total_pages is not None and page_callback is not None and total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=page_callback.format(page=page - 1)))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton(text="➡️", callback_data=page_callback.format(page=page + 1)))
        if nav_row:
            rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_list_keyboard(categories: Sequence[Category]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=cat.name, callback_data=f"mv:cat:{cat.id}:1")] for cat in categories
        ]
    )
