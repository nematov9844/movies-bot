"""Admin find/edit/delete movie flow: /panel -> "Kinolar ro'yxati" (`movie_list_admin`).

The admin types a movie code, gets a card back with its current fields, and
from there can edit a single field or soft-delete it. Gated by
``HasPermission`` (MANAGE_MOVIES is moderator+, per the TZ role table).
"""

import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import HasPermission
from app.bot.handlers.admin.panel import PANEL_TEXT
from app.bot.keyboards.admin_panel import admin_panel_keyboard
from app.bot.keyboards.movie import (
    category_picker_keyboard,
    edit_field_keyboard,
    movie_card_keyboard,
    yes_no_keyboard,
)
from app.bot.states.movie import MovieManageStates
from app.core.constants import MOVIE_CODE_PATTERN
from app.core.logger import get_logger
from app.core.permissions import Permission
from app.database.models import Movie
from app.database.repositories.admin_repository import AdminRepository
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.movie_repository import MovieRepository
from app.services.audit.audit_service import AuditService
from app.services.movie.movie_service import MovieService

router = Router(name="admin_movie_manage")
logger = get_logger(__name__)

_MOVIE_CODE_RE = re.compile(MOVIE_CODE_PATTERN)
_TEXT_FIELDS = {"title", "description", "code"}
_FIELD_PROMPTS: dict[str, str] = {
    "title": "📝 Yangi nomni kiriting:",
    "description": '📄 Yangi tavsifni kiriting (tozalash uchun "-" yuboring):',
    "code": "🔑 Yangi kodni kiriting:",
}

POSTER_PROMPT = "🖼 Poster rasmini yuboring:"
POSTER_NOT_A_PHOTO_TEXT = "❌ Iltimos, rasm (photo) yuboring, matn emas:"

FIND_PROMPT = "🔎 Qidirilayotgan kino kodini kiriting:"
NOT_FOUND_TEXT = "❌ Bunday kodli kino topilmadi. Qayta urinib ko'ring:"
DELETE_CONFIRM_TEXT = "🗑 Rostdan ham ushbu kinoni o'chirmoqchimisiz?"
DELETED_TEXT = "✅ Kino o'chirildi (nofaol qilindi)."
CODE_EMPTY_TEXT = "❌ Kod bo'sh bo'lishi mumkin emas. Qayta kiriting:"
CODE_INVALID_TEXT = (
    "❌ Kod faqat lotin harflari, raqamlar, \"-\" va \"_\" belgilaridan iborat bo'lishi "
    "kerak (maksimal 32 belgi). Qayta kiriting:"
)
CODE_TAKEN_TEXT = "❌ Bu kod band. Boshqa kod kiriting:"
VALUE_EMPTY_TEXT = "❌ Qiymat bo'sh bo'lishi mumkin emas. Qayta kiriting:"
NO_CATEGORIES_TEXT = "ℹ️ Hozircha kategoriyalar mavjud emas."
CATEGORY_PROMPT = "🗂 Kategoriyalarni tanlang:"


def _movie_card_text(movie: Movie) -> str:
    description = movie.description or "yo'q"
    categories = ", ".join(cat.name for cat in movie.categories) or "yo'q"
    premium = "Ha" if movie.is_premium else "Yo'q"
    active = "Ha" if movie.is_active else "Yo'q"
    return (
        "🎬 <b>Kino kartasi</b>\n\n"
        f"🔑 Kod: <code>{movie.code}</code>\n"
        f"📝 Nomi: {movie.title}\n"
        f"📄 Tavsif: {description}\n"
        f"🗂 Kategoriyalar: {categories}\n"
        f"⭐ Premium: {premium}\n"
        f"✅ Faol: {active}\n"
        f"👁 Ko'rishlar: {movie.view_count} ta"
    )


async def _log_movie_action(session: AsyncSession, user_id: int, action: str, code: str) -> None:
    admin = await AdminRepository(session).get_by_user_id(user_id)
    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action=action,
        entity="movie",
        entity_id=code,
    )


async def _start_category_edit(message: Message, state: FSMContext, session: AsyncSession, code: str) -> None:
    movie = await MovieRepository(session).get_by_code(code)
    if movie is None:
        await message.edit_text(NOT_FOUND_TEXT, reply_markup=admin_panel_keyboard())
        return

    categories = await CategoryRepository(session).list_active()
    if not categories:
        await message.answer(NO_CATEGORIES_TEXT)
        return

    selected = {cat.id for cat in movie.categories}
    await state.set_state(MovieManageStates.waiting_for_edit_categories)
    await state.update_data(edit_code=code)
    await message.edit_text(
        CATEGORY_PROMPT,
        reply_markup=category_picker_keyboard(
            categories, selected, f"mmg:editcat:{code}:{{id}}", f"mmg:editcat_done:{code}"
        ),
    )


@router.callback_query(F.data == "movie_list_admin", HasPermission(Permission.MANAGE_MOVIES))
async def start_find_movie(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(MovieManageStates.waiting_for_code)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            FIND_PROMPT,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="mmg:back")]]
            ),
        )
    await callback.answer()


@router.message(MovieManageStates.waiting_for_code, HasPermission(Permission.MANAGE_MOVIES))
async def receive_find_code(message: Message, state: FSMContext, session: AsyncSession) -> None:
    code = (message.text or "").strip()
    movie = await MovieRepository(session).get_by_code(code) if code else None
    if movie is None:
        await message.answer(NOT_FOUND_TEXT)
        return

    await state.clear()
    await message.answer(_movie_card_text(movie), reply_markup=movie_card_keyboard(movie.code))


@router.callback_query(F.data.startswith("mmg:open:"), HasPermission(Permission.MANAGE_MOVIES))
async def open_card(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    code = callback.data.removeprefix("mmg:open:")
    movie = await MovieRepository(session).get_by_code(code)
    await state.clear()
    if movie is None:
        await callback.message.edit_text(NOT_FOUND_TEXT, reply_markup=admin_panel_keyboard())
    else:
        await callback.message.edit_text(_movie_card_text(movie), reply_markup=movie_card_keyboard(movie.code))
    await callback.answer()


@router.callback_query(F.data == "mmg:back", HasPermission(Permission.MANAGE_MOVIES))
async def back_to_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(PANEL_TEXT, reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("mmg:edit:"), HasPermission(Permission.MANAGE_MOVIES))
async def start_edit(callback: CallbackQuery) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    code = callback.data.removeprefix("mmg:edit:")
    await callback.message.edit_text(
        f"✏️ <code>{code}</code> — nimani tahrirlaysiz?", reply_markup=edit_field_keyboard(code)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mmg:editf:"), HasPermission(Permission.MANAGE_MOVIES))
async def choose_edit_field(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    code, field = callback.data.removeprefix("mmg:editf:").rsplit(":", maxsplit=1)

    if field in _TEXT_FIELDS:
        await state.set_state(MovieManageStates.waiting_for_edit_value)
        await state.update_data(edit_code=code, edit_field=field)
        await callback.message.edit_text(_FIELD_PROMPTS[field])
    elif field in ("premium", "active"):
        label = "⭐ Premiummi?" if field == "premium" else "✅ Faolmi?"
        await callback.message.edit_text(
            label,
            reply_markup=yes_no_keyboard(f"mmg:editval:{code}:{field}:yes", f"mmg:editval:{code}:{field}:no"),
        )
    elif field == "categories":
        await _start_category_edit(callback.message, state, session, code)
    elif field == "poster":
        await state.set_state(MovieManageStates.waiting_for_poster)
        await state.update_data(edit_code=code)
        await callback.message.edit_text(POSTER_PROMPT)

    await callback.answer()


@router.message(MovieManageStates.waiting_for_poster, F.photo, HasPermission(Permission.MANAGE_MOVIES))
async def receive_poster(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = message.from_user
    if user is None or message.photo is None:
        return

    data = await state.get_data()
    code: str = data["edit_code"]

    movie = await MovieRepository(session).get_by_code(code)
    if movie is None:
        await state.clear()
        await message.answer(NOT_FOUND_TEXT)
        return

    updated = await MovieService(session).update_movie(movie.id, poster_file_id=message.photo[-1].file_id)
    if updated is None:
        await state.clear()
        await message.answer(NOT_FOUND_TEXT)
        return

    await _log_movie_action(session, user.id, "movie_edit", updated.code)
    await state.clear()
    await message.answer(_movie_card_text(updated), reply_markup=movie_card_keyboard(updated.code))


@router.message(MovieManageStates.waiting_for_poster, HasPermission(Permission.MANAGE_MOVIES))
async def receive_poster_wrong_type(message: Message) -> None:
    await message.answer(POSTER_NOT_A_PHOTO_TEXT)


@router.message(MovieManageStates.waiting_for_edit_value, HasPermission(Permission.MANAGE_MOVIES))
async def receive_edit_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return

    data = await state.get_data()
    code: str = data["edit_code"]
    field: str = data["edit_field"]
    raw = (message.text or "").strip()

    movie = await MovieRepository(session).get_by_code(code)
    if movie is None:
        await state.clear()
        await message.answer(NOT_FOUND_TEXT)
        return

    service = MovieService(session)
    if field == "title":
        if not raw:
            await message.answer(VALUE_EMPTY_TEXT)
            return
        updated = await service.update_movie(movie.id, title=raw)
    elif field == "description":
        description = None if raw == "-" else (raw or None)
        updated = await service.update_movie(movie.id, description=description)
    else:  # field == "code"
        if not raw or not _MOVIE_CODE_RE.match(raw):
            await message.answer(CODE_INVALID_TEXT)
            return
        if raw != movie.code and await MovieRepository(session).get_by_code(raw) is not None:
            await message.answer(CODE_TAKEN_TEXT)
            return
        updated = await service.update_movie(movie.id, code=raw)

    if updated is None:
        await state.clear()
        await message.answer(NOT_FOUND_TEXT)
        return

    await _log_movie_action(session, user.id, "movie_edit", updated.code)
    await state.clear()
    await message.answer(_movie_card_text(updated), reply_markup=movie_card_keyboard(updated.code))


@router.callback_query(
    MovieManageStates.waiting_for_edit_categories,
    F.data.startswith("mmg:editcat:"),
    HasPermission(Permission.MANAGE_MOVIES),
)
async def toggle_edit_category(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    code, category_id_str = callback.data.removeprefix("mmg:editcat:").rsplit(":", maxsplit=1)
    category_id = int(category_id_str)

    data = await state.get_data()
    selected = set(data.get("category_ids", []))
    if category_id in selected:
        selected.discard(category_id)
    else:
        selected.add(category_id)
    await state.update_data(category_ids=list(selected))

    categories = await CategoryRepository(session).list_active()
    await callback.message.edit_reply_markup(
        reply_markup=category_picker_keyboard(
            categories, selected, f"mmg:editcat:{code}:{{id}}", f"mmg:editcat_done:{code}"
        )
    )
    await callback.answer()


@router.callback_query(
    MovieManageStates.waiting_for_edit_categories,
    F.data.startswith("mmg:editcat_done:"),
    HasPermission(Permission.MANAGE_MOVIES),
)
async def finish_edit_categories(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    code = callback.data.removeprefix("mmg:editcat_done:")
    data = await state.get_data()
    category_ids: list[int] = data.get("category_ids", [])

    movie = await MovieRepository(session).get_by_code(code)
    await state.clear()
    if movie is None:
        await callback.message.edit_text(NOT_FOUND_TEXT, reply_markup=admin_panel_keyboard())
        await callback.answer()
        return

    updated = await MovieService(session).update_movie(movie.id, category_ids=category_ids)
    if updated is not None:
        await _log_movie_action(session, callback.from_user.id, "movie_edit", updated.code)
        await callback.message.edit_text(_movie_card_text(updated), reply_markup=movie_card_keyboard(updated.code))
    await callback.answer()


@router.callback_query(F.data.startswith("mmg:editval:"), HasPermission(Permission.MANAGE_MOVIES))
async def receive_edit_toggle(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    code, field, choice = callback.data.removeprefix("mmg:editval:").split(":")
    value = choice == "yes"

    movie = await MovieRepository(session).get_by_code(code)
    if movie is None:
        await callback.answer()
        return

    service = MovieService(session)
    if field == "premium":
        updated = await service.update_movie(movie.id, is_premium=value)
    else:
        updated = await service.update_movie(movie.id, is_active=value)

    if updated is not None:
        await _log_movie_action(session, callback.from_user.id, "movie_edit", updated.code)
        await state.clear()
        await callback.message.edit_text(_movie_card_text(updated), reply_markup=movie_card_keyboard(updated.code))
    await callback.answer()


@router.callback_query(F.data.startswith("mmg:delete:"), HasPermission(Permission.MANAGE_MOVIES))
async def confirm_delete(callback: CallbackQuery) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    code = callback.data.removeprefix("mmg:delete:")
    await callback.message.edit_text(
        DELETE_CONFIRM_TEXT,
        reply_markup=yes_no_keyboard(f"mmg:delconfirm:{code}", f"mmg:delcancel:{code}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mmg:delconfirm:"), HasPermission(Permission.MANAGE_MOVIES))
async def do_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    code = callback.data.removeprefix("mmg:delconfirm:")
    movie = await MovieRepository(session).get_by_code(code)
    if movie is None:
        await callback.message.edit_text(NOT_FOUND_TEXT, reply_markup=admin_panel_keyboard())
        await callback.answer()
        return

    await MovieService(session).delete_movie(movie.id)
    await _log_movie_action(session, callback.from_user.id, "movie_delete", code)

    await callback.message.edit_text(f"{DELETED_TEXT}\n\n{PANEL_TEXT}", reply_markup=admin_panel_keyboard())
    await callback.answer()
    logger.info("movie_deleted", code=code, admin_user_id=callback.from_user.id)


@router.callback_query(F.data.startswith("mmg:delcancel:"), HasPermission(Permission.MANAGE_MOVIES))
async def cancel_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    code = callback.data.removeprefix("mmg:delcancel:")
    movie = await MovieRepository(session).get_by_code(code)
    if movie is not None:
        await callback.message.edit_text(_movie_card_text(movie), reply_markup=movie_card_keyboard(movie.code))
    await callback.answer()
