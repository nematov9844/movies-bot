"""Business logic for movie categories (tags like "Jangari"/"Komediya" assigned during
add/edit-movie) — until now these could only be *assigned* from existing rows; nothing
created them, so a fresh install had no categories and no way to add one."""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Category
from app.database.repositories.category_repository import CategoryRepository

_SLUG_INVALID_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    return _SLUG_INVALID_RE.sub("-", name.lower()).strip("-") or "category"


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = CategoryRepository(session)

    async def create_category(self, name: str) -> Category:
        return await self._repo.create(name=name, slug=_slugify(name), is_active=True)

    async def name_taken(self, name: str, *, exclude_category_id: int | None = None) -> bool:
        existing = await self._repo.get_by_name(name)
        return existing is not None and existing.id != exclude_category_id

    async def list_all(self) -> list[Category]:
        return await self._repo.get_many()

    async def list_active(self) -> list[Category]:
        return await self._repo.list_active()

    async def get(self, category_id: int) -> Category | None:
        return await self._repo.get(category_id)

    async def update_category(
        self, category_id: int, *, name: str | None = None, is_active: bool | None = None
    ) -> Category | None:
        fields: dict[str, object] = {}
        if name is not None:
            fields["name"] = name
            fields["slug"] = _slugify(name)
        if is_active is not None:
            fields["is_active"] = is_active
        if not fields:
            return await self._repo.get(category_id)
        return await self._repo.update(category_id, **fields)

    async def toggle_active(self, category_id: int) -> Category | None:
        category = await self._repo.get(category_id)
        if category is None:
            return None
        return await self._repo.update(category_id, is_active=not category.is_active)

    async def delete_category(self, category_id: int) -> bool:
        """Hard delete — cascades to ``movie_categories`` (removes the tag from any movie)."""
        return await self._repo.delete(category_id)
