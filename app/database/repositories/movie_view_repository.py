from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import MovieView
from app.database.repositories.base import BaseRepository


class MovieViewRepository(BaseRepository[MovieView]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, MovieView)
