from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

# Every reply-keyboard button text in main_menu_keyboard() — the only
# ReplyKeyboardMarkup in the bot, so this list is exhaustive by construction.
MAIN_MENU_BUTTON_TEXTS = frozenset(
    {
        "🔍 Kino qidirish",
        "👤 Profil",
        "⭐ Premium",
        "⚙️ Sozlamalar",
        "🎁 Do'stlarni taklif qilish",
    }
)


class MenuEscapeMiddleware(BaseMiddleware):
    """Tapping a persistent main-menu button must always navigate there — even mid-flow.

    Without this, a stray FSM wait state (the admin find-movie code prompt, an add-movie
    wizard step, ...) intercepts the button's literal text as if it were data for
    whatever that state was waiting on, replies with something like "not found", and the
    tap silently does nothing. Registered as an *outer* middleware on ``dp.message`` so
    it runs before aiogram matches the update against any state-filtered handler —
    clearing the state here lets the plain ``F.text == "..."`` menu handlers (which carry
    no state filter) take over normally, exactly as if the user had a clean session.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text in MAIN_MENU_BUTTON_TEXTS and data.get("raw_state"):
            state: FSMContext = data["state"]
            await state.clear()
            # aiogram's own FSMContextMiddleware (which runs before any
            # user-registered outer middleware) snapshots the state string
            # into data["raw_state"] once, up front — every state-filtered
            # handler's ``StateFilter`` compares against *that* frozen value
            # via dependency injection, not a fresh ``state.get_state()``
            # call. Clearing the FSMContext's backing storage above updates
            # future requests but not this already-captured one, so it has
            # to be overwritten here too or the stale snapshot still routes
            # this update into whatever handler the old state pointed at.
            data["raw_state"] = None
        return await handler(event, data)
