"""Admin bot Statistika screen: /panel -> "📊 Statistika".

Bugun/hafta/oy tabs share one render function. "Bugun" reads Phase 10's
live Redis counters (``StatsService.get_today``); "hafta"/"oy" sum the
``statistics`` table rows Phase 11's daily scheduler job flushes into.
Gated by ``HasPermission(Permission.VIEW_STATS)`` — moderator and above,
per the TZ role table (statistika ko'rish is the one moderator-visible
admin action alongside movie management).
"""

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import HasPermission
from app.bot.handlers.admin.panel import PANEL_TEXT
from app.bot.keyboards.admin_panel import admin_panel_keyboard
from app.bot.keyboards.stats import stats_period_keyboard
from app.core.permissions import Permission
from app.services.stats.stats_service import PeriodStats, StatsService

router = Router(name="admin_stats")

_PERIOD_LABELS = {"today": "Bugun", "week": "Hafta (7 kun)", "month": "Oy (30 kun)"}


async def _fetch(service: StatsService, period: str) -> PeriodStats:
    if period == "week":
        return await service.get_week()
    if period == "month":
        return await service.get_month()
    return await service.get_today()


def _format(period: str, stats: PeriodStats) -> str:
    lines = [
        f"📊 <b>Statistika — {_PERIOD_LABELS[period]}</b>",
        "",
        f"🆕 Yangi userlar: {stats.new_users}",
        f"👥 Aktiv userlar: {stats.active_users}",
        f"🎬 Yuborilgan kinolar: {stats.movies_sent}",
        f"⚠️ Xatolar: {stats.errors}",
        "",
        "🏆 <b>Top 10 kino:</b>",
    ]
    if stats.top_movies:
        lines += [
            f"{i}. {movie.title} (<code>{movie.code}</code>) — {movie.views} ko'rish"
            for i, movie in enumerate(stats.top_movies, start=1)
        ]
    else:
        lines.append("— ma'lumot yo'q —")

    lines += ["", "👤 <b>Top 10 user:</b>"]
    if stats.top_users:
        lines += [
            f"{i}. {user.label} — {user.views} ko'rish"
            for i, user in enumerate(stats.top_users, start=1)
        ]
    else:
        lines.append("— ma'lumot yo'q —")

    return "\n".join(lines)


async def _render(callback: CallbackQuery, session: AsyncSession, period: str) -> None:
    stats = await _fetch(StatsService(session), period)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(_format(period, stats), reply_markup=stats_period_keyboard(period))
    await callback.answer()


@router.callback_query(F.data == "stats_menu", HasPermission(Permission.VIEW_STATS))
async def open_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    await _render(callback, session, "today")


@router.callback_query(
    F.data.in_({"stats_period:today", "stats_period:week", "stats_period:month"}),
    HasPermission(Permission.VIEW_STATS),
)
async def switch_period(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.data is None:
        await callback.answer()
        return
    period = callback.data.removeprefix("stats_period:")
    await _render(callback, session, period)


@router.callback_query(F.data == "stats_panel", HasPermission(Permission.VIEW_STATS))
async def back_to_admin_panel(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(PANEL_TEXT, reply_markup=admin_panel_keyboard())
    await callback.answer()
