from aiogram.fsm.state import State, StatesGroup


class AddMovieStates(StatesGroup):
    """The admin `/panel` -> "Kino qo'shish" wizard, one state per prompt."""

    waiting_for_video = State()
    waiting_for_duplicate_confirm = State()
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_categories = State()
    waiting_for_premium = State()
    waiting_for_confirm = State()


class MovieManageStates(StatesGroup):
    """The admin find/edit/delete flow, triggered by `/panel` -> "Kinolar ro'yxati".

    Editing a single field (title/description/code) is a one free-text-reply
    round trip (``waiting_for_edit_value``, with which field and which
    movie's code stashed in FSM data); premium/active toggles are answered
    entirely with inline buttons and never enter a waiting state.
    """

    waiting_for_code = State()
    waiting_for_edit_value = State()
    waiting_for_edit_categories = State()


class SearchStates(StatesGroup):
    """The user-facing "🔍 Kino qidirish" -> "Nom bo'yicha qidirish" free-text search.

    Stays in ``waiting_for_query`` while the user browses paginated results
    (pagination is answered via inline buttons, not new text) so a fresh
    piece of text at any point is treated as a new search query.
    """

    waiting_for_query = State()
