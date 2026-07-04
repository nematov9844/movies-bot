"""Sentry init shared by the bot and API — a no-op whenever ``SENTRY_DSN`` isn't set.

Called once at process startup, before anything that could raise. Sentry's
FastAPI/Starlette integrations auto-enable from ``sentry_sdk.init()`` alone
(no explicit integration object needed) as long as init happens before the
``FastAPI()`` app is constructed; aiogram has no such integration, so the
bot's global error handler explicitly calls ``sentry_sdk.capture_exception``
on top of this.
"""

import sentry_sdk

from app.core.config import settings


def setup_sentry() -> None:
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, traces_sample_rate=0.0)
