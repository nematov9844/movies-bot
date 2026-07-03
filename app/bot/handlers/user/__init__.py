from aiogram import Router

from app.bot.handlers.user import force_subscribe as user_force_subscribe
from app.bot.handlers.user import invite as user_invite
from app.bot.handlers.user import movie as user_movie
from app.bot.handlers.user import movie_search as user_movie_search
from app.bot.handlers.user import profile as user_profile
from app.bot.handlers.user import settings as user_settings
from app.bot.handlers.user import start as user_start

user_router = Router(name="user")

user_router.include_router(user_start.router)
user_router.include_router(user_profile.router)
user_router.include_router(user_settings.router)
user_router.include_router(user_invite.router)
# Not content-gated: must always be reachable so a blocked user can retry.
user_router.include_router(user_force_subscribe.router)
# Browse submenu (exact-text "🔍 Kino qidirish" button + its own FSM-scoped
# search-query handler) must come before the movie-code catch-all below, so
# a free-text search query is never misread as a code lookup and vice versa.
user_router.include_router(user_movie_search.router)
# Movie-code catch-all: registered last so every exact reply-menu-button
# handler above gets first refusal on the text before this broader pattern
# match is tried.
user_router.include_router(user_movie.router)

__all__ = ["user_router"]
