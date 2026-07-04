from aiogram.fsm.state import State, StatesGroup


class EditSettingStates(StatesGroup):
    """The admin `/panel` -> "⚙️ Sozlamalar" -> free-text edit flow (welcome_text/support_username)."""

    waiting_for_value = State()
