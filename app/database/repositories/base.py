"""Generic CRUD repository shared by all per-model repositories.

Keeps every repository consistent: a thin wrapper around the ORM session
doing plain queries only (no business logic). Filters are simple keyword
equality — good enough for the lookups repositories need; anything more
elaborate belongs in a service.
"""

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base


class BaseRepository[ModelT: Base]:
    """Generic async CRUD repository for a single SQLAlchemy model."""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def _filtered(self, stmt: Select[Any], filters: dict[str, Any]) -> Select[Any]:
        for field, value in filters.items():
            stmt = stmt.where(getattr(self.model, field) == value)
        return stmt

    async def get(self, id: Any) -> ModelT | None:
        return await self.session.get(self.model, id)

    async def get_many(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
        **filters: Any,
    ) -> list[ModelT]:
        stmt = self._filtered(select(self.model), filters)
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **fields: Any) -> ModelT:
        obj = self.model(**fields)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, id: Any, **fields: Any) -> ModelT | None:
        obj = await self.get(id)
        if obj is None:
            return None
        for field, value in fields.items():
            setattr(obj, field, value)
        await self.session.flush()
        return obj

    async def delete(self, id: Any) -> bool:
        obj = await self.get(id)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        return True

    async def count(self, **filters: Any) -> int:
        stmt = self._filtered(select(func.count()).select_from(self.model), filters)
        result = await self.session.execute(stmt)
        return result.scalar_one()
