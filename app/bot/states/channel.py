from aiogram.fsm.state import State, StatesGroup


class AddChannelStates(StatesGroup):
    """The admin `/panel` -> "📢 Kanallar" -> "Kanal qo'shish" wizard, one state per prompt."""

    waiting_for_channel = State()
    waiting_for_priority = State()
    waiting_for_join_limit = State()
    waiting_for_dates = State()
    waiting_for_daily_window = State()
    waiting_for_confirm = State()


class ChannelManageStates(StatesGroup):
    """The admin channel list -> edit-field flow.

    Only the free-text fields (priority/join_limit/dates/daily_window) enter
    a waiting state; ``is_required`` is answered entirely with inline
    yes/no buttons and never enters one, mirroring
    ``MovieManageStates.waiting_for_edit_value``.
    """

    waiting_for_edit_value = State()
