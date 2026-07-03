"""Minimal dict-based translator for user-facing bot text.

Every string a handler shows to a user goes through :func:`t`. Translations
are keyed by a dotted string key, then by ISO language code. ``uz`` is the
bot's default language and must stay complete; ``ru`` is filled in
incrementally as needed (see ``SUPPORTED_LANGUAGES`` in
``app.core.constants``) — a missing ``ru`` string (or an entirely unsupported
language code) falls back to ``uz`` rather than raising, since a translation
gap must never break the bot for a user.
"""

from typing import Any

from app.core.constants import DEFAULT_LANGUAGE

TRANSLATIONS: dict[str, dict[str, str]] = {
    "welcome": {
        "uz": (
            "Assalomu alaykum, {name}! 👋\n\n"
            "Bu bot orqali kinolarni topishingiz mumkin. "
            "Kino kodini yuboring yoki quyidagi menyudan foydalaning."
        ),
        "ru": (
            "Здравствуйте, {name}! 👋\n\n"
            "Через этого бота вы можете находить фильмы. "
            "Отправьте код фильма или воспользуйтесь меню ниже."
        ),
    },
    "profile": {
        "uz": (
            "👤 <b>Sizning profilingiz</b>\n\n"
            "🆔 Telegram ID: <code>{telegram_id}</code>\n"
            "👨‍💼 Ism: {full_name}\n"
            "💎 Premium: {premium_status}\n"
            "🎬 Ko'rilgan kinolar: {movies_watched} ta\n"
            "👥 Takliflar: {referral_count} ta"
        ),
    },
    "profile.premium_active": {
        "uz": "faol, muddati: {expires_at}",
    },
    "profile.premium_none": {
        "uz": "yo'q",
    },
    "settings.choose_language": {
        "uz": "⚙️ Tilni tanlang:",
        "ru": "⚙️ Выберите язык:",
    },
    "settings.language_changed": {
        "uz": "✅ Til muvaffaqiyatli o'zgartirildi!",
        "ru": "✅ Язык успешно изменён!",
    },
    "invite.text": {
        "uz": (
            "🎁 Sizning taklif havolangiz:\n{link}\n\n"
            "Siz orqali botga qo'shilganlar: {count} ta"
        ),
    },
}


def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs: Any) -> str:
    """Translate ``key`` into ``lang``, formatting ``kwargs`` into the string.

    Falls back to :data:`DEFAULT_LANGUAGE` when ``lang`` (or the key itself,
    for that language) is missing. If the key is entirely unknown, the key
    is returned as-is rather than raising — this function must never crash
    a handler over a translation gap.
    """
    entries = TRANSLATIONS.get(key)
    if entries is None:
        return key

    template = entries.get(lang) or entries.get(DEFAULT_LANGUAGE)
    if template is None:
        return key

    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template
