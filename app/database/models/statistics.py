from datetime import date

from sqlalchemy import Date, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Statistics(Base, TimestampMixin):
    __tablename__ = "statistics"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    new_users: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    active_users: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    movies_sent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    errors: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    api_requests: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
