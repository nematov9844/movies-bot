from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Referral
from app.database.repositories.base import BaseRepository


class ReferralRepository(BaseRepository[Referral]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Referral)

    async def create_if_absent(self, *, referrer_id: int, referred_id: int) -> bool:
        """Insert a referral row unless ``referred_id`` already has one.

        Uses ``INSERT ... ON CONFLICT DO NOTHING`` on the unique
        ``referred_id`` column so concurrent/duplicate referral attempts for
        the same user converge safely at the database level instead of
        raising ``IntegrityError``. Returns whether a row was inserted.
        """
        stmt = (
            pg_insert(Referral)
            .values(referrer_id=referrer_id, referred_id=referred_id)
            .on_conflict_do_nothing(index_elements=[Referral.referred_id])
            .returning(Referral.id)
        )
        result = await self.session.execute(stmt)
        return result.first() is not None
