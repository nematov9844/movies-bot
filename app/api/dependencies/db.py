"""FastAPI DB-session dependency, built on the shared session factory.

Routes depend on ``DbSession`` (or ``get_db_session`` directly) rather than
importing ``app.database.session`` themselves, keeping the FastAPI-specific
``Depends``/``Annotated`` plumbing in one place.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    async for session in get_session():
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
