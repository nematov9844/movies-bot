import re

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.main_menu import main_menu_keyboard
from app.core.i18n import t
from app.core.logger import get_logger
from app.services.user.user_service import UserService

router = Router(name="start")
logger = get_logger(__name__)

_REFERRAL_PAYLOAD_RE = re.compile(r"^ref_(\d+)$")


def _parse_referrer_id(payload: str | None) -> int | None:
    """Extract the referrer's user_id from a ``ref_<user_id>`` deep-link payload."""
    if not payload:
        return None
    match = _REFERRAL_PAYLOAD_RE.match(payload)
    if match is None:
        return None
    return int(match.group(1))


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return

    user_service = UserService(session)

    referrer_id = _parse_referrer_id(command.args)
    if referrer_id is not None:
        recorded = await user_service.record_referral(referred_id=user.id, referrer_id=referrer_id)
        if recorded:
            logger.info("referral_recorded", referrer_id=referrer_id, referred_id=user.id)
        else:
            # Self-referral, unknown referrer, or already-referred user — all
            # expected user behavior, not an error worth an error-level log.
            logger.info("referral_skipped", referrer_id=referrer_id, referred_id=user.id)

    language = await user_service.get_language(user.id)
    await message.answer(
        t("welcome", lang=language, name=user.first_name or "foydalanuvchi"),
        reply_markup=main_menu_keyboard(),
    )
    logger.info("start_command", user_id=user.id)
