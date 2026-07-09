"""Admin bot Sozlamalar screen: /panel -> "⚙️ Sozlamalar" (Phase 12).

maintenance_mode/force_subscribe_enabled/premium_enabled toggle in place;
welcome_text/support_username go through a one-step FSM text prompt. Every
write goes through ``SettingsService.set``, which invalidates the setting's
cache entry immediately — per the TZ, "Restart TALAB QILINMAYDI", so the
change is live for the very next update, bot/API restart included.
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import HasPermission
from app.bot.handlers.admin.panel import PANEL_TEXT
from app.bot.keyboards.admin_panel import admin_panel_keyboard
from app.bot.keyboards.admin_settings import settings_menu_keyboard, settings_menu_text
from app.bot.states.admin_settings import EditSettingStates
from app.core.permissions import Permission
from app.services.settings.settings_service import SettingsService

router = Router(name="admin_settings")

_TOGGLE_KEYS = {"maintenance_mode", "force_subscribe_enabled", "premium_enabled"}
_EDIT_PROMPTS = {
    "welcome_text": "💬 Yangi salomlashuv matnini kiriting:",
    "support_username": "🆘 Yangi qo'llab-quvvatlash username'ini kiriting (masalan @support):",
    "payment_details": (
        "💳 To'lov rekvizitlarini kiriting (masalan: karta raqami, egasi, telefon) — "
        "bu foydalanuvchiga tarif tanlaganda ko'rsatiladi:"
    ),
}
VALUE_EMPTY_TEXT = "❌ Qiymat bo'sh bo'lishi mumkin emas. Qayta kiriting:"
SAVED_TEXT = "✅ Saqlandi."


async def _menu_content(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    service = SettingsService(session)
    maintenance = await service.get_bool("maintenance_mode", default=False)
    force_subscribe = await service.get_bool("force_subscribe_enabled", default=True)
    premium = await service.get_bool("premium_enabled", default=True)
    welcome_text = await service.get("welcome_text") or "—"
    support_username = await service.get("support_username") or "—"
    payment_details = await service.get("payment_details") or "— (hali kiritilmagan)"

    text = settings_menu_text(
        maintenance=maintenance,
        force_subscribe=force_subscribe,
        premium=premium,
        welcome_text=welcome_text,
        support_username=support_username,
        payment_details=payment_details,
    )
    keyboard = settings_menu_keyboard(
        maintenance=maintenance, force_subscribe=force_subscribe, premium=premium
    )
    return text, keyboard


@router.callback_query(F.data == "settings_menu", HasPermission(Permission.MANAGE_SETTINGS))
async def open_settings(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    text, keyboard = await _menu_content(session)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("stg:toggle:"), HasPermission(Permission.MANAGE_SETTINGS))
async def toggle_setting(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    key = callback.data.removeprefix("stg:toggle:")
    if key not in _TOGGLE_KEYS:
        await callback.answer()
        return

    service = SettingsService(session)
    current = await service.get_bool(key, default=key != "maintenance_mode")
    await service.set(key, "false" if current else "true")

    text, keyboard = await _menu_content(session)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer("✅ Yangilandi")


@router.callback_query(F.data.startswith("stg:edit:"), HasPermission(Permission.MANAGE_SETTINGS))
async def start_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    key = callback.data.removeprefix("stg:edit:")
    prompt = _EDIT_PROMPTS.get(key)
    if prompt is None:
        await callback.answer()
        return

    await state.set_state(EditSettingStates.waiting_for_value)
    await state.update_data(setting_key=key)
    await callback.message.edit_text(prompt)
    await callback.answer()


@router.message(EditSettingStates.waiting_for_value, HasPermission(Permission.MANAGE_SETTINGS))
async def receive_value(message: Message, state: FSMContext, session: AsyncSession) -> None:
    value = (message.text or "").strip()
    if not value:
        await message.answer(VALUE_EMPTY_TEXT)
        return

    data = await state.get_data()
    key: str = data["setting_key"]
    await SettingsService(session).set(key, value)
    await state.clear()

    text, keyboard = await _menu_content(session)
    await message.answer(SAVED_TEXT)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "stg:panel", HasPermission(Permission.MANAGE_SETTINGS))
async def back_to_admin_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(PANEL_TEXT, reply_markup=admin_panel_keyboard())
    await callback.answer()
