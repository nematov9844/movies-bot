from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import t
from app.core.logger import get_logger
from app.services.user.user_service import UserService

router = Router(name="profile")
logger = get_logger(__name__)

_TASHKENT_TZ = ZoneInfo("Asia/Tashkent")


def _humanize(dt: datetime) -> str:
    """Render a UTC-stored timestamp as ``dd.mm.yyyy`` in local (Tashkent) time."""
    return dt.astimezone(_TASHKENT_TZ).strftime("%d.%m.%Y")


@router.message(F.text == "👤 Profil")
async def show_profile(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return

    profile = await UserService(session).get_profile(user.id)
    if profile is None:
        return

    if profile.premium_active and profile.premium_expires_at is not None:
        premium_status = t(
            "profile.premium_active",
            lang=profile.language,
            expires_at=_humanize(profile.premium_expires_at),
        )
    else:
        premium_status = t("profile.premium_none", lang=profile.language)

    await message.answer(
        t(
            "profile",
            lang=profile.language,
            telegram_id=profile.telegram_id,
            full_name=profile.full_name,
            premium_status=premium_status,
            movies_watched=profile.movies_watched,
            referral_count=profile.referral_count,
        )
    )
    logger.info("profile_viewed", user_id=user.id)
