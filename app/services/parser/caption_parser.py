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
import unicodedata
from dataclasses import dataclass, field

import httpx

from app.core.logger import get_logger

logger = get_logger(__name__)

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_API_VERSION = "2023-06-01"
_AI_TIMEOUT_SECONDS = 15.0
# Local CPU/GPU inference is slower and more variable than a cloud API call,
# especially the first request after the model needs loading into memory.
_OLLAMA_TIMEOUT_SECONDS = 60.0

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
    # Bare announcement-banner lines ("🔥 TUGADI! 🔥", "BOSHLANDI") some
    # channels post with no other title text at all — accepting one as a
    # real title risks merging two completely unrelated shows together
    # later, since "Final"/"Tugadi" is exactly the kind of word many
    # different shows' *real* captions also carry as a decorative suffix.
    "final", "tugadi", "tugadi!", "boshlandi", "boshlandi!", "boshlandii",
    "yakuniy", "yakuniy qism", "tamom", "ova",
}
# "Premyera" ("premiere") is a promotional banner line ("Premyera", "SUPER
# PREMYERA", "Premyera 3.Fasl", "Premyera... Boshlandi") that shows up *ahead
# of* the real title line in some channels — an exact-phrase match in
# _NON_TITLE_PHRASES can't catch every variant, so this instead matches any
# candidate line that *starts with* the word (trailing season/hype text and
# all), which the plain set-membership check above would miss entirely.
_PROMOTIONAL_LINE_RE = re.compile(r"^(?:super\s+|kanalda\s+)?premyera\b", re.IGNORECASE)

# "Anime nomi:"/"Anime nom:" ("anime name:") is its own channel's combined
# label, distinct from a bare "Anime:" or "Nomi:" line — must be listed
# before the bare alternatives so "Anime nomi: X" doesn't fall through to
# matching just "anime" and then failing on the leftover "nomi: X" text.
_TITLE_LABEL_RE = re.compile(
    r"^(?:anime\s+nomi|anime\s+nom|nomi|nom|title|name|anime)\s*[:\-]\s*(.+)$", re.IGNORECASE
)
# A line that's nothing but a bracketed tag (e.g. "[ Video ]", "[HD]") once
# trimmed — a post-format marker, never the actual title, so it must not win
# the "first surviving line" fallback below.
_BRACKET_ONLY_RE = re.compile(r"^\[.*\]$")
# Some channels wrap the episode/season marker itself in brackets on the title
# line, e.g. "Nomi: Show [10-qism]" — once the marker text is consumed, the
# empty bracket pair left behind ("Nomi: Show [ ]") must not leak into the
# title, or every episode number variant splinters into its own series.
_EMPTY_BRACKET_RE = re.compile(r"[\[({]\s*[\])}]")
# A bare 1-3 digit number in parens ("Lutsifer (16)") that survives after
# season/episode/year/quality have already been extracted elsewhere in the
# caption is virtually always the channel's own internal post/batch counter,
# not part of the title — left alone, a different counter value per post
# means the very same show splinters into a new series every single episode.
# 4-digit runs are excluded so a genuine year in parens is never touched.
_NUMERIC_PAREN_NOISE_RE = re.compile(r"\(\s*\d{1,3}\s*\)")
# Telegram markdown emphasis markers — stripped wholesale before any other
# extraction runs (see extract_deterministic).
_MARKDOWN_MARKER_RE = re.compile(r"\*\*|__|~~")

_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0001f1e6-\U0001f1ff"
    "\ufe0f"  # variation selector-16 (emoji presentation)
    "\u200d"  # zero-width joiner (combined emoji)
    "\u2500-\u257f"  # box-drawing (decorative "\u256d\u2500\u2500\u2500\u2500"/"\u251c" banner borders)
    "\u2022-\u2027"  # bullet-ish punctuation ("\u2023" and friends)
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
_RESERVED_MARKER_WORDS = r"Episode|Ep|Season|Qism|Qsm|Qisim|Fasl|Mavsum|Sezon"
_EPISODE_WORD_RE = re.compile(
    rf"\b(?:Episode|Ep)\.?\s+([A-Za-z]+(?:[\s-]+(?!(?:{_RESERVED_MARKER_WORDS})\b)[A-Za-z]+)?)\b",
    re.IGNORECASE,
)
# Uzbek's own possessive/definite suffixes ("qism" -> "qismi"/"qismini"/
# "qismning", "N-qismini tomosha qiling" = "watch its Nth part") are distinct,
# common, grammatically-correct spellings — not typos — so they're matched
# explicitly rather than patched around. Longest alternative first so "ini"
# wins over the bare "i" it starts with.
# "." is also a real separator some channels use ("21.Qism", "3.Fasl") —
# alongside space/hyphen, not instead of them. Deliberately excludes "\n":
# a title that happens to end in a bare number ("Iblis Lordi 2099", "Kaiju
# No. 8") sitting on the line right above a separate "Qism: N/Total" line
# must not let that trailing number bridge across the line break and get
# read as "<number>-qism" — allowing "\s" (which matches newlines too)
# here did exactly that, misreading the title's own trailing digits as the
# episode/season number instead of the real one on the next line.
_SUFFIX_VARIANTS = r"(?:ini|ning|i)?"
# "." and "_" are both real separators different channels use ("21.Qism",
# "Qism_1") alongside space/hyphen — "\n" is deliberately excluded (see above).
_SAME_LINE_SEP = r"[ \t._-]*"
# "Qism" itself has observed spelling drift across channels beyond the
# possessive suffixes above: "Qsm" (vowel dropped) and "Qisim" (vowel added)
# both show up as often as the standard spelling on some channels' posts.
_QISM_WORD = r"q(?:ism|isim|sm)"
_QISM_NUM_RE = re.compile(rf"\b(\d{{1,4}}){_SAME_LINE_SEP}{_QISM_WORD}{_SUFFIX_VARIANTS}\b", re.IGNORECASE)
# "Qism: 5/12" (a fansub's own "current/total" counter) — the trailing
# "/total" is just that channel's episode-count tag, not part of the number
# we want, so the pattern stops at the first digit run.
_QISM_NUM_RE_ALT = re.compile(
    rf"\b{_QISM_WORD}{_SUFFIX_VARIANTS}{_SAME_LINE_SEP}[:#]?{_SAME_LINE_SEP}(\d{{1,4}})\b", re.IGNORECASE
)
_SEASON_NUM_RE = re.compile(r"\bSeason\s*#?\s*(\d{1,3})\b", re.IGNORECASE)
_FASL_NUM_RE = re.compile(rf"\b(\d{{1,3}}){_SAME_LINE_SEP}fasl{_SUFFIX_VARIANTS}\b", re.IGNORECASE)
_FASL_NUM_RE_ALT = re.compile(rf"\bfasl{_SUFFIX_VARIANTS}{_SAME_LINE_SEP}[:#]?{_SAME_LINE_SEP}(\d{{1,3}})\b", re.IGNORECASE)
# "Mavsum" is another real Uzbek word for "season", used interchangeably
# with "fasl" depending on the channel/translator.
_MAVSUM_NUM_RE = re.compile(rf"\b(\d{{1,3}}){_SAME_LINE_SEP}mavsum{_SUFFIX_VARIANTS}\b", re.IGNORECASE)
_MAVSUM_NUM_RE_ALT = re.compile(
    rf"\bmavsum{_SUFFIX_VARIANTS}{_SAME_LINE_SEP}[:#]?{_SAME_LINE_SEP}(\d{{1,3}})\b", re.IGNORECASE
)
# "Sezon" (from Russian "сезон") is a third real "season" synonym some
# channels use instead of "fasl"/"mavsum".
_SEZON_NUM_RE = re.compile(rf"\b(\d{{1,3}}){_SAME_LINE_SEP}sezon{_SUFFIX_VARIANTS}\b", re.IGNORECASE)
_SEZON_NUM_RE_ALT = re.compile(
    rf"\bsezon{_SUFFIX_VARIANTS}{_SAME_LINE_SEP}[:#]?{_SAME_LINE_SEP}(\d{{1,3}})\b", re.IGNORECASE
)
# "Bo'lim" ("part"/"cour") splits one season into multiple forward-numbered
# chunks that each restart their own episode count (a long season released in
# batches) — e.g. "(3-fasl 1-bo'lim)" then later "(3-fasl 2-bo'lim)". There's
# no reliable general rule for folding "part" into a single running episode
# number (each part's own length varies and isn't known up front), so this is
# only ever stripped out of the title candidate — not resolved into a field —
# to stop it leaking in as literal, part-numbered title noise (which would
# otherwise mint a "new" duplicate series per part, the exact bug this is
# guarding against). The resulting season/episode collision on the next
# part's episode 1 is left to the existing refuse-and-DM safety net, where a
# human can place it with the right episode number by hand.
_BOLIM_NUM_RE = re.compile(rf"\b(\d{{1,3}}){_SAME_LINE_SEP}bo[ʻʼ']?lim{_SUFFIX_VARIANTS}\b", re.IGNORECASE)
_BOLIM_NUM_RE_ALT = re.compile(
    rf"\bbo[ʻʼ']?lim{_SUFFIX_VARIANTS}{_SAME_LINE_SEP}[:#]?{_SAME_LINE_SEP}(\d{{1,3}})\b", re.IGNORECASE
)
_SEASON_WORD_RE = re.compile(
    rf"\bSeason\s+([A-Za-z]+(?:[\s-]+(?!(?:{_RESERVED_MARKER_WORDS})\b)[A-Za-z]+)?)\b",
    re.IGNORECASE,
)
_YEAR_PAREN_RE = re.compile(r"\((\d{4})\)")
_YEAR_BARE_RE = re.compile(r"\b(19\d{2}|20[0-3]\d)\b")
# Broad "this text is talking about an episode" signal, independent of
# whether a number was actually attached — see ParsedCaption.episode_marker_seen.
_EPISODE_MARKER_WORD_RE = re.compile(rf"\b(?:{_QISM_WORD}|epizod|episode)\b", re.IGNORECASE)
# Broad "this post belongs to a part/cour-split season" signal — see
# ParsedCaption.part_marker_seen and the note above _BOLIM_NUM_RE.
_BOLIM_MARKER_WORD_RE = re.compile(r"\bbo[ʻʼ']?lim\b", re.IGNORECASE)

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
    # True if the raw caption uses an episode word ("qism"/"epizod"/"episode")
    # at all, regardless of whether a number was successfully extracted next
    # to it — lets a caller tell "genuinely a standalone movie" apart from
    # "this is someone's episode, we just failed to read which one" instead
    # of defaulting the latter into a movie by mistake.
    episode_marker_seen: bool = False
    # True if the caption mentions "bo'lim" (a part/cour within a season) at
    # all — the episode number on one of these is only unique *within its own
    # part*, not across the whole season, so a caller must not treat a
    # same-episode-number collision on one of these as "definitely the same
    # episode re-uploaded" (see CaptionIngestService's replace_on_collision).
    part_marker_seen: bool = False

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
    if match := _MAVSUM_NUM_RE.search(text):
        return int(match.group(1)), match
    if match := _MAVSUM_NUM_RE_ALT.search(text):
        return int(match.group(1)), match
    if match := _SEZON_NUM_RE.search(text):
        return int(match.group(1)), match
    if match := _SEZON_NUM_RE_ALT.search(text):
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


_TITLE_STRIP_CHARS = " \t-_.·|*#\"“”«»‹›"


def _extract_title(text: str, consumed_spans: list[re.Match[str] | None]) -> str | None:
    cleaned = _consume(
        text, *[m.re for m in consumed_spans if m is not None], _BOLIM_NUM_RE, _BOLIM_NUM_RE_ALT
    )
    candidates = []
    for line in cleaned.splitlines():
        candidate = _EMOJI_RE.sub("", line).strip(_TITLE_STRIP_CHARS)
        if not candidate:
            continue
        if candidate.lower() in _NON_TITLE_PHRASES:
            continue
        if _BRACKET_ONLY_RE.match(candidate):
            continue
        if _PROMOTIONAL_LINE_RE.match(candidate):
            continue
        candidate = _EMPTY_BRACKET_RE.sub("", candidate).strip(_TITLE_STRIP_CHARS)
        candidate = _NUMERIC_PAREN_NOISE_RE.sub("", candidate).strip(_TITLE_STRIP_CHARS)
        if not candidate:
            continue
        candidates.append(candidate)

    # An explicit "Nomi: ..."/"Title: ..." label beats plain line order —
    # channels routinely put a decorative or format tag ("[ Video ]") on the
    # line *before* the actual labeled title.
    for candidate in candidates:
        if label_match := _TITLE_LABEL_RE.match(candidate):
            return label_match.group(1).strip(_TITLE_STRIP_CHARS)

    return candidates[0] if candidates else None


def extract_deterministic(text: str) -> ParsedCaption:
    """Pure regex extraction — no I/O, always safe to call, the sole source of truth
    for any field it manages to resolve (the AI fallback never overrides these)."""
    # Some channels post captions in a stylized Unicode font (Mathematical
    # Alphanumeric Symbols — "𝙰𝚗𝚒𝚖𝚎" instead of "Anime") purely for visual flair.
    # Every regex below is written against plain ASCII keywords, so left
    # unnormalized this is indistinguishable from a caption with no
    # recognizable title/marker text at all. NFKC folds each styled
    # character back to its plain compatibility equivalent losslessly for
    # this purpose — it's a real title either way, just rendered differently.
    text = unicodedata.normalize("NFKC", text)
    # Telegram markdown emphasis (__bold__, **bold**, ~~strike~~) is routinely
    # wrapped directly around a marker with no space, e.g. "5 qism__" — since
    # "_" is a \w character, that trailing __ silently defeats every marker
    # pattern's closing \b. Stripping the marker pairs up front avoids
    # special-casing every single regex below.
    text = _MARKDOWN_MARKER_RE.sub("", text)
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
        title=title,
        season_number=season,
        episode_number=episode,
        quality=quality,
        year=year,
        episode_marker_seen=bool(_EPISODE_MARKER_WORD_RE.search(text)),
        part_marker_seen=bool(_BOLIM_MARKER_WORD_RE.search(text)),
    )
    result.sources = {f: "regex" for f in _FIELDS if getattr(result, f) is not None}
    return result


def _ai_system_prompt(missing_fields: list[str]) -> str:
    return (
        "You are a strict metadata extractor for a movie/anime Telegram channel post. "
        f"Extract ONLY these fields: {', '.join(missing_fields)}. "
        "Respond with a single valid JSON object with exactly those keys — no prose, "
        "no markdown fences. "
        "If a field's value cannot be determined with confidence from the given text, "
        "its value MUST be the JSON null — never guess a plausible-sounding default. "
        "season_number and episode_number and year must be integers or null. "
        "title and quality must be strings or null."
    )


def _coerce_ai_json(raw: str, missing_fields: list[str]) -> dict[str, object]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("AI response was not a JSON object")
    return {k: v for k, v in parsed.items() if k in missing_fields}


class CaptionParserService:
    """Orchestrates deterministic extraction + an optional AI fallback.

    Two interchangeable AI backends, tried in this order when configured:
    1. **Ollama** (``ollama_base_url`` set) — local, free, no data leaves the
       machine; preferred whenever it's available.
    2. **Anthropic** (``api_key`` set) — used if Ollama isn't configured.

    Neither is required — ``ollama_base_url=None`` and ``api_key=None`` (the
    default) makes this behave as regex-only — every install works without
    the AI stage; it's purely additive for messier real-world captions.
    """

    def __init__(
        self,
        api_key: str | None,
        model: str,
        http_client: httpx.AsyncClient | None = None,
        *,
        ollama_base_url: str | None = None,
        ollama_model: str = "qwen3:8b",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._http_client = http_client
        self._ollama_base_url = ollama_base_url.rstrip("/") if ollama_base_url else None
        self._ollama_model = ollama_model

    async def parse(self, text: str) -> ParsedCaption:
        result = extract_deterministic(text)
        if not result.missing_fields:
            return result

        if self._ollama_base_url:
            try:
                ai_values = await self._parse_with_ollama(text, result.missing_fields)
                self._apply_ai_values(result, ai_values)
                return result
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("caption_parser_ollama_failed", error=str(exc))
                # Falls through to Anthropic (if configured) rather than giving
                # up outright — a transient local-model hiccup shouldn't cost
                # the whole AI stage when a cloud fallback is also available.

        if not self._api_key:
            return result

        try:
            ai_values = await self._parse_with_ai(text, result.missing_fields)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("caption_parser_ai_failed", error=str(exc))
            return result

        self._apply_ai_values(result, ai_values)
        return result

    @staticmethod
    def _apply_ai_values(result: ParsedCaption, ai_values: dict[str, object]) -> None:
        for field_name in list(result.missing_fields):
            value = ai_values.get(field_name)
            if value is not None:
                setattr(result, field_name, value)
                result.sources[field_name] = "ai"

    async def _parse_with_ollama(self, text: str, missing_fields: list[str]) -> dict[str, object]:
        client = self._http_client or httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT_SECONDS)
        owns_client = self._http_client is None
        try:
            response = await client.post(
                f"{self._ollama_base_url}/api/chat",
                json={
                    "model": self._ollama_model,
                    "stream": False,
                    "format": "json",
                    # Extended "thinking" is on by default for models that support it
                    # (e.g. qwen3) and turns a ~1-2s structured-extraction call into a
                    # 40-60s one for no accuracy benefit on a task this narrow.
                    "think": False,
                    "messages": [
                        {"role": "system", "content": _ai_system_prompt(missing_fields)},
                        {"role": "user", "content": text},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if owns_client:
                await client.aclose()

        content = payload.get("message", {}).get("content")
        if not content:
            raise ValueError("no content in Ollama response")
        return _coerce_ai_json(content, missing_fields)

    async def _parse_with_ai(self, text: str, missing_fields: list[str]) -> dict[str, object]:
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
                    "system": _ai_system_prompt(missing_fields),
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
        return _coerce_ai_json(text_block, missing_fields)
