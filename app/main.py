import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

_req_logger = logging.getLogger("arlo.assistant.request")

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


_DEFAULT_SECRET_VALUES = {
    "jwt_secret": "dev-jwt-secret-change-in-production",
    "api_key": "arlo-assistant-dev-key",
    "arlo_runtime_token": "change-me-to-a-real-secret",
}


def _audit_secrets() -> None:
    """Warn loudly (dev) or refuse to boot (prod) if any sensitive value is
    still the shipping default. The intent is to stop an operator from
    accidentally exposing a container on the Tailscale network with the
    committed dev JWT secret.
    """
    audit_log = logging.getLogger("arlo.assistant.security")
    offenders = [
        field for field, default in _DEFAULT_SECRET_VALUES.items()
        if getattr(settings, field, None) == default
    ]
    if not offenders:
        return
    message = (
        "Sensitive settings still hold the shipped default value: "
        + ", ".join(offenders)
        + ". Rotate before exposing this service publicly."
    )
    if settings.environment == "production":
        raise RuntimeError(message)
    for field in offenders:
        audit_log.warning("%s is using the default shipped value.", field)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    _audit_secrets()

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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body_bytes = b""
    try:
        body_bytes = await request.body()
    except Exception:
        pass
    _req_logger.error(
        "422 on %s %s | errors=%s | raw_body=%r",
        request.method, request.url.path, exc.errors(), body_bytes[:2000],
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


# Middleware (order matters — first added = outermost)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
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
