from unittest.mock import AsyncMock

from app.bot.middlewares.menu_escape import MenuEscapeMiddleware
from app.tests.bot.helpers import make_message


async def test_clears_state_when_menu_button_text_arrives_mid_flow() -> None:
    """Regression guard: tapping a main-menu button while some other FSM wait state is
    active (e.g. the admin find-movie code prompt) must clear that state instead of
    letting it swallow the button's text as if it were data — otherwise the tap does
    nothing except reply with that state's "not found"/invalid-input message. Clearing
    just the FSMContext isn't enough — data["raw_state"] (the frozen snapshot every
    state-filtered handler's StateFilter actually compares against) has to be
    overwritten too, or the stale value still routes this same update to the old
    handler regardless of what state.clear() did to the backing storage."""
    message, _ = make_message(1, "🔍 Kino qidirish")
    state = AsyncMock()
    handler = AsyncMock(return_value="handled")
    data = {"state": state, "raw_state": "SomeStates:waiting_for_something"}

    result = await MenuEscapeMiddleware()(handler, message, data)

    state.clear.assert_awaited_once()
    assert data["raw_state"] is None
    handler.assert_awaited_once_with(message, data)
    assert result == "handled"


async def test_leaves_state_alone_when_no_state_is_set() -> None:
    message, _ = make_message(1, "🔍 Kino qidirish")
    state = AsyncMock()
    handler = AsyncMock(return_value="handled")
    data = {"state": state, "raw_state": None}

    await MenuEscapeMiddleware()(handler, message, data)

    state.clear.assert_not_awaited()


async def test_leaves_state_alone_for_unrelated_text() -> None:
    """Ordinary text (a movie code, a free-text search query, ...) is untouched — only
    an exact match on one of the main-menu's own button labels triggers the escape."""
    message, _ = make_message(1, "temir odam")
    state = AsyncMock()
    handler = AsyncMock(return_value="handled")
    data = {"state": state, "raw_state": "SomeStates:waiting_for_something"}

    await MenuEscapeMiddleware()(handler, message, data)

    state.clear.assert_not_awaited()
    assert data["raw_state"] == "SomeStates:waiting_for_something"
