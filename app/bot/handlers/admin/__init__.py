from aiogram import Router

from app.bot.handlers.admin import auth as admin_auth

admin_router = Router(name="admin")

admin_router.include_router(admin_auth.router)

__all__ = ["admin_router"]
