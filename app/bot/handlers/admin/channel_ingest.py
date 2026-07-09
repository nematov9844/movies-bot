"""Auto-ingest: turns new video posts into saved database rows with zero
admin interaction, via two distinct triggers that share the same
parse-then-save tail.

1. ``auto_ingest_from_source_channel`` — a new post lands in one of
   ``settings.source_channels_list`` (the bot must be an admin there). It's
   relayed into the storage channel first — exactly like the interactive
   wizards already do — to get a storage-channel-scoped ``file_id``,
   matching this app's "videos only ever live in the storage channel"
   invariant. Covers everything posted *after* the bot joins that channel.

2. ``auto_ingest_from_storage_forward`` — a post lands directly in the
   storage channel as a genuine Telegram forward (``forward_origin`` set),
   as opposed to the bot's own ``send_video`` calls from
   ``movie_add.py``/``series_manage.py`` (which are freshly-authored posts,
   never forwards). This is how ``scripts/backfill_channels.py`` — a
   one-off userbot script that reads a source channel's *historical* posts,
   which the Bot API itself can never do — gets its forwarded videos
   ingested. ``forward_origin`` is the signal that tells them apart from
   the interactive wizards' own posts into that same channel, so this
   never double-processes a movie an admin just added by hand.

Neither path guesses: whatever ``CaptionIngestService.save`` can't
confidently resolve (missing title, ambiguous episode/season, an
episode-number collision, ...) DMs ``settings.owner_id`` with the reason
and where to find it, since nobody is watching this in real time to notice
a silently-dropped video.
"""

from aiogram import Bot, F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, MessageOriginChannel
from aiogram.types import Video as TgVideo
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.services.parser.caption_parser import CaptionParserService
from app.services.parser.ingest_service import CaptionIngestService

router = Router(name="admin_channel_ingest")
logger = get_logger(__name__)
_parser_service = CaptionParserService(
    settings.anthropic_api_key,
    settings.anthropic_model,
    ollama_base_url=settings.ollama_base_url,
    ollama_model=settings.ollama_model,
)

# Source channels whose uploads are known (an explicit call from the owner,
# not something inferrable from the data itself) to be better quality than
# whatever from an earlier backfill already occupies that episode slot — an
# episode-number collision against one of these overwrites the existing row
# instead of refusing it to a human. Matched as a substring since a forward's
# origin title is the channel's full display name (emoji, tagline and all),
# not just its handle.
_REPLACE_ON_COLLISION_SOURCES = ("anibro",)


def _prefers_replace_on_collision(source_channel_title: str | None) -> bool:
    if not source_channel_title:
        return False
    lowered = source_channel_title.lower()
    return any(name in lowered for name in _REPLACE_ON_COLLISION_SOURCES)


FAILURE_DM_TEXT = (
    "⚠️ Avto-parser bu videoni saqlay olmadi (sabab: {reason}).\n"
    "Manba: {source}, xabar ID: {message_id}\n"
    "Caption: {caption}\n"
    "Videoni ko'rib, kerakli tugmani bosing — qayta forward qilish shart emas:"
)


def _resume_keyboard(storage_message_id: int) -> InlineKeyboardMarkup:
    """Both callbacks carry the storage channel's own message id — the video
    is re-fetched from there by id (a forward, not a re-upload) when tapped,
    so the admin never has to go find and forward it manually."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎬 Film sifatida qo'shish", callback_data=f"resume:movie:{storage_message_id}"
                ),
                InlineKeyboardButton(
                    text="📺 Serial qismi sifatida", callback_data=f"resume:series:{storage_message_id}"
                ),
            ]
        ]
    )


def _is_configured_source_channel(message: Message) -> bool:
    username = (message.chat.username or "").lower()
    return bool(username) and username in settings.source_channels_list


@router.channel_post(F.video, _is_configured_source_channel)
async def auto_ingest_from_source_channel(message: Message, bot: Bot, session: AsyncSession) -> None:
    if message.video is None:
        return

    sent = await bot.send_video(
        chat_id=settings.storage_channel_id,
        video=message.video.file_id,
        caption=message.caption,
    )
    if sent.video is None:
        return

    await _parse_and_save(
        bot,
        session,
        caption=message.caption,
        video=sent.video,
        storage_message_id=sent.message_id,
        source=f"@{message.chat.username}",
        source_message_id=message.message_id,
        source_channel_title=message.chat.title,
    )


@router.channel_post(F.chat.id == settings.storage_channel_id, F.video, F.forward_origin)
async def auto_ingest_from_storage_forward(message: Message, bot: Bot, session: AsyncSession) -> None:
    if message.video is None:
        return

    origin = message.forward_origin
    source_channel_title = origin.chat.title if isinstance(origin, MessageOriginChannel) else None

    await _parse_and_save(
        bot,
        session,
        caption=message.caption,
        video=message.video,
        storage_message_id=message.message_id,
        source="backfill",
        source_message_id=message.message_id,
        source_channel_title=source_channel_title,
    )


async def _parse_and_save(
    bot: Bot,
    session: AsyncSession,
    *,
    caption: str | None,
    video: TgVideo,
    storage_message_id: int,
    source: str,
    source_message_id: int,
    source_channel_title: str | None = None,
) -> None:
    parsed = await _parser_service.parse(caption or "")
    result = await CaptionIngestService(session).save(
        parsed,
        file_id=video.file_id,
        file_unique_id=video.file_unique_id,
        storage_message_id=storage_message_id,
        duration=video.duration,
        file_size=video.file_size,
        source_label=source_channel_title,
        replace_on_collision=_prefers_replace_on_collision(source_channel_title),
    )

    if result.success:
        logger.info(
            "auto_ingest_saved",
            movie_code=result.movie.code if result.movie else None,
            source=source,
            confidence=parsed.confidence,
        )
        return

    logger.warning("auto_ingest_failed", reason=result.reason, source=source)
    # The video itself, not just a text notice — the admin has to actually
    # watch it to know what it even is before picking film-vs-episode.
    await bot.send_video(
        settings.owner_id,
        video=video.file_id,
        caption=FAILURE_DM_TEXT.format(
            reason=result.reason,
            source=source,
            message_id=source_message_id,
            caption=(caption or "(bo'sh)")[:200],
        ),
        reply_markup=_resume_keyboard(storage_message_id),
    )
