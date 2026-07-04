from datetime import date

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_users: int
    new_users_today: int
    total_movies: int
    active_premium_count: int
    premium_conversion_percent: float


class DailyPoint(BaseModel):
    date: date
    new_users: int
    active_users: int
    movies_sent: int


class DashboardResponse(BaseModel):
    summary: DashboardSummary
    daily: list[DailyPoint]
