from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.movie_repository import MovieRepository


async def test_create_and_get(session: AsyncSession) -> None:
    repo = MovieRepository(session)
    movie = await repo.create(code="m1", title="Movie One", file_id="file1")

    fetched = await repo.get(movie.id)
    assert fetched is not None
    assert fetched.code == "m1"
    assert fetched.is_active is True
    assert fetched.view_count == 0


async def test_get_by_code(session: AsyncSession) -> None:
    repo = MovieRepository(session)
    await repo.create(code="m2", title="Movie Two", file_id="file2")

    found = await repo.get_by_code("m2")
    assert found is not None
    assert found.title == "Movie Two"
    assert await repo.get_by_code("does-not-exist") is None


async def test_update_soft_delete(session: AsyncSession) -> None:
    repo = MovieRepository(session)
    movie = await repo.create(code="m3", title="Movie Three", file_id="file3")

    updated = await repo.update(movie.id, is_active=False)
    assert updated is not None
    assert updated.is_active is False
    # Row still exists (soft delete), unlike a hard repo.delete().
    assert await repo.get(movie.id) is not None


async def test_count_with_filter(session: AsyncSession) -> None:
    repo = MovieRepository(session)
    await repo.create(code="m4", title="Premium Movie", file_id="file4", is_premium=True)
    await repo.create(code="m5", title="Free Movie", file_id="file5", is_premium=False)

    assert await repo.count(is_premium=True) == 1
    assert await repo.count(is_premium=False) == 1


async def test_get_by_file_unique_id(session: AsyncSession) -> None:
    repo = MovieRepository(session)
    await repo.create(code="m6", title="Movie Six", file_id="file6", file_unique_id="uniq-6")

    found = await repo.get_by_file_unique_id("uniq-6")
    assert found is not None
    assert found.code == "m6"
    assert await repo.get_by_file_unique_id("does-not-exist") is None
