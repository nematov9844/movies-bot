from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import SUPPORTED_LANGUAGES
from app.core.i18n import t
from app.core.logger import get_logger
from app.services.user.user_service import UserService

router = Router(name="settings")
logger = get_logger(__name__)

# Language names are proper nouns, not translated strings — shown the same
# regardless of the currently active UI language.
_LANGUAGE_LABELS: dict[str, str] = {
    "uz": "🇺🇿 O'zbekcha",
    "ru": "🇷🇺 Русский",
}
_LANGUAGE_CALLBACK_PREFIX = "set_lang:"


def _language_keyboard(current_language: str) -> InlineKeyboardMarkup:
    rows = []
    for lang in SUPPORTED_LANGUAGES:
        label = _LANGUAGE_LABELS.get(lang, lang)
        if lang == current_language:
            label = f"✅ {label}"
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"{_LANGUAGE_CALLBACK_PREFIX}{lang}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(F.text == "⚙️ Sozlamalar")
async def show_settings(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return

    language = await UserService(session).get_language(user.id)
    await message.answer(
        t("settings.choose_language", lang=language),
        reply_markup=_language_keyboard(language),
    )


@router.callback_query(F.data.startswith(_LANGUAGE_CALLBACK_PREFIX))
async def set_language(callback: CallbackQuery, session: AsyncSession) -> None:
    user = callback.from_user
    if callback.data is None:
        await callback.answer()
        return

    language = callback.data.removeprefix(_LANGUAGE_CALLBACK_PREFIX)
    if language not in SUPPORTED_LANGUAGES:
        await callback.answer()
        return

    await UserService(session).set_language(user.id, language)

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            t("settings.language_changed", lang=language),
        )
    await callback.answer()
    logger.info("language_changed", user_id=user.id, language=language)
