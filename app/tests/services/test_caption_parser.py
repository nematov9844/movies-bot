"""Pure regex-extraction tests — no DB, no network, one behavior per test."""

from app.services.parser.caption_parser import extract_deterministic


def test_sxxexx_style() -> None:
    result = extract_deterministic("Naruto\nS01E05")
    assert result.title == "Naruto"
    assert result.season_number == 1
    assert result.episode_number == 5
    assert result.sources == {"title": "regex", "season_number": "regex", "episode_number": "regex"}


def test_sxxexx_lowercase_no_padding() -> None:
    result = extract_deterministic("One Piece\ns1e5")
    assert result.season_number == 1
    assert result.episode_number == 5


def test_episode_numeric() -> None:
    result = extract_deterministic("Naruto\nEpisode 5")
    assert result.title == "Naruto"
    assert result.episode_number == 5
    assert result.season_number is None


def test_episode_word_number() -> None:
    result = extract_deterministic("Naruto\nEpisode Five")
    assert result.episode_number == 5


def test_season_and_episode_word_numbers() -> None:
    """Regression guard for the "Season One Episode Five" ambiguity: without the reserved-word
    lookahead, the season pattern greedily swallows "One Episode" and season_number ends up None."""
    result = extract_deterministic("Naruto\nSeason One Episode Five")
    assert result.title == "Naruto"
    assert result.season_number == 1
    assert result.episode_number == 5


def test_season_and_episode_word_numbers_compound() -> None:
    result = extract_deterministic("Show\nSeason Twenty Two Episode Thirty Five")
    assert result.season_number == 22
    assert result.episode_number == 35


def test_uzbek_qism_suffix() -> None:
    result = extract_deterministic("Naruto\n5-qism")
    assert result.title == "Naruto"
    assert result.episode_number == 5


def test_uzbek_qism_prefix() -> None:
    result = extract_deterministic("Naruto\nQism 5")
    assert result.episode_number == 5


def test_uzbek_fasl_suffix() -> None:
    result = extract_deterministic("Naruto\n2-fasl 5-qism")
    assert result.season_number == 2
    assert result.episode_number == 5


def test_quality_tag() -> None:
    result = extract_deterministic("Some Movie\n1080p")
    assert result.quality == "1080p"


def test_quality_tag_case_insensitive_input_canonical_output() -> None:
    result = extract_deterministic("Some Movie\nHD quality, uhd remaster")
    assert result.quality in ("UHD", "HD")


def test_year_in_parens() -> None:
    result = extract_deterministic("Inception (2010)")
    assert result.year == 2010
    assert result.title == "Inception"


def test_year_bare() -> None:
    result = extract_deterministic("Inception 2010")
    assert result.year == 2010


def test_filename_style() -> None:
    result = extract_deterministic("Naruto.S01E05.1080p.mkv")
    assert result.season_number == 1
    assert result.episode_number == 5
    assert result.quality == "1080p"


def test_combined_series_season_episode_year_quality() -> None:
    result = extract_deterministic("Attack on Titan (2013)\nSeason 4 Episode 12\n1080p")
    assert result.title == "Attack on Titan"
    assert result.year == 2013
    assert result.season_number == 4
    assert result.episode_number == 12
    assert result.quality == "1080p"


def test_emoji_only_promotional_caption_yields_no_confident_fields() -> None:
    result = extract_deterministic("🔥 New Episode 🔥")
    assert result.title is None
    assert result.episode_number is None
    assert result.sources == {}


def test_plain_movie_title_no_markers() -> None:
    result = extract_deterministic("Just a plain movie title with nothing else")
    assert result.title == "Just a plain movie title with nothing else"
    assert result.episode_number is None
    assert result.season_number is None


def test_no_text_at_all_yields_all_null() -> None:
    result = extract_deterministic("")
    assert result.title is None
    assert result.season_number is None
    assert result.episode_number is None
    assert result.quality is None
    assert result.year is None
    assert result.sources == {}


def test_is_episode_property() -> None:
    assert extract_deterministic("Naruto\nEpisode 5").is_episode is True
    assert extract_deterministic("Standalone Movie").is_episode is False


def test_missing_fields_property() -> None:
    result = extract_deterministic("Naruto\nEpisode 5")
    assert set(result.missing_fields) == {"season_number", "quality", "year"}


def test_confidence_is_zero_for_no_fields_resolved() -> None:
    assert extract_deterministic("").confidence == 0.0


def test_confidence_is_full_when_every_field_resolved_by_regex() -> None:
    result = extract_deterministic("Attack on Titan (2013)\nSeason 4 Episode 12\n1080p")
    assert result.missing_fields == []
    assert result.confidence == 1.0


def test_confidence_is_partial_when_some_fields_missing() -> None:
    result = extract_deterministic("Naruto\nEpisode 5")
    # 2 of 5 fields resolved (title, episode_number), both by regex.
    assert result.confidence == round(2 / 5, 2)


def test_confidence_weighs_ai_sourced_fields_lower_than_regex() -> None:
    result = extract_deterministic("Naruto\nEpisode 5")
    result.quality = "1080p"
    result.sources["quality"] = "ai"
    # (1.0 + 1.0 + 0.6) / 5 == 0.52
    assert result.confidence == round((1.0 + 1.0 + 0.6) / 5, 2)
