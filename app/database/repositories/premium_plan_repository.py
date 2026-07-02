from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import PremiumPlan
from app.database.repositories.base import BaseRepository


class PremiumPlanRepository(BaseRepository[PremiumPlan]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, PremiumPlan)
