"""Admin add-movie wizard: /panel -> "Kino qo'shish" (`movie_add`).

Video -> kod -> nomi -> tavsif -> kategoriyalar -> premium -> tasdiqlash,
each step advancing ``AddMovieStates``. Gated by ``HasPermission`` (not bare
``IsAdmin``) since MANAGE_MOVIES is moderator+, per the TZ role table.
"""

import re
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import HasPermission
from app.bot.keyboards.movie import (
    category_picker_keyboard,
    confirm_keyboard,
    skip_keyboard,
    suggestion_keyboard,
    yes_no_keyboard,
)
from app.bot.states.movie import AddMovieStates
from app.core.config import settings
from app.core.constants import MOVIE_CODE_PATTERN
from app.core.logger import get_logger
from app.core.permissions import Permission
from app.database.repositories.admin_repository import AdminRepository
from app.database.repositories.category_repository import CategoryRepository
from app.database.repositories.movie_repository import MovieRepository
from app.services.audit.audit_service import AuditService
from app.services.movie.movie_service import MovieService
from app.services.parser.caption_parser import extract_deterministic

router = Router(name="admin_movie_add")
logger = get_logger(__name__)

_MOVIE_CODE_RE = re.compile(MOVIE_CODE_PATTERN)
_DESCRIPTION_SKIP_CALLBACK = "madd:desc_skip"
_CATEGORY_TOGGLE_CALLBACK = "madd:cat:{id}"
_CATEGORY_DONE_CALLBACK = "madd:cat_done"
_PREMIUM_YES_CALLBACK = "madd:prem:yes"
_PREMIUM_NO_CALLBACK = "madd:prem:no"
_CONFIRM_CALLBACK = "madd:confirm"
_CANCEL_CALLBACK = "madd:cancel"
_DUPLICATE_CONTINUE_CALLBACK = "madd:dup:continue"
_DUPLICATE_CANCEL_CALLBACK = "madd:dup:cancel"
_TITLE_SUGGESTION_ACCEPT_CALLBACK = "madd:title_suggest"

VIDEO_PROMPT = "🎬 Kino videosini yuboring."
NOT_VIDEO_TEXT = "❌ Bu video emas. Iltimos, kino videosini yuboring."
DUPLICATE_WARNING_TEXT = (
    "⚠️ Bu video allaqachon bazada mavjud (kod: <code>{code}</code>, nomi: {title}).\n"
    "Baribir davom etasizmi?"
)
CODE_PROMPT = "🔑 Kino uchun kod kiriting (masalan: 123):"
CODE_EMPTY_TEXT = "❌ Kod bo'sh bo'lishi mumkin emas. Qayta kiriting:"
CODE_INVALID_TEXT = (
    "❌ Kod faqat lotin harflari, raqamlar, \"-\" va \"_\" belgilaridan iborat bo'lishi "
    "kerak (maksimal 32 belgi). Qayta kiriting:"
)
CODE_TAKEN_TEXT = "❌ Bu kod band. Boshqa kod kiriting:"
TITLE_PROMPT = "📝 Kino nomini kiriting:"
TITLE_SUGGESTION_TEXT = "🤖 Taklif qilingan nom: <b>{title}</b>"
TITLE_EMPTY_TEXT = "❌ Nom bo'sh bo'lishi mumkin emas. Qayta kiriting:"
DESCRIPTION_PROMPT = "📄 Kino tavsifini kiriting (yoki o'tkazib yuboring):"
NO_CATEGORIES_TEXT = "ℹ️ Hozircha kategoriyalar mavjud emas."
CATEGORY_PROMPT = "🗂 Kategoriyalarni tanlang:"
PREMIUM_PROMPT = "⭐ Bu kino premium foydalanuvchilar uchunmi?"
CANCELLED_TEXT = "❌ Bekor qilindi."


def _confirm_text(data: dict[str, Any]) -> str:
    description = data.get("description") or "yo'q"
    all_categories: dict[str, str] = data.get("all_categories", {})
    selected_ids: list[int] = data.get("category_ids", [])
    names = [all_categories[str(cid)] for cid in selected_ids if str(cid) in all_categories]
    categories_text = ", ".join(names) if names else "yo'q"
    premium_text = "Ha" if data.get("is_premium") else "Yo'q"
    return (
        "🎬 <b>Kino ma'lumotlarini tasdiqlang:</b>\n\n"
        f"🔑 Kod: <code>{data['code']}</code>\n"
        f"📝 Nomi: {data['title']}\n"
        f"📄 Tavsif: {description}\n"
        f"🗂 Kategoriyalar: {categories_text}\n"
        f"⭐ Premium: {premium_text}"
    )


async def _advance_to_categories(message: Message, state: FSMContext, session: AsyncSession) -> None:
    categories = await CategoryRepository(session).list_active()
    if not categories:
        await state.update_data(category_ids=[], all_categories={})
        await message.answer(NO_CATEGORIES_TEXT)
        await _prompt_premium(message, state)
        return

    await state.update_data(category_ids=[], all_categories={str(cat.id): cat.name for cat in categories})
    await state.set_state(AddMovieStates.waiting_for_categories)
    await message.answer(
        CATEGORY_PROMPT,
        reply_markup=category_picker_keyboard(
            categories, set(), _CATEGORY_TOGGLE_CALLBACK, _CATEGORY_DONE_CALLBACK
        ),
    )


async def _prompt_premium(message: Message, state: FSMContext) -> None:
    await state.set_state(AddMovieStates.waiting_for_premium)
    await message.answer(PREMIUM_PROMPT, reply_markup=yes_no_keyboard(_PREMIUM_YES_CALLBACK, _PREMIUM_NO_CALLBACK))


@router.callback_query(F.data == "movie_add", HasPermission(Permission.MANAGE_MOVIES))
async def start_add_movie(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddMovieStates.waiting_for_video)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(VIDEO_PROMPT)
    await callback.answer()


@router.message(AddMovieStates.waiting_for_video, HasPermission(Permission.MANAGE_MOVIES))
async def receive_video(message: Message, state: FSMContext, bot: Bot, session: AsyncSession) -> None:
    if message.video is None:
        await message.answer(NOT_VIDEO_TEXT)
        return

    # Re-send into the storage channel (reusing the incoming file_id avoids a
    # re-upload) to get the storage channel's own file_id/message_id — the
    # ones actually used for delivery and identifying the source message.
    sent = await bot.send_video(
        chat_id=settings.storage_channel_id,
        video=message.video.file_id,
        caption=message.caption,
    )
    if sent.video is None:
        await message.answer(NOT_VIDEO_TEXT)
        return

    # Deterministic (regex-only) extraction — pure, no I/O, safe to always
    # run. Only a "title" the parser is confident about (regex-sourced, not
    # a guess) is worth suggesting; quality/year are supplementary metadata
    # this wizard never asked for before, so any regex hit is a free upgrade.
    parsed = extract_deterministic(message.caption or "")
    await state.update_data(
        file_id=sent.video.file_id,
        file_unique_id=sent.video.file_unique_id,
        storage_message_id=sent.message_id,
        duration=sent.video.duration,
        file_size=sent.video.file_size,
        suggested_title=parsed.title if parsed.sources.get("title") == "regex" else None,
        quality=parsed.quality,
        year=parsed.year,
    )

    duplicate = (
        await MovieRepository(session).get_by_file_unique_id(sent.video.file_unique_id)
        if sent.video.file_unique_id
        else None
    )
    if duplicate is not None:
        await state.set_state(AddMovieStates.waiting_for_duplicate_confirm)
        await message.answer(
            DUPLICATE_WARNING_TEXT.format(code=duplicate.code, title=duplicate.title),
            reply_markup=yes_no_keyboard(_DUPLICATE_CONTINUE_CALLBACK, _DUPLICATE_CANCEL_CALLBACK),
        )
        return

    await state.set_state(AddMovieStates.waiting_for_code)
    await message.answer(CODE_PROMPT)


@router.callback_query(
    AddMovieStates.waiting_for_duplicate_confirm,
    F.data == _DUPLICATE_CONTINUE_CALLBACK,
    HasPermission(Permission.MANAGE_MOVIES),
)
async def continue_after_duplicate_warning(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddMovieStates.waiting_for_code)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(CODE_PROMPT)
    await callback.answer()


@router.callback_query(
    AddMovieStates.waiting_for_duplicate_confirm,
    F.data == _DUPLICATE_CANCEL_CALLBACK,
    HasPermission(Permission.MANAGE_MOVIES),
)
async def cancel_after_duplicate_warning(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(CANCELLED_TEXT)
    await callback.answer()


@router.message(AddMovieStates.waiting_for_code, HasPermission(Permission.MANAGE_MOVIES))
async def receive_code(message: Message, state: FSMContext, session: AsyncSession) -> None:
    code = (message.text or "").strip()
    if not code:
        await message.answer(CODE_EMPTY_TEXT)
        return
    if not _MOVIE_CODE_RE.match(code):
        await message.answer(CODE_INVALID_TEXT)
        return

    existing = await MovieRepository(session).get_by_code(code)
    if existing is not None:
        await message.answer(CODE_TAKEN_TEXT)
        return

    await state.update_data(code=code)
    await state.set_state(AddMovieStates.waiting_for_title)

    data = await state.get_data()
    suggested_title = data.get("suggested_title")
    if suggested_title:
        await message.answer(
            f"{TITLE_PROMPT}\n\n{TITLE_SUGGESTION_TEXT.format(title=suggested_title)}",
            reply_markup=suggestion_keyboard(_TITLE_SUGGESTION_ACCEPT_CALLBACK),
        )
    else:
        await message.answer(TITLE_PROMPT)


@router.message(AddMovieStates.waiting_for_title, HasPermission(Permission.MANAGE_MOVIES))
async def receive_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer(TITLE_EMPTY_TEXT)
        return

    await state.update_data(title=title)
    await state.set_state(AddMovieStates.waiting_for_description)
    await message.answer(DESCRIPTION_PROMPT, reply_markup=skip_keyboard(_DESCRIPTION_SKIP_CALLBACK))


@router.callback_query(
    AddMovieStates.waiting_for_title,
    F.data == _TITLE_SUGGESTION_ACCEPT_CALLBACK,
    HasPermission(Permission.MANAGE_MOVIES),
)
async def accept_title_suggestion(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    suggested_title = data.get("suggested_title")
    if not suggested_title or not isinstance(callback.message, Message):
        await callback.answer()
        return

    await state.update_data(title=suggested_title)
    await state.set_state(AddMovieStates.waiting_for_description)
    await callback.message.edit_text(DESCRIPTION_PROMPT, reply_markup=skip_keyboard(_DESCRIPTION_SKIP_CALLBACK))
    await callback.answer()


@router.message(AddMovieStates.waiting_for_description, HasPermission(Permission.MANAGE_MOVIES))
async def receive_description(message: Message, state: FSMContext, session: AsyncSession) -> None:
    description = (message.text or "").strip() or None
    await state.update_data(description=description)
    await _advance_to_categories(message, state, session)


@router.callback_query(
    AddMovieStates.waiting_for_description,
    F.data == _DESCRIPTION_SKIP_CALLBACK,
    HasPermission(Permission.MANAGE_MOVIES),
)
async def skip_description(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.update_data(description=None)
    if isinstance(callback.message, Message):
        await _advance_to_categories(callback.message, state, session)
    await callback.answer()


@router.callback_query(
    AddMovieStates.waiting_for_categories,
    F.data.startswith("madd:cat:"),
    HasPermission(Permission.MANAGE_MOVIES),
)
async def toggle_category(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if callback.data is None:
        await callback.answer()
        return

    category_id = int(callback.data.removeprefix("madd:cat:"))
    data = await state.get_data()
    selected = set(data.get("category_ids", []))
    if category_id in selected:
        selected.discard(category_id)
    else:
        selected.add(category_id)
    await state.update_data(category_ids=list(selected))

    categories = await CategoryRepository(session).list_active()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(
            reply_markup=category_picker_keyboard(
                categories, selected, _CATEGORY_TOGGLE_CALLBACK, _CATEGORY_DONE_CALLBACK
            )
        )
    await callback.answer()


@router.callback_query(
    AddMovieStates.waiting_for_categories,
    F.data == _CATEGORY_DONE_CALLBACK,
    HasPermission(Permission.MANAGE_MOVIES),
)
async def finish_categories(callback: CallbackQuery, state: FSMContext) -> None:
    if isinstance(callback.message, Message):
        await _prompt_premium(callback.message, state)
    await callback.answer()


@router.callback_query(
    AddMovieStates.waiting_for_premium,
    F.data.in_({_PREMIUM_YES_CALLBACK, _PREMIUM_NO_CALLBACK}),
    HasPermission(Permission.MANAGE_MOVIES),
)
async def receive_premium(callback: CallbackQuery, state: FSMContext) -> None:
    is_premium = callback.data == _PREMIUM_YES_CALLBACK
    await state.update_data(is_premium=is_premium)
    await state.set_state(AddMovieStates.waiting_for_confirm)

    data = await state.get_data()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            _confirm_text(data), reply_markup=confirm_keyboard(_CONFIRM_CALLBACK, _CANCEL_CALLBACK)
        )
    await callback.answer()


@router.callback_query(
    AddMovieStates.waiting_for_confirm, F.data == _CONFIRM_CALLBACK, HasPermission(Permission.MANAGE_MOVIES)
)
async def confirm_add(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    user = callback.from_user
    data = await state.get_data()

    admin = await AdminRepository(session).get_by_user_id(user.id)
    movie = await MovieService(session).create_movie(
        code=data["code"],
        title=data["title"],
        description=data.get("description"),
        file_id=data["file_id"],
        file_unique_id=data.get("file_unique_id"),
        storage_message_id=data.get("storage_message_id"),
        duration=data.get("duration"),
        file_size=data.get("file_size"),
        is_premium=bool(data.get("is_premium")),
        created_by=admin.id if admin is not None else None,
        category_ids=data.get("category_ids", []),
        quality=data.get("quality"),
        year=data.get("year"),
    )

    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action="movie_add",
        entity="movie",
        entity_id=movie.code,
    )

    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(f"✅ Kino qo'shildi. Kod: <code>{movie.code}</code>")
    await callback.answer()
    logger.info("movie_added", code=movie.code, admin_user_id=user.id)


@router.callback_query(
    AddMovieStates.waiting_for_confirm, F.data == _CANCEL_CALLBACK, HasPermission(Permission.MANAGE_MOVIES)
)
async def cancel_add(callback: CallbackQuery, state: FSMContext) -> None:
    # The video is already sitting in the storage channel from step 2
    # regardless — that's fine, an orphaned channel message with no DB row
    # is harmless, so there's nothing to roll back there.
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(CANCELLED_TEXT)
    await callback.answer()
