"""Inline keyboards for the admin `/panel` -> "🗂 Kategoriyalar" management flow."""

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import Category


def category_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Kategoriya qo'shish", callback_data="cat:new")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="cat:panel")],
        ]
    )


def category_management_list_keyboard(categories: Sequence[Category]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'🟢' if category.is_active else '🔴'} {category.name}",
                callback_data=f"cat:view:{category.id}",
            )
        ]
        for category in categories
    ]
    rows.append([InlineKeyboardButton(text="➕ Kategoriya qo'shish", callback_data="cat:new")])
    rows.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="cat:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_card_keyboard(category: Category) -> InlineKeyboardMarkup:
    toggle_text = "🔴 O'chirish (yashirish)" if category.is_active else "🟢 Yoqish"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data=f"cat:toggle:{category.id}")],
            [InlineKeyboardButton(text="🗑 Butunlay o'chirish", callback_data=f"cat:delete:{category.id}")],
            [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="cat:list")],
        ]
    )


def category_delete_confirm_keyboard(confirm_callback: str, cancel_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Ha, o'chirish", callback_data=confirm_callback),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data=cancel_callback),
            ]
        ]
    )
