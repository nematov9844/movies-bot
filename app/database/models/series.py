from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin


class Series(Base, TimestampMixin):
    """A show/anime that groups seasons, e.g. "Naruto" — searched by title in the bot."""

    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    seasons: Mapped[list["Season"]] = relationship(
        back_populates="series", order_by="Season.number", cascade="all, delete-orphan"
    )


class Season(Base, TimestampMixin):
    """One "fasl" of a series — episodes (``Movie`` rows) attach to this via ``Movie.season_id``."""

    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("series_id", "number", name="uq_seasons_series_id_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    series: Mapped[Series] = relationship(back_populates="seasons")
