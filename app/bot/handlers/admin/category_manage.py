"""Admin category management: /panel -> "🗂 Kategoriyalar".

Until now categories could only be *assigned* to a movie from the add/edit
wizard's picker (``movie_add.py``/``movie_manage.py``) — nothing created
one, so a fresh install had none and no way to add one. This is that missing
piece: create/toggle/delete, kept deliberately small (just a name) since
that's all ``Category`` has beyond its auto-derived slug.
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import HasPermission
from app.bot.handlers.admin.panel import PANEL_TEXT
from app.bot.keyboards.admin_panel import admin_panel_keyboard
from app.bot.keyboards.category import (
    category_card_keyboard,
    category_delete_confirm_keyboard,
    category_management_list_keyboard,
    category_menu_keyboard,
)
from app.bot.states.category import CategoryManageStates
from app.core.logger import get_logger
from app.core.permissions import Permission
from app.database.repositories.admin_repository import AdminRepository
from app.services.audit.audit_service import AuditService
from app.services.category.category_service import CategoryService

router = Router(name="admin_category_manage")
logger = get_logger(__name__)

CATEGORY_MENU_TEXT = "🗂 <b>Kategoriyalar</b>\n\nKino/serial qo'shishda tanlanadigan yorliqlar (masalan: Jangari, Komediya)."
NO_CATEGORIES_TEXT = "ℹ️ Hozircha kategoriyalar mavjud emas."
NAME_PROMPT = "🗂 Kategoriya nomini kiriting (masalan: Jangari):"
NAME_EMPTY_TEXT = "❌ Nom bo'sh bo'lishi mumkin emas. Qayta kiriting:"
NAME_TAKEN_TEXT = "❌ Bu nomli kategoriya allaqachon mavjud. Boshqa nom kiriting:"
NOT_FOUND_TEXT = "❌ Topilmadi."
DELETE_CONFIRM_TEXT = (
    "🗑 Rostdan ham ushbu kategoriyani butunlay o'chirmoqchimisiz?\n"
    "(Kinolardan ham bu yorliq olib tashlanadi, kinolarning o'zi o'chmaydi)"
)
DELETED_TEXT = "✅ O'chirildi."


def _category_card_text(name: str, is_active: bool) -> str:
    status = "🟢 Faol" if is_active else "🔴 Nofaol (yashirilgan)"
    return f"🗂 <b>{name}</b>\n\nHolat: {status}"


@router.callback_query(F.data == "category_menu", HasPermission(Permission.MANAGE_MOVIES))
async def open_category_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(CATEGORY_MENU_TEXT, reply_markup=category_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "cat:panel", HasPermission(Permission.MANAGE_MOVIES))
async def back_to_admin_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(PANEL_TEXT, reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "cat:list", HasPermission(Permission.MANAGE_MOVIES))
async def list_categories(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    categories = await CategoryService(session).list_all()
    if not categories:
        await callback.message.edit_text(NO_CATEGORIES_TEXT, reply_markup=category_menu_keyboard())
    else:
        await callback.message.edit_text(
            CATEGORY_MENU_TEXT, reply_markup=category_management_list_keyboard(categories)
        )
    await callback.answer()


@router.callback_query(F.data == "cat:new", HasPermission(Permission.MANAGE_MOVIES))
async def start_new_category(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CategoryManageStates.waiting_for_name)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(NAME_PROMPT)
    await callback.answer()


@router.message(CategoryManageStates.waiting_for_name, HasPermission(Permission.MANAGE_MOVIES))
async def receive_category_name(message: Message, state: FSMContext, session: AsyncSession) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(NAME_EMPTY_TEXT)
        return

    service = CategoryService(session)
    if await service.name_taken(name):
        await message.answer(NAME_TAKEN_TEXT)
        return

    category = await service.create_category(name)
    await state.clear()

    admin = await AdminRepository(session).get_by_user_id(message.from_user.id)
    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action="category_create",
        entity="category",
        entity_id=str(category.id),
    )

    await message.answer(
        _category_card_text(category.name, category.is_active), reply_markup=category_card_keyboard(category)
    )
    logger.info("category_added", category_id=category.id, name=category.name)


@router.callback_query(F.data.startswith("cat:view:"), HasPermission(Permission.MANAGE_MOVIES))
async def view_category(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    category_id = int(callback.data.removeprefix("cat:view:"))
    category = await CategoryService(session).get(category_id)
    if category is None:
        await callback.answer(NOT_FOUND_TEXT, show_alert=True)
        return

    await callback.message.edit_text(
        _category_card_text(category.name, category.is_active), reply_markup=category_card_keyboard(category)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat:toggle:"), HasPermission(Permission.MANAGE_MOVIES))
async def toggle_category(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    category_id = int(callback.data.removeprefix("cat:toggle:"))
    service = CategoryService(session)
    category = await service.toggle_active(category_id)
    if category is None:
        await callback.answer(NOT_FOUND_TEXT, show_alert=True)
        return

    admin = await AdminRepository(session).get_by_user_id(callback.from_user.id)
    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action="category_toggle",
        entity="category",
        entity_id=str(category_id),
        payload={"is_active": category.is_active},
    )

    await callback.message.edit_text(
        _category_card_text(category.name, category.is_active), reply_markup=category_card_keyboard(category)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat:delete:"), HasPermission(Permission.MANAGE_MOVIES))
async def confirm_delete_category(callback: CallbackQuery) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return
    category_id = callback.data.removeprefix("cat:delete:")
    await callback.message.edit_text(
        DELETE_CONFIRM_TEXT,
        reply_markup=category_delete_confirm_keyboard(
            f"cat:delete_confirm:{category_id}", f"cat:view:{category_id}"
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat:delete_confirm:"), HasPermission(Permission.MANAGE_MOVIES))
async def do_delete_category(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    category_id = int(callback.data.removeprefix("cat:delete_confirm:"))
    admin = await AdminRepository(session).get_by_user_id(callback.from_user.id)
    deleted = await CategoryService(session).delete_category(category_id)
    if not deleted:
        await callback.answer(NOT_FOUND_TEXT, show_alert=True)
        return

    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action="category_delete",
        entity="category",
        entity_id=str(category_id),
    )

    await callback.message.edit_text(DELETED_TEXT, reply_markup=category_menu_keyboard())
    await callback.answer()
    logger.info("category_deleted", category_id=category_id)
