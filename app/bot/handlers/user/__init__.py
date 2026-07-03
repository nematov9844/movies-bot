from aiogram import Router

from app.bot.handlers.user import invite as user_invite
from app.bot.handlers.user import profile as user_profile
from app.bot.handlers.user import settings as user_settings
from app.bot.handlers.user import start as user_start

user_router = Router(name="user")

user_router.include_router(user_start.router)
user_router.include_router(user_profile.router)
user_router.include_router(user_settings.router)
user_router.include_router(user_invite.router)

__all__ = ["user_router"]
