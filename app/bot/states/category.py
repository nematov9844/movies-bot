from aiogram.fsm.state import State, StatesGroup


class CategoryManageStates(StatesGroup):
    """The admin `/panel` -> "🗂 Kategoriyalar" -> "➕ Kategoriya qo'shish" one-step wizard."""

    waiting_for_name = State()
