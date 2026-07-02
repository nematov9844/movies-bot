from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Referral
from app.database.repositories.base import BaseRepository


class ReferralRepository(BaseRepository[Referral]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Referral)
