from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health_check import router as health_router
from app.api.chat import router as chat_router
from app.db.base import Base
from app.db.engine import engine
from app.db import models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create default user if not exists
    from app.db.engine import async_session
    from app.db.models import UserRow
    from app.services.chat_service import DEFAULT_USER_ID
    from sqlalchemy import select

    async with async_session() as session:
        existing = await session.get(UserRow, DEFAULT_USER_ID)
        if not existing:
            session.add(UserRow(id=DEFAULT_USER_ID, name="User"))
            await session.commit()

    yield
    await engine.dispose()


app = FastAPI(title="Arlo Assistant", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(chat_router)
