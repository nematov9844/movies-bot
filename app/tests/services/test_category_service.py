from sqlalchemy.ext.asyncio import AsyncSession

from app.services.category.category_service import CategoryService


async def test_create_category_generates_slug(session: AsyncSession) -> None:
    service = CategoryService(session)
    category = await service.create_category("Jangari Kino!")
    assert category.name == "Jangari Kino!"
    assert category.slug == "jangari-kino"


async def test_name_taken(session: AsyncSession) -> None:
    service = CategoryService(session)
    await service.create_category("Komediya")

    assert await service.name_taken("Komediya") is True
    assert await service.name_taken("Drama") is False


async def test_name_taken_excludes_self(session: AsyncSession) -> None:
    service = CategoryService(session)
    category = await service.create_category("Drama")

    assert await service.name_taken("Drama", exclude_category_id=category.id) is False


async def test_update_category_renames_and_reslugifies(session: AsyncSession) -> None:
    service = CategoryService(session)
    category = await service.create_category("Jangari")

    updated = await service.update_category(category.id, name="Jangari Film")
    assert updated is not None
    assert updated.name == "Jangari Film"
    assert updated.slug == "jangari-film"


async def test_toggle_active(session: AsyncSession) -> None:
    service = CategoryService(session)
    category = await service.create_category("Trillar")
    assert category.is_active is True

    toggled = await service.toggle_active(category.id)
    assert toggled is not None
    assert toggled.is_active is False

    toggled_again = await service.toggle_active(category.id)
    assert toggled_again is not None
    assert toggled_again.is_active is True


async def test_list_all_vs_list_active(session: AsyncSession) -> None:
    service = CategoryService(session)
    active = await service.create_category("Faol")
    inactive = await service.create_category("Nofaol")
    await service.toggle_active(inactive.id)

    all_categories = await service.list_all()
    assert {c.id for c in all_categories} >= {active.id, inactive.id}

    active_only = await service.list_active()
    active_ids = {c.id for c in active_only}
    assert active.id in active_ids
    assert inactive.id not in active_ids


async def test_delete_category(session: AsyncSession) -> None:
    service = CategoryService(session)
    category = await service.create_category("O'chiriladigan")

    deleted = await service.delete_category(category.id)
    assert deleted is True
    assert await service.get(category.id) is None

    assert await service.delete_category(999999) is False
