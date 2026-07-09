"""One-off maintenance script: finds series that are really the same show
saved under two different titles (a fansub caption used the full name once
and a nickname/hashtag elsewhere — e.g. "Maktab tomonidan tan olinmagan
iblislar hukumdori [Anos]" and "Anos") and merges them into one.

Two-stage safety, matching this codebase's "never guess" parser philosophy:
1. Cheap candidate generation — normalized substring/fuzzy match on titles.
2. Each candidate pair is confirmed by a local Ollama call before anything
   is touched; ``null``/low-confidence answers are skipped, not merged.

Merging never overwrites data:
- A season that doesn't already exist (by number) under the canonical series
  is simply reassigned.
- A season number that collides gets merged episode-by-episode; an
  episode_number collision within that is left in place (not moved, not
  deleted) and reported, exactly like a fresh ingest collision would be.
- A series/season only gets deleted once every one of its movies has been
  moved out (a partial merge leaves the remainder in place for review).

Usage:
    python -m scripts.merge_duplicate_series --dry-run
    python -m scripts.merge_duplicate_series
"""

import argparse
import asyncio
import difflib
import json
import re
from dataclasses import dataclass

import httpx
from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from app.database.models import Movie, Season, Series
from app.database.session import session_scope
from sqlalchemy import select

logger = get_logger(__name__)

_SIMILARITY_THRESHOLD = 0.6
_NORMALIZE_RE = re.compile(r"[^\w\s]", re.UNICODE)

# Deterministic safety net over the AI's distinct_season call: these words mark
# the end/a bonus of the SAME season (never a new one), but the model isn't
# fully consistent about that on its own (observed it call an "OVA" caption
# distinct_season=true once) — for a mistake this costly (renumbering real
# episodes into the wrong season), a keyword override beats trusting a single
# semantic judgment.
_SAME_SEASON_MARKER_RE = re.compile(
    r"\b(?:ova|final|yakuniy|tugadi|tugagan|tamom)\b", re.IGNORECASE
)


@dataclass
class SeriesInfo:
    id: int
    title: str
    episode_count: int


def _normalize(title: str) -> str:
    return _NORMALIZE_RE.sub(" ", title.lower()).strip()


# Second deterministic safety net: the model has been observed to confirm
# same_show=true for two titles sharing zero actual (specific) words — a
# wrong call here silently mixes two different shows' episodes together, so
# it isn't enough to just trust one semantic judgment on short/generic
# titles. Require *some* lexical grounding: a shared non-generic whole word,
# a substring relationship (nickname/truncation), or near-identical spelling
# (a typo of a single/short title) — anything less overrides the AI back to
# false. The stoplist mirrors the trope words/phrases called out in the AI
# prompt above — apostrophes normalize to spaces, so "tug'ilishi" tokenizes
# as "tug" + "ilishi"/"ilgan", not one word.
_LEXICAL_MATCH_RATIO = 0.85
_GENERIC_TROPE_WORDS = {
    "qayta", "tug", "ilishi", "ilgan", "tugilish", "boshqa", "dunyodan", "dunyoda", "dunyoga",
    "dunyo", "hukumdor", "hukumdori", "hukmdor", "maktab", "sarguzashtchi", "sarguzasht",
    "qahramon", "qahramoni", "qahramonlar", "qahramonning", "jamoasidan", "jamoasi", "final",
    "ova", "yakuniy", "tugadi", "tugagan", "tamom", "kelgan", "olib", "va", "bilan", "uchun",
    "ham", "bu", "shu", "sen", "men", "uni", "uning", "haqida", "hayoti", "qismi", "fasl",
}


def _content_words(normalized_title: str) -> set[str]:
    # Apostrophes normalize to spaces (see _normalize), so contractions like
    # "o'zim"/"o'z" split into a real word plus a stray 1-2 letter fragment
    # ("o", "zim") — those fragments must not count as a "shared word" match.
    return {w for w in normalized_title.split() if len(w) >= 3} - _GENERIC_TROPE_WORDS


def _lexically_plausible(title_a: str, title_b: str) -> bool:
    na, nb = _normalize(title_a), _normalize(title_b)
    # The substring check only counts if both sides have some non-generic
    # content word — "final" is trivially a substring of nearly every
    # "...#Final" caption's normalized text, but that's not evidence those
    # are the same show, just that both carry the same decorative suffix.
    # The ratio fallback below doesn't need this guard: it's comparing raw
    # character similarity (a typo like "Hukumdor"/"Hukmdor"), not semantics,
    # and "final" vs. a whole other title already scores far below threshold
    # on its own.
    has_content = bool(_content_words(na)) and bool(_content_words(nb))
    if has_content and (na in nb or nb in na):
        return True
    if _content_words(na) & _content_words(nb):
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= _LEXICAL_MATCH_RATIO


def _is_candidate_pair(a: str, b: str) -> bool:
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb or na == nb:
        return na == nb and na != ""
    if na in nb or nb in na:
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= _SIMILARITY_THRESHOLD


@dataclass
class MergeDecision:
    same_show: bool
    # True when title_b is a genuinely different season/part/cour/sequel of the
    # same show ("Season 2", "TV-2", "2nd Season") rather than just a
    # differently-formatted caption for the *same* episodes ("#Final", "OVA",
    # a typo) — decides whether _merge_series renumbers instead of merging
    # straight into the matching season number.
    distinct_season: bool = False


async def _confirm_same_show(client: httpx.AsyncClient, title_a: str, title_b: str) -> MergeDecision:
    system_prompt = (
        "You compare two Telegram-caption-derived titles from an anime/movie database.\n\n"
        "Step 1: decide whether they name the EXACT SAME specific show — e.g. a full title vs. "
        "its common nickname/abbreviation, the same title with/without a translated subtitle, or "
        "the same title with a decorative suffix like '#Final'/'OVA'/'Yakuniy qism' or a "
        "typo/spelling variant.\n\n"
        "Anime and isekai titles routinely reuse the same generic trope words AND WHOLE TROPE "
        "PHRASES — 'reincarnation' (qayta tug'ilishi), 'ruler'/'demon lord' (hukumdor), 'academy' "
        "(maktab), 'adventurer' (sarguzashtchi), 'hero party' (qahramonlar jamoasi), and — very "
        "commonly — the isekai opener 'from/in another world' (boshqa dunyodan/boshqa dunyoda/"
        "boshqa dunyoga) — across DOZENS of completely unrelated shows. A shared trope PREFIX "
        "phrase like 'Boshqa dunyodan kelgan ...' followed by a DIFFERENT specific noun (a "
        "different profession, character, or premise) means DIFFERENT shows, not the same one — "
        "e.g. 'Boshqa dunyodan kelgan oshpaz qahramon' (chef hero from another world) and "
        "'Boshqa Dunyodan Kelgan Yolg'onchi Sehrgar' (lying sorcerer from another world) are two "
        "unrelated titles that merely open with the same trope phrase.\n"
        "Only answer same_show=true when the titles share a specific, non-generic identifier: a "
        "proper noun/character name, or a distinctive multi-word phrase that is NOT just a common "
        "trope opener/theme, or one is clearly a truncation/nickname/typo of the other's specific "
        "wording. When two titles share only a generic trope prefix/theme and differ in their "
        "specific noun/subject, answer same_show=false.\n\n"
        "Step 2 (only if same_show is true): decide whether title B is just a differently-"
        "formatted caption for the SAME season's episodes, or whether it names a genuinely "
        "DIFFERENT, later season/part/cour of that same show.\n"
        "distinct_season=false (the common case) for: a decorative suffix like '#Final', "
        "'Yakuniy qism', 'Tugadi', 'OVA', 'Tugagan' — these describe the LAST EPISODE of the SAME "
        "season/batch, not a new one; a typo; a nickname; a bare punctuation/whitespace/emoji "
        "difference.\n"
        "distinct_season=true ONLY for an explicit, unambiguous new-season marker: 'Season 2', "
        "'2nd Season', 'TV-2', 'TV2', 'Part 2', 'II', or similar — where the title itself names a "
        "specific later installment, not just marks that a batch of posts finished.\n"
        "If in doubt, distinct_season=false.\n\n"
        "Respond with a single JSON object: "
        '{"same_show": true|false, "distinct_season": true|false, "confidence": 0.0-1.0}. '
        "distinct_season must be false whenever same_show is false. If unsure about either, "
        "prefer false rather than guessing."
    )
    try:
        response = await client.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/chat",
            json={
                "model": settings.ollama_model,
                "stream": False,
                "format": "json",
                # Without this, qwen3's extended "thinking" turns a ~1-2s call into
                # 40-60s for no accuracy benefit on a task this narrow — see the
                # matching note in caption_parser.py's _parse_with_ollama.
                "think": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f'Title A: "{title_a}"\nTitle B: "{title_b}"'},
                ],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content")
        parsed = json.loads(content) if content else {}
        same_show = bool(parsed.get("same_show")) and float(parsed.get("confidence", 0)) >= 0.7
        return MergeDecision(
            same_show=same_show, distinct_season=same_show and bool(parsed.get("distinct_season"))
        )
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("merge_confirm_failed", title_a=title_a, title_b=title_b, error=str(exc))
        return MergeDecision(same_show=False)


async def _merge_series(
    session, keep: Series, drop: Series, *, distinct_season: bool, dry_run: bool
) -> None:
    logger.info(
        "merging_series",
        keep=keep.title, keep_id=keep.id, drop=drop.title, drop_id=drop.id,
        distinct_season=distinct_season,
    )
    if dry_run:
        return

    keep_seasons = {s.number: s for s in (await session.execute(
        select(Season).where(Season.series_id == keep.id)
    )).scalars().all()}
    drop_seasons = (await session.execute(
        select(Season).where(Season.series_id == drop.id)
    )).scalars().all()

    # A confirmed *different* season/part of the same show must never collide
    # into an existing season by number coincidence (e.g. both defaulted to
    # season 1 because neither caption ever states an explicit season) —
    # renumber onto the next free slot instead of merging episode-by-episode.
    next_free_number = max(keep_seasons.keys(), default=0) + 1

    for drop_season in drop_seasons:
        if distinct_season:
            drop_season.series_id = keep.id
            drop_season.number = next_free_number
            keep_seasons[next_free_number] = drop_season
            next_free_number += 1
            continue

        target = keep_seasons.get(drop_season.number)
        if target is None:
            drop_season.series_id = keep.id
            keep_seasons[drop_season.number] = drop_season
            continue

        target_episodes = {m.episode_number: m for m in (await session.execute(
            select(Movie).where(Movie.season_id == target.id)
        )).scalars().all()}
        drop_movies = (await session.execute(
            select(Movie).where(Movie.season_id == drop_season.id)
        )).scalars().all()

        remaining = 0
        for movie in drop_movies:
            if movie.episode_number in target_episodes:
                logger.warning(
                    "merge_episode_collision_left_in_place",
                    series=drop.title, season=drop_season.number, episode=movie.episode_number,
                )
                remaining += 1
                continue
            movie.season_id = target.id

        if remaining == 0:
            await session.delete(drop_season)

    await session.flush()
    remaining_seasons = (await session.execute(
        select(Season).where(Season.series_id == drop.id)
    )).scalars().all()
    if not remaining_seasons:
        await session.delete(drop)
    else:
        logger.warning("series_partially_merged_left_in_place", title=drop.title, id=drop.id)


async def run(dry_run: bool) -> None:
    async with session_scope() as session:
        rows = (await session.execute(select(Series))).scalars().all()
        infos = []
        for s in rows:
            count = len((await session.execute(
                select(Movie.id).join(Season, Season.id == Movie.season_id).where(Season.series_id == s.id)
            )).all())
            infos.append(SeriesInfo(id=s.id, title=s.title, episode_count=count))

        candidates = [
            (a, b) for i, a in enumerate(infos) for b in infos[i + 1:] if _is_candidate_pair(a.title, b.title)
        ]
        logger.info("merge_candidates_found", count=len(candidates))

        if not candidates:
            return

        merged_ids: set[int] = set()
        client = httpx.AsyncClient()
        try:
            for a, b in candidates:
                if a.id in merged_ids or b.id in merged_ids:
                    continue
                decision = await _confirm_same_show(client, a.title, b.title)
                if decision.same_show and not _lexically_plausible(a.title, b.title):
                    decision.same_show = False
                    decision.distinct_season = False
                if decision.distinct_season and (
                    _SAME_SEASON_MARKER_RE.search(a.title) or _SAME_SEASON_MARKER_RE.search(b.title)
                ):
                    decision.distinct_season = False
                logger.info(
                    "merge_candidate_checked",
                    title_a=a.title, title_b=b.title,
                    confirmed=decision.same_show, distinct_season=decision.distinct_season,
                )
                if not decision.same_show:
                    continue

                keep_info, drop_info = (a, b) if a.episode_count >= b.episode_count else (b, a)
                keep = await session.get(Series, keep_info.id)
                drop = await session.get(Series, drop_info.id)
                if keep is None or drop is None:
                    continue
                await _merge_series(
                    session, keep, drop, distinct_season=decision.distinct_season, dry_run=dry_run
                )
                merged_ids.add(drop_info.id)
        finally:
            await client.aclose()


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="List merges that would happen, change nothing")
    args = parser.parse_args()

    if not settings.ollama_base_url:
        raise SystemExit("OLLAMA_BASE_URL is not set — this script needs it to confirm merges.")

    asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    main()
