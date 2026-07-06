"""One-off userbot script: forwards a channel's *entire existing history* of
video posts into the storage channel, so ``app.bot.handlers.admin.channel_ingest``
(``auto_ingest_from_storage_forward``) picks each one up and parses/saves it —
exactly the same pipeline new posts already go through.

Why this can't be a normal bot script
--------------------------------------
The Telegram Bot API only ever gives a bot updates for messages posted *after*
it joined a chat — there is no "fetch this channel's full history" call in
the Bot API, no matter how the bot is configured. Reading old messages
requires a real user session (MTProto, via Telethon here), which is why this
needs ``TELEGRAM_API_ID``/``TELEGRAM_API_HASH`` (from https://my.telegram.org)
instead of the bot token, and an interactive login the first time it runs.

The account you log in with must already be a member of (or otherwise able
to send into) the storage channel, and must have access to read the source
channel(s) — being their owner/admin, as in this project's case, covers both.

Usage
-----
    python -m scripts.backfill_channels JEKIANIME JEKIKINO NUR1Kkino
    python -m scripts.backfill_channels JEKIANIME --dry-run
    python -m scripts.backfill_channels JEKIANIME --limit 20

The first run prompts for your phone number and the login code Telegram
sends you (and a 2FA password if you have one enabled) — interactive, so run
this from a real terminal, not a background/headless process. It then saves
a local ``backfill.session`` file so every later run reuses it silently.

Safe to interrupt and re-run: the auto-ingest handler on the receiving end
already refuses duplicates (same ``file_unique_id``) and episode-number
clashes rather than double-writing them — this script itself does no
bookkeeping of what it's already forwarded.
"""

import argparse
import asyncio

from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from telethon import TelegramClient
from telethon.errors import FloodWaitError

logger = get_logger(__name__)

SESSION_NAME = "backfill"
# Telegram's own flood-control on forwardMessages is generous, but hammering
# it across potentially thousands of old posts risks a multi-minute
# FloodWaitError anyway — a small fixed pause between each one keeps this
# comfortably under that ceiling instead of relying solely on catching it.
PACE_SECONDS = 1.5


async def _backfill_channel(client: TelegramClient, source: str, *, limit: int | None, dry_run: bool) -> None:
    forwarded = 0
    skipped = 0

    # reverse=True: oldest first, so episode-number conflicts (if the same
    # show was posted out of order) surface against the *earlier* episode
    # already in the database, which is the more useful one to have kept.
    async for message in client.iter_messages(source, reverse=True, limit=limit):
        if message is None or message.video is None:
            skipped += 1
            continue

        if dry_run:
            forwarded += 1
            logger.info("backfill_dry_run_would_forward", source=source, message_id=message.id)
            continue

        while True:
            try:
                await client.forward_messages(settings.storage_channel_id, message)
                break
            except FloodWaitError as exc:
                logger.warning("backfill_flood_wait", source=source, seconds=exc.seconds)
                await asyncio.sleep(exc.seconds)

        forwarded += 1
        if forwarded % 25 == 0:
            logger.info("backfill_progress", source=source, forwarded=forwarded)
        await asyncio.sleep(PACE_SECONDS)

    logger.info("backfill_channel_done", source=source, forwarded=forwarded, skipped_non_video=skipped)


async def _run(sources: list[str], *, limit: int | None, dry_run: bool) -> None:
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise SystemExit(
            "TELEGRAM_API_ID / TELEGRAM_API_HASH are not set — get them from "
            "https://my.telegram.org and add them to .env first."
        )

    client = TelegramClient(SESSION_NAME, settings.telegram_api_id, settings.telegram_api_hash)
    async with client:
        me = await client.get_me()
        logger.info("backfill_logged_in", user_id=me.id, username=me.username)

        for source in sources:
            logger.info("backfill_channel_start", source=source, dry_run=dry_run)
            await _backfill_channel(client, source, limit=limit, dry_run=dry_run)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="+", help="Source channel usernames (no @), e.g. JEKIANIME")
    parser.add_argument("--limit", type=int, default=None, help="Cap messages read per channel (testing)")
    parser.add_argument("--dry-run", action="store_true", help="List what would be forwarded, forward nothing")
    args = parser.parse_args()

    asyncio.run(_run(args.sources, limit=args.limit, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
