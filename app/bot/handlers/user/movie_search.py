"""User-facing "🔍 Kino qidirish" submenu: search, top/new/popular, categories.

Every handler here is content-serving (it browses or delivers movies), so
every one carries ``flags={"content_gate": True}`` — Phase 7's
ForceSubscribeMiddleware will check that flag to decide whether to enforce
the force-subscribe gate before running the handler.
"""

import html
import math
from collections.abc import Sequence

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.movie import (
    browse_menu_keyboard,
    category_list_keyboard,
    movie_detail_keyboard,
    movie_list_keyboard,
)
from app.bot.keyboards.series import (
    episode_list_keyboard,
    season_list_keyboard,
    series_results_keyboard,
)
from app.bot.states.movie import SearchStates
from app.core.constants import (
    EPISODE_PAGE_SIZE,
    NEW_MOVIES_LIMIT,
    POPULAR_MOVIES_LIMIT,
    POPULAR_MOVIES_WINDOW_DAYS,
    SEARCH_PAGE_SIZE,
    SEASON_PAGE_SIZE,
    TOP_MOVIES_LIMIT,
)
from app.database.models import Movie
from app.database.repositories.category_repository import CategoryRepository
from app.services.movie.movie_service import MovieService
from app.services.series.series_service import SeriesService

router = Router(name="user_movie_search")

# List taps go to the detail card (poster/title/description + one "olish"
# button) — actual delivery is a separate step, only reached from there.
_DETAIL_CALLBACK = "mv:detail:{code}"
_SERIES_RESULTS_LIMIT = 5

BROWSE_MENU_TEXT = "🔍 Nima qilishni xohlaysiz?"
SEARCH_QUERY_PROMPT = "🔎 Qidirilayotgan kino nomini kiriting:"
NO_RESULTS_TEXT = "Hech narsa topilmadi."
NO_CATEGORIES_TEXT = "Hozircha kategoriyalar mavjud emas."
CATEGORY_LIST_TEXT = "🗂 Kategoriyani tanlang:"
CATEGORY_NOT_FOUND_TEXT = "Kategoriya topilmadi."
MOVIE_NOT_FOUND_TEXT = "Kino topilmadi."
SERIES_NOT_FOUND_TEXT = "Serial topilmadi."
SEASON_NOT_FOUND_TEXT = "Fasl topilmadi."
NO_SEASONS_TEXT = "Bu serialda hozircha fasllar yo'q."
NO_EPISODES_TEXT = "Bu faslda hozircha qismlar yo'q."
SEASONS_LABEL_TEXT = "📂 Fasllar:"
EPISODES_LABEL_TEXT = "🎞 Qismlar:"


def _movie_rows_text(movies: Sequence[Movie]) -> str:
    return "\n".join(f"• {movie.title} — <code>{movie.code}</code>" for movie in movies)


def _with_back_row(keyboard: InlineKeyboardMarkup, callback_data: str, text: str = "⬅️ Orqaga") -> InlineKeyboardMarkup:
    """Appends a back row to an existing keyboard — every browse/list screen ends
    with one of these so drilling down never becomes a dead end."""
    return InlineKeyboardMarkup(
        inline_keyboard=[*keyboard.inline_keyboard, [InlineKeyboardButton(text=text, callback_data=callback_data)]]
    )


async def _edit_detail(message: Message, text: str, keyboard: InlineKeyboardMarkup) -> None:
    """Edits a card that may be a photo (series poster) or plain text — season/episode
    pagination reuses this so it keeps working either way."""
    if message.photo:
        await message.edit_caption(caption=text, reply_markup=keyboard)
    else:
        await message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("mv:detail:"), flags={"content_gate": True})
async def show_movie_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    """Poster/title/description + a single "🎬 Kinoni olish" button — tapping that delivers."""
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    code = callback.data.removeprefix("mv:detail:")
    movie = await MovieService(session).get_by_code_cached(code)
    if movie is None:
        await callback.answer(MOVIE_NOT_FOUND_TEXT, show_alert=True)
        return

    source_line = f"\n\n📡 Manba: {movie.source_channel}" if movie.source_channel else ""
    text = f"<b>{movie.title}</b>\n\n{movie.description or ''}{source_line}".rstrip()
    keyboard = movie_detail_keyboard(movie.code)
    if movie.poster_file_id:
        await callback.message.answer_photo(photo=movie.poster_file_id, caption=text, reply_markup=keyboard)
    else:
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


# --- Submenu entry -----------------------------------------------------------


@router.message(F.text == "🔍 Kino qidirish", flags={"content_gate": True})
async def open_browse_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(BROWSE_MENU_TEXT, reply_markup=browse_menu_keyboard())


@router.callback_query(F.data == "mv:browse", flags={"content_gate": True})
async def back_to_browse_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """The one common "back" target every browse/list/search screen below falls
    back to — reachable from anywhere in this router without needing to track
    exactly which list the admin drilled down from."""
    await state.clear()
    if isinstance(callback.message, Message):
        await _edit_detail(callback.message, BROWSE_MENU_TEXT, browse_menu_keyboard())
    await callback.answer()


# --- Free-text title search ---------------------------------------------------


async def _build_search_page(session: AsyncSession, query: str, page: int) -> tuple[str, InlineKeyboardMarkup]:
    """Combines matching series (as one tappable group each, not their 100s of episodes) with
    standalone-movie results (``standalone_only=True`` excludes episodes from the flat list —
    they're only reachable by drilling into their series/season, per the TZ)."""
    series_list, _ = await SeriesService(session).search_series(query, _SERIES_RESULTS_LIMIT, 0)
    movies, total = await MovieService(session).search(query, page, SEARCH_PAGE_SIZE, standalone_only=True)
    total_pages = max(1, math.ceil(total / SEARCH_PAGE_SIZE))

    # `query` is raw user-typed text echoed back under HTML parse_mode —
    # escaped so it can't break entity parsing or spoof formatting.
    header = f'🔎 "{html.escape(query)}" bo\'yicha natijalar ({page}/{total_pages}):'
    body = _movie_rows_text(movies) if movies else (NO_RESULTS_TEXT if not series_list else "")
    text = f"{header}\n\n{body}" if body else header

    movie_keyboard = movie_list_keyboard(
        movies,
        _DETAIL_CALLBACK,
        page=page,
        total_pages=total_pages,
        page_callback="mv:search:page:{page}",
    )
    combined_rows = [*series_results_keyboard(series_list).inline_keyboard, *movie_keyboard.inline_keyboard]
    keyboard = _with_back_row(InlineKeyboardMarkup(inline_keyboard=combined_rows), "mv:browse")
    return text, keyboard


@router.callback_query(F.data == "mv:search", flags={"content_gate": True})
async def start_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchStates.waiting_for_query)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            SEARCH_QUERY_PROMPT,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="mv:browse")]]
            ),
        )
    await callback.answer()


@router.message(SearchStates.waiting_for_query, flags={"content_gate": True})
async def receive_search_query(message: Message, state: FSMContext, session: AsyncSession) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer(SEARCH_QUERY_PROMPT)
        return

    await state.update_data(query=query)
    text, keyboard = await _build_search_page(session, query, 1)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(
    SearchStates.waiting_for_query, F.data.startswith("mv:search:page:"), flags={"content_gate": True}
)
async def paginate_search(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    page = int(callback.data.removeprefix("mv:search:page:"))
    data = await state.get_data()
    query = data.get("query")
    if not query:
        await callback.answer()
        return

    text, keyboard = await _build_search_page(session, query, page)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


# --- Static top/new/popular lists --------------------------------------------


async def _render_static_list(callback: CallbackQuery, header: str, movies: Sequence[Movie]) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    body = _movie_rows_text(movies) if movies else NO_RESULTS_TEXT
    keyboard = _with_back_row(movie_list_keyboard(movies, _DETAIL_CALLBACK), "mv:browse")
    await callback.message.edit_text(f"{header}\n\n{body}", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "mv:top", flags={"content_gate": True})
async def show_top(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    movies = await MovieService(session).list_top(TOP_MOVIES_LIMIT)
    await _render_static_list(callback, "🏆 Top kinolar:", movies)


@router.callback_query(F.data == "mv:new", flags={"content_gate": True})
async def show_new(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    movies = await MovieService(session).list_new(NEW_MOVIES_LIMIT)
    await _render_static_list(callback, "🆕 Yangi qo'shilganlar:", movies)


@router.callback_query(F.data == "mv:popular", flags={"content_gate": True})
async def show_popular(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    movies = await MovieService(session).list_popular_recent(POPULAR_MOVIES_WINDOW_DAYS, POPULAR_MOVIES_LIMIT)
    await _render_static_list(callback, f"🔥 Mashhur (so'nggi {POPULAR_MOVIES_WINDOW_DAYS} kun):", movies)


# --- Categories -----------------------------------------------------------


@router.callback_query(F.data == "mv:cats", flags={"content_gate": True})
async def show_categories(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    categories = await CategoryRepository(session).list_active()
    back_only = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="mv:browse")]])
    if not categories:
        await callback.message.edit_text(NO_CATEGORIES_TEXT, reply_markup=back_only)
    else:
        keyboard = _with_back_row(category_list_keyboard(categories), "mv:browse")
        await callback.message.edit_text(CATEGORY_LIST_TEXT, reply_markup=keyboard)
    await callback.answer()


async def _build_category_page(
    session: AsyncSession, category_id: int, page: int
) -> tuple[str, InlineKeyboardMarkup] | None:
    category = await CategoryRepository(session).get(category_id)
    if category is None:
        return None

    movies, total = await MovieService(session).list_by_category(category_id, page, SEARCH_PAGE_SIZE)
    total_pages = max(1, math.ceil(total / SEARCH_PAGE_SIZE))
    header = f"🗂 <b>{category.name}</b> ({page}/{total_pages}):"
    body = _movie_rows_text(movies) if movies else NO_RESULTS_TEXT
    keyboard = movie_list_keyboard(
        movies,
        _DETAIL_CALLBACK,
        page=page,
        total_pages=total_pages,
        page_callback=f"mv:cat:{category_id}:{{page}}",
    )
    keyboard = _with_back_row(keyboard, "mv:cats")
    return f"{header}\n\n{body}", keyboard


@router.callback_query(F.data.startswith("mv:cat:"), flags={"content_gate": True})
async def show_category_movies(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    category_id_str, page_str = callback.data.removeprefix("mv:cat:").split(":")
    result = await _build_category_page(session, int(category_id_str), int(page_str))
    if result is None:
        back_only = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="mv:cats")]]
        )
        await callback.message.edit_text(CATEGORY_NOT_FOUND_TEXT, reply_markup=back_only)
        await callback.answer()
        return

    text, keyboard = result
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


# --- Series -> seasons -> episodes ------------------------------------------
# Both pickers are compact numbered grids (see episode_list_keyboard/
# season_list_keyboard), paginated at EPISODE_PAGE_SIZE/SEASON_PAGE_SIZE —
# so a series with a very large season or episode count still renders as a
# handful of clean screens instead of one very tall list.


async def _build_season_page(
    session: AsyncSession, series_id: int, page: int
) -> tuple[str, InlineKeyboardMarkup] | None:
    service = SeriesService(session)
    series = await service.get_series(series_id)
    if series is None:
        return None

    seasons, total = await service.list_seasons_paginated(
        series_id, SEASON_PAGE_SIZE, (page - 1) * SEASON_PAGE_SIZE
    )
    total_pages = max(1, math.ceil(total / SEASON_PAGE_SIZE))
    source_line = f"\n\n📡 Manba: {series.source_channel}" if series.source_channel else ""
    header = f"📺 <b>{series.title}</b>\n\n{series.description or ''}{source_line}".rstrip()
    body = NO_SEASONS_TEXT if not seasons else SEASONS_LABEL_TEXT
    text = f"{header}\n\n{body}" if body else header
    keyboard = _with_back_row(season_list_keyboard(seasons, series_id, page=page, total_pages=total_pages), "mv:browse")
    return text, keyboard


@router.callback_query(F.data.startswith("mv:series:"), flags={"content_gate": True})
async def show_series_seasons(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    series_id = int(callback.data.removeprefix("mv:series:"))
    service = SeriesService(session)
    series = await service.get_series(series_id)
    result = await _build_season_page(session, series_id, 1)
    if series is None or result is None:
        await callback.answer(SERIES_NOT_FOUND_TEXT, show_alert=True)
        return

    text, keyboard = result
    if series.poster_file_id:
        # A fresh message (not an edit) — the search results list stays visible above it,
        # and every subsequent season/episode tap here edits *this* new message instead.
        await callback.message.answer_photo(photo=series.poster_file_id, caption=text, reply_markup=keyboard)
    else:
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("mv:season_page:"), flags={"content_gate": True})
async def paginate_seasons(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    series_id_str, page_str = callback.data.removeprefix("mv:season_page:").split(":")
    result = await _build_season_page(session, int(series_id_str), int(page_str))
    if result is None:
        await callback.answer(SERIES_NOT_FOUND_TEXT, show_alert=True)
        return

    text, keyboard = result
    await _edit_detail(callback.message, text, keyboard)
    await callback.answer()


async def _build_episode_page(
    session: AsyncSession, season_id: int, page: int
) -> tuple[str, InlineKeyboardMarkup] | None:
    service = SeriesService(session)
    season = await service.get_season(season_id)
    if season is None:
        return None
    series = await service.get_series(season.series_id)

    episodes, total = await service.list_episodes(season_id, EPISODE_PAGE_SIZE, (page - 1) * EPISODE_PAGE_SIZE)
    total_pages = max(1, math.ceil(total / EPISODE_PAGE_SIZE))
    header = f"📺 <b>{series.title if series else '?'} — {season.number}-fasl</b> ({page}/{total_pages}):"
    body = NO_EPISODES_TEXT if not episodes else EPISODES_LABEL_TEXT
    text = f"{header}\n\n{body}" if body else header
    keyboard = episode_list_keyboard(episodes, season_id, page=page, total_pages=total_pages, series_id=season.series_id)
    return text, keyboard


@router.callback_query(F.data.startswith("mv:season:"), flags={"content_gate": True})
async def show_season_episodes(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    season_id = int(callback.data.removeprefix("mv:season:"))
    result = await _build_episode_page(session, season_id, 1)
    if result is None:
        await callback.answer(SEASON_NOT_FOUND_TEXT, show_alert=True)
        return

    text, keyboard = result
    await _edit_detail(callback.message, text, keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("mv:ep_page:"), flags={"content_gate": True})
async def paginate_episodes(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    season_id_str, page_str = callback.data.removeprefix("mv:ep_page:").split(":")
    result = await _build_episode_page(session, int(season_id_str), int(page_str))
    if result is None:
        await callback.answer(SEASON_NOT_FOUND_TEXT, show_alert=True)
        return

    text, keyboard = result
    await _edit_detail(callback.message, text, keyboard)
    await callback.answer()
