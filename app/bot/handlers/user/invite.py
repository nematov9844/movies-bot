from aiogram import Bot, F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import t
from app.core.logger import get_logger
from app.services.user.user_service import UserService

router = Router(name="invite")
logger = get_logger(__name__)


@router.message(F.text == "🎁 Do'stlarni taklif qilish")
async def show_invite_link(message: Message, session: AsyncSession, bot: Bot) -> None:
    user = message.from_user
    if user is None:
        return

    user_service = UserService(session)
    language = await user_service.get_language(user.id)
    referral_count = await user_service.get_referral_count(user.id)

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"

    await message.answer(t("invite.text", lang=language, link=link, count=referral_count))
    logger.info("invite_link_shown", user_id=user.id)
