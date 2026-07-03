from aiogram import Router

from app.bot.handlers.admin import auth as admin_auth
from app.bot.handlers.admin import channel_add as admin_channel_add
from app.bot.handlers.admin import channel_manage as admin_channel_manage
from app.bot.handlers.admin import movie_add as admin_movie_add
from app.bot.handlers.admin import movie_manage as admin_movie_manage
from app.bot.handlers.admin import panel as admin_panel
from app.bot.handlers.admin import premium_grant as admin_premium_grant

admin_router = Router(name="admin")

admin_router.include_router(admin_auth.router)
admin_router.include_router(admin_panel.router)
admin_router.include_router(admin_movie_add.router)
admin_router.include_router(admin_movie_manage.router)
admin_router.include_router(admin_channel_add.router)
admin_router.include_router(admin_channel_manage.router)
admin_router.include_router(admin_premium_grant.router)

__all__ = ["admin_router"]
