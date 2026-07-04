from aiogram.fsm.state import State, StatesGroup


class SeriesManageStates(StatesGroup):
    """The admin `/panel` -> "📺 Seriallar" wizard: new series -> new season -> bulk episode forward."""

    waiting_for_series_title = State()
    waiting_for_series_description = State()
    waiting_for_season_number = State()
    waiting_for_season_premium_choice = State()
    waiting_for_episode_forward = State()
