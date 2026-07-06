from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str = Field(...)
    storage_channel_id: int = Field(...)
    owner_id: int = Field(...)

    # Postgres
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "movie"
    postgres_password: str = Field(...)
    postgres_db: str = "movie_platform"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    jwt_secret: str = Field(...)
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7
    # Comma-separated browser origins allowed to call the API cross-origin —
    # the web admin panel lives on its own subdomain (per Phase 18's nginx
    # config, e.g. panel.domain.uz calling api.domain.uz), so this can't
    # just be "debug ? * : []"; production needs its real origin(s) listed
    # here explicitly. Empty in dev is fine since `debug=True` already
    # allows "*" regardless of this value.
    cors_origins: str = ""

    # General
    debug: bool = False
    environment: str = "production"
    sentry_dsn: str | None = None
    timezone: str = "Asia/Tashkent"

    # Caption parser (Phase: AI-assisted series/season/episode extraction).
    # Optional — CaptionParserService works deterministically (regex-only)
    # without this; it's only used as a fallback to fill fields the regex
    # layer left null. Unset in dev/test is fine.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    # Comma-separated public channel usernames (no "@") the bot auto-relays
    # new video posts from into the storage channel for parsing — e.g. the
    # admin's own movie/anime channels, once the bot is added there as
    # admin. Empty by default: this feature does nothing until configured.
    # A one-off userbot script (scripts/backfill_channels.py) separately
    # covers each channel's *existing* history, which the Bot API can never
    # read regardless of this setting.
    source_channels: str = ""

    # Userbot credentials (my.telegram.org) — only read by
    # scripts/backfill_channels.py, never by the bot/API/admin-panel
    # processes. Needed because the Bot API cannot read a channel's history
    # from before the bot joined; a real user session can.
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None

    @computed_field
    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @computed_field
    @property
    def source_channels_list(self) -> list[str]:
        return [c.strip().lstrip("@").lower() for c in self.source_channels.split(",") if c.strip()]

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
