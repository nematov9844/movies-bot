from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.keyboards.main_menu import main_menu_keyboard
from app.core.logger import get_logger

router = Router(name="start")
logger = get_logger(__name__)

WELCOME_TEXT = (
    "Assalomu alaykum, {name}! 👋\n\n"
    "Bu bot orqali kinolarni topishingiz mumkin. "
    "Kino kodini yuboring yoki quyidagi menyudan foydalaning."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    name = message.from_user.first_name if message.from_user else "foydalanuvchi"
    await message.answer(
        WELCOME_TEXT.format(name=name),
        reply_markup=main_menu_keyboard(),
    )
    logger.info("start_command", user_id=message.from_user.id if message.from_user else None)
