"""Admin premium menu/grant wizard: /panel -> "⭐ Premium" -> "Premium berish".

Target user_id -> plan -> confirmation card -> grant, each step advancing
``GrantPremiumStates``. Gated by ``HasPermission(Permission.GRANT_PREMIUM)``
(admin+, per the TZ role table), mirroring ``channel_add.py``'s wizard
style.

``PremiumService.grant`` extends an existing active row instead of
stacking a second one — the confirmation card surfaces the user's current
expiry and the resulting new expiry up front precisely so the admin isn't
surprised by that behavior before confirming.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import HasPermission
from app.bot.handlers.admin.panel import PANEL_TEXT
from app.bot.keyboards.admin_panel import admin_panel_keyboard
from app.bot.keyboards.movie import confirm_keyboard
from app.bot.keyboards.premium import format_price, premium_menu_keyboard, premium_plans_keyboard
from app.bot.states.premium import GrantPremiumStates
from app.core.logger import get_logger
from app.core.permissions import Permission
from app.database.models import PremiumPlan, PremiumUser
from app.database.repositories.admin_repository import AdminRepository
from app.database.repositories.user_repository import UserRepository
from app.services.audit.audit_service import AuditService
from app.services.premium.premium_service import PremiumService

router = Router(name="admin_premium_grant")
logger = get_logger(__name__)

_TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

_PLAN_CALLBACK_PREFIX = "prmg:plan:"
_CONFIRM = "prmg:confirm"
_CANCEL = "prmg:cancel"

PREMIUM_MENU_TEXT = "⭐ <b>Premium</b>\n\nKerakli amalni tanlang:"
USER_ID_PROMPT = "🆔 Foydalanuvchining Telegram ID raqamini kiriting:"
USER_ID_INVALID_TEXT = "❌ Butun son kiriting:"
USER_NOT_FOUND_TEXT = "❌ Bu foydalanuvchi botdan hali foydalanmagan. Avval u botga /start yozishi kerak."
NO_PLANS_TEXT = "❌ Faol premium tariflar mavjud emas."
PLAN_PROMPT = "📦 Tarifni tanlang:"
PLAN_NOT_FOUND_TEXT = "❌ Tarif topilmadi."
CANCELLED_TEXT = "❌ Bekor qilindi."


def _humanize(dt: datetime) -> str:
    """Render a UTC-stored timestamp as ``dd.mm.yyyy`` in local (Tashkent) time."""
    return dt.astimezone(_TASHKENT_TZ).strftime("%d.%m.%Y")


def _confirm_text(target_user_id: int, plan: PremiumPlan, current: PremiumUser | None) -> str:
    if current is not None:
        new_expiry = current.expires_at + timedelta(days=plan.days)
        extension_note = (
            f"\n\nℹ️ Foydalanuvchida hozir ham faol premium bor (tugash sanasi: {_humanize(current.expires_at)}). "
            f"Yangi tarif qo'shiladi va muddat {_humanize(new_expiry)} sanasigacha uzaytiriladi."
        )
    else:
        new_expiry = datetime.now(UTC) + timedelta(days=plan.days)
        extension_note = ""
    return (
        "⭐ <b>Premium berishni tasdiqlang:</b>\n\n"
        f"🆔 Foydalanuvchi: <code>{target_user_id}</code>\n"
        f"📦 Tarif: {plan.name} ({plan.days} kun)\n"
        f"💰 Narx: {format_price(plan.price)} so'm\n"
        f"📅 Yangi tugash sanasi: {_humanize(new_expiry)}"
        f"{extension_note}"
    )


@router.callback_query(F.data == "premium_menu", HasPermission(Permission.GRANT_PREMIUM))
async def open_premium_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(PREMIUM_MENU_TEXT, reply_markup=premium_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "prm:panel", HasPermission(Permission.GRANT_PREMIUM))
async def back_to_admin_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(PANEL_TEXT, reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "premium_grant", HasPermission(Permission.GRANT_PREMIUM))
async def start_grant_premium(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(GrantPremiumStates.waiting_for_user_id)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(USER_ID_PROMPT)
    await callback.answer()


@router.message(GrantPremiumStates.waiting_for_user_id, HasPermission(Permission.GRANT_PREMIUM))
async def receive_target_user_id(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = (message.text or "").strip()
    try:
        target_user_id = int(raw)
    except ValueError:
        await message.answer(USER_ID_INVALID_TEXT)
        return

    target_user = await UserRepository(session).get(target_user_id)
    if target_user is None:
        await message.answer(USER_NOT_FOUND_TEXT)
        return

    plans = await PremiumService(session).list_active_plans()
    if not plans:
        await state.clear()
        await message.answer(NO_PLANS_TEXT)
        return

    await state.update_data(target_user_id=target_user_id)
    await state.set_state(GrantPremiumStates.waiting_for_plan)
    await message.answer(PLAN_PROMPT, reply_markup=premium_plans_keyboard(plans, _PLAN_CALLBACK_PREFIX))


@router.callback_query(
    GrantPremiumStates.waiting_for_plan,
    F.data.startswith(_PLAN_CALLBACK_PREFIX),
    HasPermission(Permission.GRANT_PREMIUM),
)
async def receive_plan(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    plan_id = int(callback.data.removeprefix(_PLAN_CALLBACK_PREFIX))
    premium_service = PremiumService(session)
    plan = await premium_service.get_plan(plan_id)
    if plan is None:
        await callback.answer(PLAN_NOT_FOUND_TEXT, show_alert=True)
        return

    data = await state.get_data()
    target_user_id: int = data["target_user_id"]
    current = await premium_service.get_active(target_user_id)

    await state.update_data(plan_id=plan_id)
    await state.set_state(GrantPremiumStates.waiting_for_confirm)
    await callback.message.edit_text(
        _confirm_text(target_user_id, plan, current), reply_markup=confirm_keyboard(_CONFIRM, _CANCEL)
    )
    await callback.answer()


@router.callback_query(
    GrantPremiumStates.waiting_for_confirm, F.data == _CONFIRM, HasPermission(Permission.GRANT_PREMIUM)
)
async def confirm_grant_premium(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    data = await state.get_data()
    target_user_id: int = data["target_user_id"]
    plan_id: int = data["plan_id"]

    premium_service = PremiumService(session)
    plan = await premium_service.get_plan(plan_id)
    if plan is None:
        await state.clear()
        await callback.message.edit_text(PLAN_NOT_FOUND_TEXT)
        await callback.answer()
        return

    admin = await AdminRepository(session).get_by_user_id(callback.from_user.id)
    premium_user = await premium_service.grant(
        user_id=target_user_id,
        plan_id=plan_id,
        granted_by=admin.id if admin is not None else None,
    )

    await AuditService(session).log(
        admin_id=admin.id if admin is not None else None,
        action="premium_grant",
        entity="premium_user",
        entity_id=str(target_user_id),
        payload={"plan_id": plan_id, "days": plan.days},
    )

    await state.clear()
    await callback.message.edit_text(
        f"✅ Premium berildi.\n\n🆔 Foydalanuvchi: <code>{target_user_id}</code>\n"
        f"📅 Amal qilish muddati: {_humanize(premium_user.expires_at)} gacha"
    )
    await callback.answer()
    logger.info(
        "premium_granted",
        target_user_id=target_user_id,
        plan_id=plan_id,
        admin_user_id=callback.from_user.id,
    )

    try:
        await bot.send_message(
            target_user_id,
            "🎉 Sizga premium tarif berildi!\n\n"
            f"📦 Tarif: {plan.name}\n"
            f"📅 Amal qilish muddati: {_humanize(premium_user.expires_at)} gacha",
        )
    except TelegramAPIError as exc:
        logger.warning("premium_grant_dm_failed", target_user_id=target_user_id, error=str(exc))


@router.callback_query(
    GrantPremiumStates.waiting_for_confirm, F.data == _CANCEL, HasPermission(Permission.GRANT_PREMIUM)
)
async def cancel_grant_premium(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(CANCELLED_TEXT)
    await callback.answer()
