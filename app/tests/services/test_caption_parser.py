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


def test_labeled_title_line_strips_label() -> None:
    result = extract_deterministic("🎬 Nomi: Real dunyodan haqiqiyroq o'yin 3-qism")
    assert result.title == "Real dunyodan haqiqiyroq o'yin"
    assert result.episode_number == 3


def test_bracketed_episode_marker_leaves_no_empty_brackets_in_title() -> None:
    """Regression guard: the same show's captions later switched to wrapping the
    qism marker in brackets ("[10-qism]") — consuming just the marker text must
    not leave a dangling "[ ]" in the title, or this episode splinters into its
    own separately-titled series from the earlier, unbracketed episodes."""
    result = extract_deterministic("🎬 Nomi: Real dunyodan haqiqiyroq o'yin [10-qism]")
    assert result.title == "Real dunyodan haqiqiyroq o'yin"
    assert result.episode_number == 10


def test_bracket_only_decorative_line_is_skipped_for_title() -> None:
    """Regression guard: a "[ Video ]" format tag on its own line, ahead of the
    real "Nomi: ..." labeled title, must not itself win as the title — that
    would splinter one show's episodes across two differently-titled series."""
    result = extract_deterministic("[ Video ]\n🎬 Nomi: Real dunyodan haqiqiyroq o'yin 3-qism")
    assert result.title == "Real dunyodan haqiqiyroq o'yin"


def test_qism_with_colon_and_total_count_fraction() -> None:
    """Some fansub captions use "Qism: N/Total" instead of "N-qism" — only the
    current-episode numerator matters, the "/Total" is that channel's own tag."""
    result = extract_deterministic("📒 Nomi: Bu chinni qo'g'irchoq sevib qoldi\n🎞 Qism: 5/12 🎥")
    assert result.title == "Bu chinni qo'g'irchoq sevib qoldi"
    assert result.episode_number == 5


def test_anime_labeled_title_line_strips_label() -> None:
    result = extract_deterministic("Anime: Ovchi x Ovchi\n3-qism")
    assert result.title == "Ovchi x Ovchi"


def test_anime_nomi_combined_label_strips_label() -> None:
    """Regression guard: "Anime nomi:" ("anime name:") is its own channel's combined
    label — must not fall through to matching bare "anime" and then failing on the
    leftover " nomi: <title>" text, which would leave a hashtag noise line from
    earlier in the caption to win as the title instead."""
    result = extract_deterministic("#new #nisekoi\n\nAnime nomi: Soxta Sevgi\n\nQismi: 1")
    assert result.title == "Soxta Sevgi"


def test_hashtag_prefixed_labeled_title_strips_hashtag() -> None:
    result = extract_deterministic("📒 Nomi: #Arifureta\n🎞 Qism: 13/13")
    assert result.title == "Arifureta"


def test_markdown_emphasis_markers_stripped_from_title() -> None:
    result = extract_deterministic("**__ Nomi: Shaman KIng\n5-qism")
    assert result.title == "Shaman KIng"


def test_qism_marker_immediately_wrapped_in_markdown_underscores() -> None:
    """Regression guard: "5 qism__" (Telegram __italic__ markdown butted directly
    against the marker, no space) must still match — "_" is a \\w character, so
    an unstripped trailing "__" would silently defeat qism's closing \\b."""
    result = extract_deterministic("__Show Name [Tag] - 5 qism__\n#Hashtag")
    assert result.episode_number == 5


def test_uzbek_qismi_possessive_suffix() -> None:
    """"qismi" ("the Nth part") is Uzbek's own grammatically correct possessive
    form, not a typo of "qism" — a real, common caption spelling."""
    result = extract_deterministic("🎬 Nomi: Dororo 4-qismi")
    assert result.title == "Dororo"
    assert result.episode_number == 4


def test_episode_marker_seen_when_word_present_but_no_number_resolved() -> None:
    """A caption that clearly talks about an episode ("qism") but whose number
    couldn't be resolved must be flagged so a caller doesn't mistake it for a
    standalone movie — see CaptionIngestService's use of this flag."""
    result = extract_deterministic("Some Show\nYangi qism tez orada")
    assert result.episode_number is None
    assert result.episode_marker_seen is True


def test_episode_marker_not_seen_for_genuine_standalone_movie() -> None:
    result = extract_deterministic("Sening Isming (Max film)\n1080p")
    assert result.episode_number is None
    assert result.episode_marker_seen is False


def test_premyera_banner_line_skipped_for_title() -> None:
    """Regression guard: "Premyera" ("premiere") is a promotional banner line
    some channels put ahead of the real title — picking it as the title would
    dump every different show's episodes under one fake "Premyera" series."""
    result = extract_deterministic('🔥 #Premyera\n\n🎬 "Grimm" T/s seriali 4 fasl 21.Qism')
    assert result.title == 'Grimm" T/s seriali'
    assert result.season_number == 4
    assert result.episode_number == 21


def test_premyera_variants_all_skipped() -> None:
    for line in ("PREMYERA", "SUPER PREMYERA", "KANALDA PREMYERA", "Premyera 3.Fasl", "Premyera... Boshlandi"):
        result = extract_deterministic(f"{line}\nActual Show Title")
        assert result.title == "Actual Show Title", line


def test_qism_with_period_separator() -> None:
    result = extract_deterministic("Show Name\n21.Qism")
    assert result.episode_number == 21


def test_fasl_with_period_separator() -> None:
    result = extract_deterministic("Show Name\n3.Fasl")
    assert result.season_number == 3


def test_mavsum_as_season_synonym() -> None:
    result = extract_deterministic("Show Name\n2-mavsum 5-qism")
    assert result.season_number == 2
    assert result.episode_number == 5


def test_bolim_part_marker_stripped_from_title() -> None:
    """Regression guard: a "cour"/part split of one season ("(3-fasl 1-bo'lim)",
    then later "(3-fasl 2-bo'lim)") must not leak its part number into the
    title — a different part number per post would otherwise splinter the
    same show into a new series each time a new part starts airing."""
    part1 = extract_deterministic("Anime: Omadsizning Qayta Tug'ilishi (3-fasl 1-bo'lim)\nQism: 1/14")
    part2 = extract_deterministic("Anime: Omadsizning Qayta Tug'ilishi (3-fasl 2-bo'lim)\nQism: 1/12")

    assert part1.title == "Omadsizning Qayta Tug'ilishi"
    assert part2.title == "Omadsizning Qayta Tug'ilishi"
    assert part1.season_number == 3
    assert part2.season_number == 3


def test_title_ending_in_bare_number_does_not_bleed_into_next_line_qism() -> None:
    """Regression guard: when a show's real title ends in a bare number ("Iblis Lordi
    2099", "Kaiju No. 8") sitting on its own line right above a separate "Qism: N/Total"
    line, that trailing digit must not bridge across the line break and get misread as
    "<title's number>-qism" — every post for a 12-episode show would otherwise parse as
    the *same* wrong episode number (the title's own number), splintering it into a
    separate one-episode series per post instead of accumulating under one series."""
    result = extract_deterministic("Anime: Iblis Lordi 2099\nQism: 5/12\nOvoz berdi: BADBRO")
    assert result.title == "Iblis Lordi 2099"
    assert result.episode_number == 5

    kaiju = extract_deterministic("Anime: Kaiju No. 8\nQism: 1/12 (ONGOING)\nOvoz berdi: BADBRO")
    assert kaiju.title == "Kaiju No. 8"
    assert kaiju.episode_number == 1


def test_quoted_title_strips_surrounding_quotes() -> None:
    result = extract_deterministic('"Doktor Haus."    \n2-mavsum 5-qism')
    assert result.title == "Doktor Haus"


def test_numeric_paren_noise_stripped_after_season_episode_resolved() -> None:
    """Regression guard: "Lutsifer (2 FASL 3 QISM) (16)" — the trailing "(16)"
    is the channel's own internal post counter, not part of the title; left
    in, a different counter per post splinters the same show into a new
    series every single episode."""
    result = extract_deterministic("🔥 Lutsifer  (2 FASL 3 QISM) (16) 🔥")
    assert result.title == "Lutsifer"
    assert result.season_number == 2
    assert result.episode_number == 3


def test_year_in_parens_not_treated_as_noise() -> None:
    result = extract_deterministic("Inception (2010)")
    assert result.year == 2010
    assert result.title == "Inception"


def test_qism_with_ini_suffix() -> None:
    """"qismini" ("watch its Nth part") is a real Uzbek accusative+possessive
    construction, not a typo of "qism"."""
    result = extract_deterministic("Hoziroq 2 qismini tomosha qiling")
    assert result.episode_number == 2


def test_fasl_with_ning_suffix() -> None:
    result = extract_deterministic("Show\n3 faslning qismlari")
    assert result.season_number == 3


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


def test_stylized_unicode_font_caption_is_normalized() -> None:
    """Regression guard: some channels post in "Mathematical Alphanumeric Symbols"
    (a stylized Unicode font) purely for visual flair — every regex here is written
    against plain ASCII keywords, so without NFKC normalization first, a caption like
    this parses as if it had no recognizable title/marker text at all."""
    result = extract_deterministic("𝙰𝚗𝚒𝚖𝚎: 𝙸𝚋𝚕𝚒𝚜𝚕𝚊𝚛𝚗𝚒 𝚔𝚎𝚜𝚞𝚟𝚌𝚑𝚒 𝚚𝚒𝚕𝚒𝚌𝚑 3 𝚜𝚎𝚣𝚘𝚗\n𝚀𝚒𝚜𝚖: 6/?")
    assert result.title == "Iblislarni kesuvchi qilich"
    assert result.season_number == 3
    assert result.episode_number == 6


def test_qism_spelling_variants_qsm_and_qisim() -> None:
    """Regression guard: "Qism" drifts across channels beyond the possessive-suffix
    forms already covered — "Qsm" (vowel dropped) and "Qisim" (vowel added) both show
    up as often as the standard spelling on some channels."""
    qsm = extract_deterministic("Nomi: Ara Odam\n\n(1-Fasl) 9-Qsm")
    assert qsm.season_number == 1
    assert qsm.episode_number == 9

    qisim = extract_deterministic("Nomi: Test Anime\n\nQisim: 5/26")
    assert qisim.episode_number == 5


def test_underscore_is_a_valid_marker_separator() -> None:
    result = extract_deterministic("BuAjoyibDunyo2\nQism_7|10")
    assert result.episode_number == 7


def test_decorative_box_drawing_prefix_does_not_defeat_title_label() -> None:
    """Regression guard: a decorative banner ("╭────", "├‣ ➙") wrapped around a
    "Nomi:"-labeled line must not stop the label from being recognized — these
    box-drawing/bullet characters survive plain emoji-stripping, so left alone they
    sit in front of "Nomi:" and defeat the label regex's start-of-line anchor."""
    result = extract_deterministic(
        "╭──────────────────────\n"
        "├‣ ➙🎬 Nomi:Meni qahramonlar jamoasidan haydashdi➤\n"
        "➙🎥 Qismi:➤5"
    )
    assert result.title == "Meni qahramonlar jamoasidan haydashdi"


def test_sezon_is_a_season_synonym() -> None:
    result = extract_deterministic("Show Name 2-sezon\nQism: 3")
    assert result.season_number == 2
    assert result.episode_number == 3
