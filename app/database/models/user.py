from __future__ import annotations

from datetime import datetime

from sqlalchemy import BIGINT, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DEFAULT_LANGUAGE
from app.database.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language: Mapped[str] = mapped_column(String(8), default=DEFAULT_LANGUAGE, server_default=DEFAULT_LANGUAGE)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    referrer_id: Mapped[int | None] = mapped_column(
        BIGINT, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    referrer: Mapped[User | None] = relationship(remote_side=[id])
