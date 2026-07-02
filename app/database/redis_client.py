from functools import lru_cache

from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings


@lru_cache
def get_redis_pool() -> ConnectionPool:
    return ConnectionPool.from_url(settings.redis_url, decode_responses=True)


def get_redis() -> Redis:
    return Redis(connection_pool=get_redis_pool())
