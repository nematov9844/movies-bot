"""Shared pytest fixtures (Phase 17).

Per the TZ: a dedicated ``movie_platform_test`` database (never the app's
real one), with every test wrapped in a transaction that's rolled back
afterward — including transactions any code-under-test itself commits,
via the standard SQLAlchemy "join an external transaction" recipe
(``session`` fixture below): a SAVEPOINT is restarted every time the
inner session's transaction ends, so a ``session.commit()`` inside a
service/route under test only ever commits to the SAVEPOINT, not to the
database, and the outer ``CONN.rollback()`` at teardown discards
everything.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine

import app.database.models  # noqa: F401  registers every model on Base.metadata
from app.core import security
from app.core.config import settings
from app.core.constants import AdminRole
from app.database.base import Base
from app.database.models import Admin, User

TEST_DATABASE_URL = (
    f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}"
    f"@{settings.postgres_host}:{settings.postgres_port}/movie_platform_test"
)


@pytest.fixture(scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    connection: AsyncConnection = await test_engine.connect()
    outer_transaction = await connection.begin()
    async_session = AsyncSession(bind=connection, expire_on_commit=False)

    nested = await connection.begin_nested()

    @event.listens_for(async_session.sync_session, "after_transaction_end")
    def _restart_savepoint(sync_session: object, transaction: object) -> None:
        nonlocal nested
        if not nested.is_active:
            nested = connection.sync_connection.begin_nested()

    try:
        yield async_session
    finally:
        await async_session.close()
        await outer_transaction.rollback()
        await connection.close()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """An httpx client wired to the real FastAPI app, but sharing ``session``'s test transaction."""
    from app.api.dependencies.db import get_db_session
    from app.api.rate_limit import limiter
    from app.api_main import app

    # The Limiter's in-memory storage is a process-wide singleton (module
    # level in app/api/rate_limit.py), so without a reset here, the 5/minute
    # login limit would carry over between tests instead of being scoped to
    # each one — tests that legitimately call /api/auth/login more than a
    # few times across a session would start seeing 429s that have nothing
    # to do with what that individual test is checking.
    limiter.reset()

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


DEFAULT_TEST_PASSWORD = "test-pass-123"


@pytest.fixture
def make_admin(session: AsyncSession) -> Callable[..., Awaitable[Admin]]:
    """Factory fixture: ``await make_admin(user_id, role=AdminRole.ADMIN)`` creates a logged-in-able admin."""

    async def _make(user_id: int, role: AdminRole = AdminRole.ADMIN, password: str = DEFAULT_TEST_PASSWORD) -> Admin:
        session.add(User(id=user_id))
        await session.flush()
        admin = Admin(
            user_id=user_id,
            role=role.value,
            password_hash=security.hash_password(password),
            is_active=True,
        )
        session.add(admin)
        await session.flush()
        return admin

    return _make
