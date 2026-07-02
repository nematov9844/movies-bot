from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Kino qidirish")],
            [KeyboardButton(text="👤 Profil"), KeyboardButton(text="⭐ Premium")],
            [KeyboardButton(text="⚙️ Sozlamalar"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="🎁 Do'stlarni taklif qilish")],
        ],
        resize_keyboard=True,
    )
