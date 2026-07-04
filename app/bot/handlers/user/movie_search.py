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
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.movie import (
    browse_menu_keyboard,
    category_list_keyboard,
    movie_list_keyboard,
)
from app.bot.states.movie import SearchStates
from app.core.constants import (
    NEW_MOVIES_LIMIT,
    POPULAR_MOVIES_LIMIT,
    POPULAR_MOVIES_WINDOW_DAYS,
    SEARCH_PAGE_SIZE,
    TOP_MOVIES_LIMIT,
)
from app.database.models import Movie
from app.database.repositories.category_repository import CategoryRepository
from app.services.movie.movie_service import MovieService

router = Router(name="user_movie_search")

_DELIVER_CALLBACK = "mv:deliver:{code}"

BROWSE_MENU_TEXT = "🔍 Nima qilishni xohlaysiz?"
SEARCH_QUERY_PROMPT = "🔎 Qidirilayotgan kino nomini kiriting:"
NO_RESULTS_TEXT = "Hech narsa topilmadi."
NO_CATEGORIES_TEXT = "Hozircha kategoriyalar mavjud emas."
CATEGORY_LIST_TEXT = "🗂 Kategoriyani tanlang:"
CATEGORY_NOT_FOUND_TEXT = "Kategoriya topilmadi."


def _movie_rows_text(movies: Sequence[Movie]) -> str:
    return "\n".join(f"• {movie.title} — <code>{movie.code}</code>" for movie in movies)


# --- Submenu entry -----------------------------------------------------------


@router.message(F.text == "🔍 Kino qidirish", flags={"content_gate": True})
async def open_browse_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(BROWSE_MENU_TEXT, reply_markup=browse_menu_keyboard())


# --- Free-text title search ---------------------------------------------------


async def _build_search_page(session: AsyncSession, query: str, page: int) -> tuple[str, InlineKeyboardMarkup]:
    movies, total = await MovieService(session).search(query, page, SEARCH_PAGE_SIZE)
    total_pages = max(1, math.ceil(total / SEARCH_PAGE_SIZE))
    # `query` is raw user-typed text echoed back under HTML parse_mode —
    # escaped so it can't break entity parsing or spoof formatting.
    header = f'🔎 "{html.escape(query)}" bo\'yicha natijalar ({page}/{total_pages}):'
    body = _movie_rows_text(movies) if movies else NO_RESULTS_TEXT
    keyboard = movie_list_keyboard(
        movies,
        _DELIVER_CALLBACK,
        page=page,
        total_pages=total_pages,
        page_callback="mv:search:page:{page}",
    )
    return f"{header}\n\n{body}", keyboard


@router.callback_query(F.data == "mv:search", flags={"content_gate": True})
async def start_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchStates.waiting_for_query)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(SEARCH_QUERY_PROMPT)
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
    await callback.message.edit_text(
        f"{header}\n\n{body}", reply_markup=movie_list_keyboard(movies, _DELIVER_CALLBACK)
    )
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
    if not categories:
        await callback.message.edit_text(NO_CATEGORIES_TEXT)
    else:
        await callback.message.edit_text(CATEGORY_LIST_TEXT, reply_markup=category_list_keyboard(categories))
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
        _DELIVER_CALLBACK,
        page=page,
        total_pages=total_pages,
        page_callback=f"mv:cat:{category_id}:{{page}}",
    )
    return f"{header}\n\n{body}", keyboard


@router.callback_query(F.data.startswith("mv:cat:"), flags={"content_gate": True})
async def show_category_movies(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    category_id_str, page_str = callback.data.removeprefix("mv:cat:").split(":")
    result = await _build_category_page(session, int(category_id_str), int(page_str))
    if result is None:
        await callback.message.edit_text(CATEGORY_NOT_FOUND_TEXT)
        await callback.answer()
        return

    text, keyboard = result
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
