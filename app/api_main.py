from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, health
from app.core.config import settings
from app.core.logger import get_logger, setup_logging
from app.database.session import async_session_factory
from app.services.admin.admin_service import AdminService

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("api_starting", environment=settings.environment)
    async with async_session_factory() as session:
        await AdminService(session).ensure_owner_seeded()
        await session.commit()
    yield
    logger.info("api_stopping")


app = FastAPI(title="Movie Platform API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
