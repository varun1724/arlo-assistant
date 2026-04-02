from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.calendar import router as calendar_router
from app.api.health_check import router as health_check_router
from app.api.chat import router as chat_router
from app.api.integrations import router as integrations_router
from app.api.goals import router as goals_router
from app.api.grocery import router as grocery_router
from app.api.knowledge import router as knowledge_router
from app.api.reminders import router as reminders_router
from app.api.habits import router as habits_router
from app.api.health import router as health_router
from app.api.recipes import router as recipes_router
from app.api.tasks import router as tasks_router
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.middleware import RequestLoggingMiddleware, ErrorHandlerMiddleware
from app.db.base import Base
from app.db.engine import engine
from app.db import models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    # Create tables (will be replaced by alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create default user for legacy API key auth
    from app.db.engine import async_session
    from app.db.models import UserRow
    from app.services.chat_service import DEFAULT_USER_ID

    async with async_session() as session:
        existing = await session.get(UserRow, DEFAULT_USER_ID)
        if not existing:
            session.add(UserRow(id=DEFAULT_USER_ID, name="User"))
            await session.commit()

    yield
    await engine.dispose()


app = FastAPI(title="Arlo Assistant", version="0.2.0", lifespan=lifespan)

# Middleware (order matters — first added = outermost)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_check_router)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(health_router)
app.include_router(tasks_router)
app.include_router(goals_router)
app.include_router(habits_router)
app.include_router(recipes_router)
app.include_router(grocery_router)
app.include_router(knowledge_router)
app.include_router(reminders_router)
app.include_router(calendar_router)
app.include_router(integrations_router)
