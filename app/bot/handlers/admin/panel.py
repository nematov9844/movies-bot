from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.filters import IsAdmin
from app.bot.keyboards.admin_panel import admin_panel_keyboard

router = Router(name="admin_panel")

PANEL_TEXT = "🛠 <b>Admin panel</b>\n\nKerakli bo'limni tanlang:"


@router.message(Command("panel"), IsAdmin())
async def cmd_panel(message: Message) -> None:
    """Entry point for the admin bot menu; any active admin can open it.

    Individual actions behind each button (e.g. movie add/edit/delete) are
    gated by their own ``HasPermission`` checks, since some are restricted
    to admin/owner rather than every active admin role.
    """
    await message.answer(PANEL_TEXT, reply_markup=admin_panel_keyboard())
