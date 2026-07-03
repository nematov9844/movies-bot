from aiogram.fsm.state import State, StatesGroup


class GrantPremiumStates(StatesGroup):
    """The admin `/panel` -> "⭐ Premium" -> "Premium berish" wizard, one state per prompt."""

    waiting_for_user_id = State()
    waiting_for_plan = State()
    waiting_for_confirm = State()
