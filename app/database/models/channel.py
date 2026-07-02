from datetime import datetime, time

from sqlalchemy import BIGINT, Boolean, DateTime, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Channel(Base, TimestampMixin):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(BIGINT, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    invite_link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expire_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    daily_start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    daily_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    join_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_joins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
