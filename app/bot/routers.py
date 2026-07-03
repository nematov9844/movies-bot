from aiogram import Router

from app.bot.handlers.admin import admin_router
from app.bot.handlers.user import user_router

main_router = Router(name="main")

main_router.include_router(admin_router)
main_router.include_router(user_router)
