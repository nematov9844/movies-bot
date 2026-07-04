from aiogram import Router

from app.bot.handlers.admin import auth as admin_auth
from app.bot.handlers.admin import broadcast as admin_broadcast
from app.bot.handlers.admin import channel_add as admin_channel_add
from app.bot.handlers.admin import channel_manage as admin_channel_manage
from app.bot.handlers.admin import movie_add as admin_movie_add
from app.bot.handlers.admin import movie_manage as admin_movie_manage
from app.bot.handlers.admin import panel as admin_panel
from app.bot.handlers.admin import premium_grant as admin_premium_grant
from app.bot.handlers.admin import settings as admin_settings
from app.bot.handlers.admin import stats as admin_stats

admin_router = Router(name="admin")

admin_router.include_router(admin_auth.router)
admin_router.include_router(admin_panel.router)
admin_router.include_router(admin_movie_add.router)
admin_router.include_router(admin_movie_manage.router)
admin_router.include_router(admin_channel_add.router)
admin_router.include_router(admin_channel_manage.router)
admin_router.include_router(admin_premium_grant.router)
admin_router.include_router(admin_broadcast.router)
admin_router.include_router(admin_stats.router)
admin_router.include_router(admin_settings.router)

__all__ = ["admin_router"]
