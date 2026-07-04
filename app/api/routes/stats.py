"""Web panel Dashboard page: summary cards + a 30-day chart series."""

from fastapi import APIRouter

from app.api.dependencies.auth import CurrentAdmin
from app.api.dependencies.db import DbSession
from app.api.schemas.stats import DailyPoint, DashboardResponse, DashboardSummary
from app.core.constants import STATS_MONTH_DAYS
from app.services.stats.stats_service import StatsService

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=DashboardResponse)
async def get_dashboard(session: DbSession, _current_admin: CurrentAdmin) -> DashboardResponse:
    data = await StatsService(session).get_dashboard(STATS_MONTH_DAYS)
    conversion = (data.active_premium_count / data.total_users * 100) if data.total_users else 0.0

    return DashboardResponse(
        summary=DashboardSummary(
            total_users=data.total_users,
            new_users_today=data.new_users_today,
            total_movies=data.total_movies,
            active_premium_count=data.active_premium_count,
            premium_conversion_percent=round(conversion, 2),
        ),
        daily=[
            DailyPoint(
                date=d.day, new_users=d.new_users, active_users=d.active_users, movies_sent=d.movies_sent
            )
            for d in data.daily
        ],
    )
