"""Idempotent baseline data seeder for Phase 2.

Seeds the minimum data the platform needs to be operable out of the box:

- ``admins``: the Telegram user configured as ``OWNER_ID`` gets an ``owner``
  admin row (a placeholder ``users`` row is created for them first, since
  ``admins.user_id`` FKs to ``users.id`` and they may not have pressed
  /start yet) — delegated to ``AdminService.ensure_owner_seeded``, the same
  method the bot and API call on every process startup (Phase 4), so this
  script no longer duplicates that logic.
- ``premium_plans``: the four standard subscription lengths.
- ``settings``: baseline runtime configuration keys read by the bot/API.

Safe to run multiple times — every insert is guarded so re-running never
raises a duplicate-key error or creates duplicate rows.

Usage:
    python -m scripts.seed
    docker compose exec api python -m scripts.seed
"""

import asyncio

from app.core.constants import SettingType
from app.core.logger import get_logger, setup_logging
from app.database.models import PremiumPlan, Setting
from app.database.session import async_session_factory, engine
from app.services.admin.admin_service import AdminService
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = get_logger(__name__)

PREMIUM_PLANS: list[dict[str, object]] = [
    {"name": "7 kunlik", "days": 7, "price": 15_000},
    {"name": "1 oylik", "days": 30, "price": 50_000},
    {"name": "3 oylik", "days": 90, "price": 130_000},
    {"name": "1 yillik", "days": 365, "price": 450_000},
]

SETTINGS: list[dict[str, str]] = [
    {
        "key": "bot_name",
        "value": "Movie Platform",
        "type": SettingType.STR.value,
        "description": "Botning nomi",
    },
    {
        "key": "maintenance_mode",
        "value": "false",
        "type": SettingType.BOOL.value,
        "description": "Texnik xizmat rejimi (yoqilganda bot foydalanuvchilarga vaqtincha yopiladi)",
    },
    {
        "key": "welcome_text",
        "value": (
            "Assalomu alaykum! 🎬 Movie Platform botiga xush kelibsiz.\n"
            "Kino kodini yuboring va filmni darhol oling."
        ),
        "type": SettingType.STR.value,
        "description": "/start buyrug'ida yuboriladigan salomlashuv matni",
    },
    {
        "key": "support_username",
        "value": "@support",
        "type": SettingType.STR.value,
        "description": "Qo'llab-quvvatlash xizmati Telegram username (adminpanelda o'zgartiriladi)",
    },
    {
        "key": "force_subscribe_enabled",
        "value": "true",
        "type": SettingType.BOOL.value,
        "description": "Majburiy obuna (force-subscribe) tekshiruvini yoqish/o'chirish",
    },
    {
        "key": "premium_enabled",
        "value": "true",
        "type": SettingType.BOOL.value,
        "description": "Premium obuna tizimini yoqish/o'chirish",
    },
    {
        "key": "ads_enabled",
        "value": "true",
        "type": SettingType.BOOL.value,
        "description": "Reklama ko'rsatishni yoqish/o'chirish",
    },
    {
        "key": "movie_not_found_text",
        "value": "Kechirasiz, bunday kodli kino topilmadi.",
        "type": SettingType.STR.value,
        "description": "Kino kodi bo'yicha hech narsa topilmaganda ko'rsatiladigan matn",
    },
    {
        "key": "admin_ip_whitelist",
        "value": "",
        "type": SettingType.STR.value,
        "description": (
            "Admin API'ga ruxsat etilgan IP manzillar, vergul bilan ajratilgan "
            "(bo'sh bo'lsa tekshiruv o'chirilgan)"
        ),
    },
]


async def seed_premium_plans(session) -> None:
    """Insert the standard premium plans if they don't already exist by name."""
    for plan in PREMIUM_PLANS:
        exists = await session.scalar(
            select(PremiumPlan.id).where(PremiumPlan.name == plan["name"])
        )
        if exists is not None:
            continue
        session.add(PremiumPlan(**plan, is_active=True))
        logger.info("seed_premium_plan_created", name=plan["name"])


async def seed_settings(session) -> None:
    """Insert baseline settings rows, leaving already-configured keys untouched."""
    for row in SETTINGS:
        stmt = pg_insert(Setting).values(**row).on_conflict_do_nothing(index_elements=[Setting.key])
        result = await session.execute(stmt)
        if result.rowcount:
            logger.info("seed_setting_created", key=row["key"])


async def seed() -> None:
    async with async_session_factory() as session:
        try:
            await AdminService(session).ensure_owner_seeded()
            await seed_premium_plans(session)
            await seed_settings(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await engine.dispose()
    logger.info("seed_completed")


def main() -> None:
    setup_logging()
    asyncio.run(seed())


if __name__ == "__main__":
    main()
