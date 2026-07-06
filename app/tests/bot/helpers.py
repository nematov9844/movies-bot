"""Shared helpers for bot handler tests: a mock ``Bot`` bound to a fake ``Message``.

Per the TZ: "aiogram uchun mock bot bilan" — ``AsyncMock(spec=Bot)`` is
awaitable when called (unlike ``create_autospec``, whose mocked ``__call__``
isn't async-aware), which is what ``Message.answer(...)``/``bot.send_video(...)``
need under the hood: aiogram's shortcut methods (``.answer()`` etc.) build a
``TelegramMethod`` request object and await ``self._bot(request)``, i.e. the
bound bot's ``__call__``.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from aiogram import Bot
from aiogram.types import Chat, Message, MessageOriginChannel, Video
from aiogram.types import User as TgUser


def make_bot() -> AsyncMock:
    return AsyncMock(spec=Bot)


def make_message(
    user_id: int,
    text: str,
    *,
    first_name: str = "Test",
    username: str | None = None,
    chat_id: int | None = None,
    bot: AsyncMock | None = None,
) -> tuple[Message, AsyncMock]:
    bot = bot or make_bot()
    user = TgUser(id=user_id, is_bot=False, first_name=first_name, username=username)
    chat = Chat(id=chat_id or user_id, type="private")
    message = Message.model_construct(
        message_id=1, date=datetime.now(UTC), chat=chat, from_user=user, text=text
    )
    return message.as_(bot), bot


def make_video(
    *, file_id: str = "video-file-id", file_unique_id: str = "video-unique-id"
) -> Video:
    return Video(file_id=file_id, file_unique_id=file_unique_id, width=1280, height=720, duration=120)


def make_channel_post(
    chat_id: int,
    *,
    chat_username: str | None = None,
    caption: str | None = None,
    video: Video | None = None,
    forwarded: bool = False,
    message_id: int = 1,
    bot: AsyncMock | None = None,
) -> tuple[Message, AsyncMock]:
    """A channel_post-shaped ``Message`` — no ``from_user`` (channel posts are attributed to
    the channel, not a user), optionally carrying a video and/or genuine forward metadata."""
    bot = bot or make_bot()
    chat = Chat(id=chat_id, type="channel", username=chat_username)
    forward_origin = (
        MessageOriginChannel(date=datetime.now(UTC), chat=chat, message_id=message_id)
        if forwarded
        else None
    )
    message = Message.model_construct(
        message_id=message_id,
        date=datetime.now(UTC),
        chat=chat,
        caption=caption,
        video=video,
        forward_origin=forward_origin,
    )
    return message.as_(bot), bot
