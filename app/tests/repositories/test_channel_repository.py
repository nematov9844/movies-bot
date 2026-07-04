from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.channel_repository import ChannelRepository


async def test_create_and_get(session: AsyncSession) -> None:
    repo = ChannelRepository(session)
    channel = await repo.create(channel_id=-1001111111111, title="Channel One")

    fetched = await repo.get(channel.id)
    assert fetched is not None
    assert fetched.channel_id == -1001111111111
    assert fetched.is_active is True


async def test_get_by_channel_id(session: AsyncSession) -> None:
    repo = ChannelRepository(session)
    await repo.create(channel_id=-1002222222222, title="Channel Two")

    found = await repo.get_by_channel_id(-1002222222222)
    assert found is not None
    assert found.title == "Channel Two"
    assert await repo.get_by_channel_id(-1009999999999) is None


async def test_list_active_excludes_disabled(session: AsyncSession) -> None:
    repo = ChannelRepository(session)
    await repo.create(channel_id=-1003333333333, title="Active", is_active=True)
    await repo.create(channel_id=-1004444444444, title="Disabled", is_active=False)

    active = await repo.list_active()
    titles = {c.title for c in active}
    assert "Active" in titles
    assert "Disabled" not in titles


async def test_delete(session: AsyncSession) -> None:
    repo = ChannelRepository(session)
    channel = await repo.create(channel_id=-1005555555555, title="ToDelete")

    assert await repo.delete(channel.id) is True
    assert await repo.get(channel.id) is None
