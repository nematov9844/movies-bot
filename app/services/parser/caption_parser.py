"""AI-assisted parser: turns an unstructured Telegram post (caption + optional
filename) into the structured fields ``series_manage.py``'s bulk-forward flow
and the standalone add-movie wizard need — ``title``/``season_number``/
``episode_number``/``quality``/``year``.

Two-stage pipeline, in this order:

1. **Deterministic** (``extract_deterministic``): plain regex over the known,
   observed post shapes (``S01E05``, ``Episode 5``, ``Episode Five``,
   ``5-qism``, ``N-fasl``/``Season N``, quality tags, a parenthesized year) —
   pure, no I/O, always runs, and is exhaustively unit-tested on its own.
2. **AI fallback** (``CaptionParserService.parse``): only invoked for fields
   the regex stage left ``None``, and only if an Anthropic API key is
   configured. The model is instructed to return ``null`` for anything it
   isn't confident about rather than guess — this is a fallback for messier
   phrasing, not a replacement for the deterministic stage, which always
   wins on any field it *did* resolve.

Every non-null field in the final ``ParsedCaption`` is tagged in ``sources``
with whether a regex or the AI produced it, so a caller (admin review UI,
audit log) can tell a confident deterministic hit from a model guess before
trusting it into the database — this parser never writes to the DB itself,
it only produces a structured, inspectable result.
"""

import json
import re
from dataclasses import dataclass, field

import httpx

from app.core.logger import get_logger

logger = get_logger(__name__)

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_API_VERSION = "2023-06-01"
_AI_TIMEOUT_SECONDS = 15.0

_FIELDS = ("title", "season_number", "episode_number", "quality", "year")

_ONE_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
_TEN_WORDS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}

# Ordered by specificity — checked first-match-wins, so e.g. "2160p" must be
# tried before a bare "4K" pattern could otherwise partially shadow it.
_QUALITY_TAGS = ("2160p", "1080p", "720p", "480p", "360p", "4K", "UHD", "FHD", "HD", "CAM")

# A candidate title line that (after stripping emoji/symbols) is just generic
# promotional filler, not an actual title — the deterministic stage declines
# rather than confidently returning "New Episode" as if it were a real name.
_NON_TITLE_PHRASES = {
    "new episode", "new episodes", "yangi qism", "yangi qismlar", "hot", "trending",
    "new", "yangi", "premiere", "exclusive",
}

_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0001f1e6-\U0001f1ff"
    "\ufe0f"  # variation selector-16 (emoji presentation)
    "\u200d"  # zero-width joiner (combined emoji)
    "]+",
    flags=re.UNICODE,
)

_SXXEXX_RE = re.compile(r"\bS(\d{1,3})[\s._-]*E(\d{1,4})\b", re.IGNORECASE)
_EPISODE_NUM_RE = re.compile(r"\b(?:Episode|Ep)\.?\s*#?\s*(\d{1,4})\b", re.IGNORECASE)
# The optional second word must not itself be another marker's keyword —
# without the lookahead, "Season One Episode Five" greedily captures
# "One Episode" as the season's word-number phrase (word_to_number then
# correctly fails on it, so season_number silently ends up None instead
# of 1) instead of stopping at the "Season"/"Episode" boundary.
_RESERVED_MARKER_WORDS = r"Episode|Ep|Season|Qism|Fasl"
_EPISODE_WORD_RE = re.compile(
    rf"\b(?:Episode|Ep)\.?\s+([A-Za-z]+(?:[\s-]+(?!(?:{_RESERVED_MARKER_WORDS})\b)[A-Za-z]+)?)\b",
    re.IGNORECASE,
)
_QISM_NUM_RE = re.compile(r"\b(\d{1,4})[\s-]*qism\b", re.IGNORECASE)
_QISM_NUM_RE_ALT = re.compile(r"\bqism\s*#?\s*(\d{1,4})\b", re.IGNORECASE)
_SEASON_NUM_RE = re.compile(r"\bSeason\s*#?\s*(\d{1,3})\b", re.IGNORECASE)
_FASL_NUM_RE = re.compile(r"\b(\d{1,3})[\s-]*fasl\b", re.IGNORECASE)
_FASL_NUM_RE_ALT = re.compile(r"\bfasl\s*#?\s*(\d{1,3})\b", re.IGNORECASE)
_SEASON_WORD_RE = re.compile(
    rf"\bSeason\s+([A-Za-z]+(?:[\s-]+(?!(?:{_RESERVED_MARKER_WORDS})\b)[A-Za-z]+)?)\b",
    re.IGNORECASE,
)
_YEAR_PAREN_RE = re.compile(r"\((\d{4})\)")
_YEAR_BARE_RE = re.compile(r"\b(19\d{2}|20[0-3]\d)\b")

# Confidence weighting: a regex hit is a deterministic pattern match: full
# weight. An AI-fallback hit is a model guess on messy text: partial weight,
# so a caption resolved entirely by the AI stage reads as "worth a human
# glance" rather than as trustworthy as a clean regex match.
_SOURCE_WEIGHT = {"regex": 1.0, "ai": 0.6}


def _word_to_number(text: str) -> int | None:
    tokens = re.findall(r"[a-z]+", text.lower())
    if len(tokens) == 1:
        word = tokens[0]
        return _ONE_WORDS.get(word, _TEN_WORDS.get(word))
    if len(tokens) == 2 and tokens[0] in _TEN_WORDS and tokens[1] in _ONE_WORDS and _ONE_WORDS[tokens[1]] < 10:
        return _TEN_WORDS[tokens[0]] + _ONE_WORDS[tokens[1]]
    return None


@dataclass
class ParsedCaption:
    title: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    quality: str | None = None
    year: int | None = None
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def is_episode(self) -> bool:
        """True if this looks like one episode of a series rather than a standalone movie."""
        return self.episode_number is not None

    @property
    def missing_fields(self) -> list[str]:
        return [f for f in _FIELDS if getattr(self, f) is None]

    @property
    def confidence(self) -> float:
        """0..1 — resolved fields weighted by how they were resolved (see ``_SOURCE_WEIGHT``),
        averaged over every field this parser tracks. A caller (admin review UI) can use this
        to decide whether to auto-apply a result or ask a human to double-check it first."""
        return round(sum(_SOURCE_WEIGHT[s] for s in self.sources.values()) / len(_FIELDS), 2)


def _consume(text: str, *patterns: re.Pattern[str]) -> str:
    """Blanks out every match of ``patterns`` in ``text`` — used to keep already-claimed
    spans (episode/season/quality/year markers) out of the title-candidate line."""
    for pattern in patterns:
        text = pattern.sub(" ", text)
    return text


def _extract_episode(text: str) -> tuple[int | None, re.Match[str] | None]:
    if match := _EPISODE_NUM_RE.search(text):
        return int(match.group(1)), match
    if match := _QISM_NUM_RE.search(text):
        return int(match.group(1)), match
    if match := _QISM_NUM_RE_ALT.search(text):
        return int(match.group(1)), match
    if match := _EPISODE_WORD_RE.search(text):
        number = _word_to_number(match.group(1))
        if number is not None:
            return number, match
    return None, None


def _extract_season(text: str) -> tuple[int | None, re.Match[str] | None]:
    if match := _SEASON_NUM_RE.search(text):
        return int(match.group(1)), match
    if match := _FASL_NUM_RE.search(text):
        return int(match.group(1)), match
    if match := _FASL_NUM_RE_ALT.search(text):
        return int(match.group(1)), match
    if match := _SEASON_WORD_RE.search(text):
        number = _word_to_number(match.group(1))
        if number is not None:
            return number, match
    return None, None


def _extract_quality(text: str) -> tuple[str | None, re.Match[str] | None]:
    """Returns the tag in its canonical casing straight from ``_QUALITY_TAGS``
    (e.g. always "1080p", always "UHD") regardless of how it was cased in the source text."""
    for tag in _QUALITY_TAGS:
        if match := re.search(rf"\b{re.escape(tag)}\b", text, re.IGNORECASE):
            return tag, match
    return None, None


def _extract_year(text: str) -> tuple[int | None, re.Match[str] | None]:
    if match := _YEAR_PAREN_RE.search(text):
        return int(match.group(1)), match
    if match := _YEAR_BARE_RE.search(text):
        return int(match.group(1)), match
    return None, None


def _extract_title(text: str, consumed_spans: list[re.Match[str] | None]) -> str | None:
    cleaned = _consume(text, *[m.re for m in consumed_spans if m is not None])
    for line in cleaned.splitlines():
        candidate = _EMOJI_RE.sub("", line).strip(" \t-_.·|")
        if not candidate:
            continue
        if candidate.lower() in _NON_TITLE_PHRASES:
            continue
        return candidate
    return None


def extract_deterministic(text: str) -> ParsedCaption:
    """Pure regex extraction — no I/O, always safe to call, the sole source of truth
    for any field it manages to resolve (the AI fallback never overrides these)."""
    episode, episode_match = _extract_episode(text)
    season, season_match = _extract_season(text)
    quality, quality_match = _extract_quality(text)
    year, year_match = _extract_year(text)
    # An S01E05-style match covers season+episode in one shot when the
    # separate patterns above didn't already resolve them.
    if (season is None or episode is None) and (combined := _SXXEXX_RE.search(text)):
        if season is None:
            season, season_match = int(combined.group(1)), combined
        if episode is None:
            episode, episode_match = int(combined.group(2)), combined

    title = _extract_title(text, [episode_match, season_match, quality_match, year_match])

    result = ParsedCaption(
        title=title, season_number=season, episode_number=episode, quality=quality, year=year
    )
    result.sources = {f: "regex" for f in _FIELDS if getattr(result, f) is not None}
    return result


class CaptionParserService:
    """Orchestrates deterministic extraction + an optional Claude API fallback.

    ``api_key=None`` (the default when ``ANTHROPIC_API_KEY`` isn't set) makes
    this behave as regex-only — every install works without the AI stage;
    it's purely additive for messier real-world captions.
    """

    def __init__(
        self, api_key: str | None, model: str, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._http_client = http_client

    async def parse(self, text: str) -> ParsedCaption:
        result = extract_deterministic(text)
        if not self._api_key or not result.missing_fields:
            return result

        try:
            ai_values = await self._parse_with_ai(text, result.missing_fields)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("caption_parser_ai_failed", error=str(exc))
            return result

        for field_name in result.missing_fields:
            value = ai_values.get(field_name)
            if value is not None:
                setattr(result, field_name, value)
                result.sources[field_name] = "ai"
        return result

    async def _parse_with_ai(self, text: str, missing_fields: list[str]) -> dict[str, object]:
        system_prompt = (
            "You are a strict metadata extractor for a movie/anime Telegram channel post. "
            f"Extract ONLY these fields: {', '.join(missing_fields)}. "
            "Respond with a single valid JSON object with exactly those keys — no prose, "
            "no markdown fences. "
            "If a field's value cannot be determined with confidence from the given text, "
            "its value MUST be the JSON null — never guess a plausible-sounding default. "
            "season_number and episode_number and year must be integers or null. "
            "title and quality must be strings or null."
        )

        client = self._http_client or httpx.AsyncClient(timeout=_AI_TIMEOUT_SECONDS)
        owns_client = self._http_client is None
        try:
            response = await client.post(
                _ANTHROPIC_API_URL,
                headers={
                    "x-api-key": self._api_key or "",
                    "anthropic-version": _ANTHROPIC_API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": 512,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": text}],
                },
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if owns_client:
                await client.aclose()

        content_blocks = payload.get("content", [])
        text_block = next((b.get("text") for b in content_blocks if b.get("type") == "text"), None)
        if not text_block:
            raise ValueError("no text content in Anthropic response")

        parsed = json.loads(text_block)
        if not isinstance(parsed, dict):
            raise ValueError("Anthropic response was not a JSON object")
        return {k: v for k, v in parsed.items() if k in missing_fields}
