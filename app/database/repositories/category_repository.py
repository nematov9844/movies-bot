from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Category
from app.database.repositories.base import BaseRepository


class CategoryRepository(BaseRepository[Category]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Category)
