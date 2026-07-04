import pytest
from aiogram.filters import CommandObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.user.start import cmd_start
from app.bot.middlewares.user_upsert import UserUpsertMiddleware
from app.core.constants import REDIS_KEY_SETTING
from app.database.redis_client import get_redis
from app.database.repositories.user_repository import UserRepository
from app.services.settings.settings_service import SettingsService
from app.tests.bot.helpers import make_message

_TEST_USER_ID = 940001


@pytest.fixture(autouse=True)
async def _cleanup_welcome_text_cache():
    yield
    await get_redis().delete(REDIS_KEY_SETTING.format(key="welcome_text"))


async def test_user_upsert_middleware_creates_user_row(session: AsyncSession) -> None:
    """Per the TZ's UserUpsertMiddleware: cmd_start itself never touches the users table —
    that happens in the outer middleware that always runs first in production."""
    message, _bot = make_message(_TEST_USER_ID, "/start", first_name="Alice")

    async def handler(event, data):
        return None

    await UserUpsertMiddleware()(handler, message, {"session": session, "event_from_user": message.from_user})

    user = await UserRepository(session).get(_TEST_USER_ID)
    assert user is not None
    assert user.first_name == "Alice"


async def test_start_replies_with_a_message(session: AsyncSession) -> None:
    await UserRepository(session).create(id=_TEST_USER_ID, first_name="Bob")
    message, bot = make_message(_TEST_USER_ID, "/start", first_name="Bob")
    command = CommandObject(prefix="/", command="start", args=None)

    await cmd_start(message, command, session)

    assert bot.await_args is not None
    sent = bot.await_args.args[0]
    assert sent.text  # non-empty greeting text was sent


async def test_start_uses_welcome_text_setting_when_present(session: AsyncSession) -> None:
    await UserRepository(session).create(id=_TEST_USER_ID)
    await SettingsService(session).set("welcome_text", "Custom greeting!")
    await session.commit()
    message, bot = make_message(_TEST_USER_ID, "/start")
    command = CommandObject(prefix="/", command="start", args=None)

    await cmd_start(message, command, session)

    sent = bot.await_args.args[0]
    assert sent.text == "Custom greeting!"


async def test_start_records_valid_referral(session: AsyncSession) -> None:
    referrer_id = 940002
    await UserRepository(session).create(id=referrer_id)
    await UserRepository(session).create(id=_TEST_USER_ID)  # middleware already upserted them
    message, _bot = make_message(_TEST_USER_ID, f"/start ref_{referrer_id}")
    command = CommandObject(prefix="/", command="start", args=f"ref_{referrer_id}")

    await cmd_start(message, command, session)

    new_user = await UserRepository(session).get(_TEST_USER_ID)
    assert new_user is not None
    assert new_user.referrer_id == referrer_id


async def test_start_ignores_self_referral(session: AsyncSession) -> None:
    await UserRepository(session).create(id=_TEST_USER_ID)
    message, _bot = make_message(_TEST_USER_ID, f"/start ref_{_TEST_USER_ID}")
    command = CommandObject(prefix="/", command="start", args=f"ref_{_TEST_USER_ID}")

    await cmd_start(message, command, session)

    new_user = await UserRepository(session).get(_TEST_USER_ID)
    assert new_user is not None
    assert new_user.referrer_id is None
