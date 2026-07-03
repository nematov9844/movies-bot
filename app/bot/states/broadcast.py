from aiogram.fsm.state import State, StatesGroup


class BroadcastStates(StatesGroup):
    """The admin `/panel` -> "📣 Broadcast" compose/target/confirm wizard, one state per prompt."""

    waiting_for_message = State()
    waiting_for_target = State()
    waiting_for_confirm = State()
