from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.user_repository import UserRepository


async def test_create_and_get(session: AsyncSession) -> None:
    repo = UserRepository(session)
    user = await repo.create(id=1001, username="alice")

    fetched = await repo.get(1001)
    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.username == "alice"


async def test_get_missing_returns_none(session: AsyncSession) -> None:
    repo = UserRepository(session)
    assert await repo.get(999999) is None


async def test_update(session: AsyncSession) -> None:
    repo = UserRepository(session)
    await repo.create(id=1002, username="bob")

    updated = await repo.update(1002, username="bobby", is_blocked=True)
    assert updated is not None
    assert updated.username == "bobby"
    assert updated.is_blocked is True


async def test_delete(session: AsyncSession) -> None:
    repo = UserRepository(session)
    await repo.create(id=1003, username="carl")

    assert await repo.delete(1003) is True
    assert await repo.get(1003) is None
    assert await repo.delete(1003) is False


async def test_get_by_username(session: AsyncSession) -> None:
    repo = UserRepository(session)
    await repo.create(id=1004, username="dave")

    found = await repo.get_by_username("dave")
    assert found is not None
    assert found.id == 1004
    assert await repo.get_by_username("nobody") is None


async def test_upsert_inserts_new_row_and_flags_is_new(session: AsyncSession) -> None:
    repo = UserRepository(session)
    user, is_new = await repo.upsert(1005, username="erin", first_name="Erin")

    assert is_new is True
    assert user.username == "erin"


async def test_upsert_updates_existing_row_and_flags_not_new(session: AsyncSession) -> None:
    repo = UserRepository(session)
    await repo.upsert(1006, username="frank")

    user, is_new = await repo.upsert(1006, username="frankie")

    assert is_new is False
    assert user.username == "frankie"


async def test_search_by_numeric_id(session: AsyncSession) -> None:
    repo = UserRepository(session)
    await repo.create(id=1007, username="grace")
    await repo.create(id=1008, username="heidi")

    users, total = await repo.search("1007", limit=10, offset=0)
    assert total == 1
    assert users[0].id == 1007


async def test_search_by_username_substring(session: AsyncSession) -> None:
    repo = UserRepository(session)
    await repo.create(id=1009, username="ivan_the_great")
    await repo.create(id=1010, username="judy")

    users, total = await repo.search("the_great", limit=10, offset=0)
    assert total == 1
    assert users[0].id == 1009


async def test_search_negative_id_still_matches_exactly(session: AsyncSession) -> None:
    """Regression test: str.isdigit() rejects a leading '-', silently misrouting negative ids."""
    repo = UserRepository(session)
    await repo.create(id=-42, username="negative_user")

    users, total = await repo.search("-42", limit=10, offset=0)
    assert total == 1
    assert users[0].id == -42


async def test_list_broadcastable_ids_excludes_blocked_and_inactive(session: AsyncSession) -> None:
    repo = UserRepository(session)
    await repo.create(id=2001, is_blocked=False, is_active=True)
    await repo.create(id=2002, is_blocked=True, is_active=True)
    await repo.create(id=2003, is_blocked=False, is_active=False)

    ids = await repo.list_broadcastable_ids()
    assert 2001 in ids
    assert 2002 not in ids
    assert 2003 not in ids
