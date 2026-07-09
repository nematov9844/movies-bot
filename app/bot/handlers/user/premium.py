"""User-facing "⭐ Premium" flow: reply-menu button -> plan list -> purchase intent.

No real payment integration exists yet (``PaymentProvider`` in
``app/services/premium/payment_provider.py`` is an interface only) — tapping
a plan tells the user payments aren't automated and to contact support to
arrange one manually, and pings every active admin (``AdminService.
list_active``) so they know a purchase is pending. A DM failure to any one
admin (e.g. they blocked the bot) is caught and logged rather than allowed
to break the user-facing reply or skip notifying the rest.
"""

import html

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.premium import premium_plans_keyboard
from app.core.logger import get_logger
from app.database.models import PremiumPlan
from app.services.admin.admin_service import AdminService
from app.services.premium.premium_service import PremiumService
from app.services.settings.settings_service import SettingsService

router = Router(name="premium")
logger = get_logger(__name__)

PREMIUM_MENU_TEXT = "⭐ <b>Premium tariflar</b>\n\nKerakli tarifni tanlang:"
NO_PLANS_TEXT = "ℹ️ Hozircha faol premium tariflar mavjud emas."
PLAN_NOT_FOUND_TEXT = "❌ Tarif topilmadi."
DEFAULT_SUPPORT_USERNAME = "@support"
PAID_CONFIRMATION_TEXT = "✅ Rahmat! Administratorga to'lovingiz haqida qayta xabar berildi — tez orada tasdiqlanadi."

_CALLBACK_PREFIX = "premium:choose:"
_PAID_CALLBACK_PREFIX = "premium:paid:"


def _display_name(user: TgUser) -> str:
    """Renders the purchasing user's name for an admin DM (HTML parse mode) — escaped, since
    first/last name and username are all user-controlled Telegram profile fields."""
    name_parts = [part for part in (user.first_name, user.last_name) if part]
    full_name = " ".join(name_parts) if name_parts else (user.username or str(user.id))
    return f"{html.escape(full_name)} (ID: {user.id})"


def _purchase_intent_text(plan_name: str, support_username: str, payment_details: str | None) -> str:
    details_block = f"\n\n💳 To'lov uchun rekvizitlar:\n{payment_details}" if payment_details else ""
    return (
        f"✅ Siz <b>{plan_name}</b> tarifini tanladingiz.\n\n"
        "Hozircha to'lovlar avtomatik amalga oshirilmaydi. To'lovni amalga oshirgach, "
        "pastdagi \"✅ To'ladim\" tugmasini bosing yoki qo'llab-quvvatlash xizmatiga murojaat qiling: "
        f"{support_username}"
        f"{details_block}"
    )


def _admin_notify_text(user: TgUser, plan_name: str, *, already_paid: bool = False) -> str:
    if already_paid:
        return (
            f"💰 To'lov tasdiqlash so'rovi: {_display_name(user)} foydalanuvchi \"{plan_name}\" tarifi uchun "
            "to'lovni amalga oshirganini bildirdi. Tekshirib, tasdiqlang:"
        )
    return f"🔔 Premium so'rovi: {_display_name(user)} foydalanuvchi \"{plan_name}\" tarifini tanladi."


@router.message(F.text == "⭐ Premium")
async def show_premium_plans(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return

    plans = await PremiumService(session).list_active_plans()
    if not plans:
        await message.answer(NO_PLANS_TEXT)
        return

    await message.answer(PREMIUM_MENU_TEXT, reply_markup=premium_plans_keyboard(plans, _CALLBACK_PREFIX))
    logger.info("premium_plans_viewed", user_id=user.id)


@router.callback_query(F.data.startswith(_CALLBACK_PREFIX))
async def choose_premium_plan(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    user = callback.from_user
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    plan_id = int(callback.data.removeprefix(_CALLBACK_PREFIX))
    plan = await PremiumService(session).get_plan(plan_id)
    if plan is None:
        await callback.answer(PLAN_NOT_FOUND_TEXT, show_alert=True)
        return

    settings_service = SettingsService(session)
    support_username = await settings_service.get("support_username") or DEFAULT_SUPPORT_USERNAME
    payment_details = await settings_service.get("payment_details")
    await callback.message.edit_text(
        _purchase_intent_text(plan.name, support_username, payment_details),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="✅ To'ladim", callback_data=f"{_PAID_CALLBACK_PREFIX}{plan.id}")]]
        ),
    )
    await callback.answer()

    await _notify_active_admins(session, bot, user, plan)
    logger.info("premium_purchase_intent", user_id=user.id, plan_id=plan.id)


@router.callback_query(F.data.startswith(_PAID_CALLBACK_PREFIX))
async def mark_as_paid(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    """The user's side of the manual-payment loop: re-pings every admin with a
    more urgent, "please confirm" wording (still the same one-tap grant
    button) instead of leaving the original request as the only trace an
    admin might have missed or forgotten."""
    user = callback.from_user
    if callback.data is None or not isinstance(callback.message, Message):
        await callback.answer()
        return

    plan_id = int(callback.data.removeprefix(_PAID_CALLBACK_PREFIX))
    plan = await PremiumService(session).get_plan(plan_id)
    if plan is None:
        await callback.answer(PLAN_NOT_FOUND_TEXT, show_alert=True)
        return

    await callback.message.edit_text(PAID_CONFIRMATION_TEXT)
    await callback.answer()

    await _notify_active_admins(session, bot, user, plan, already_paid=True)
    logger.info("premium_marked_paid", user_id=user.id, plan_id=plan.id)


async def _notify_active_admins(
    session: AsyncSession, bot: Bot, user: TgUser, plan: PremiumPlan, *, already_paid: bool = False
) -> None:
    admins = await AdminService(session).list_active()
    text = _admin_notify_text(user, plan.name, already_paid=already_paid)
    # One tap straight into premium_grant.py's confirm screen — the admin
    # doesn't have to retype the user id or re-pick the plan from scratch,
    # both of which this notification already names.
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Premium berish", callback_data=f"prmg:quick:{user.id}:{plan.id}")]
        ]
    )
    for admin in admins:
        try:
            await bot.send_message(admin.user_id, text, reply_markup=keyboard)
        except TelegramAPIError as exc:
            logger.warning("premium_admin_notify_failed", admin_user_id=admin.user_id, error=str(exc))
