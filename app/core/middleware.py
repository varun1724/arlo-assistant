"""Middleware — request logging, request ID, error handling."""

import logging
import time
import uuid

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import AppError

logger = logging.getLogger("arlo.assistant.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with timing and inject X-Request-ID."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        start = time.time()

        response = await call_next(request)

        duration_ms = (time.time() - start) * 1000
        response.headers["X-Request-ID"] = request_id

        logger.info(
            "%s %s %d %.0fms [%s]",
            request.method, request.url.path, response.status_code,
            duration_ms, request_id,
        )
        return response


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return standardized error responses."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except AppError as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"error": {"code": e.code, "message": e.message}},
            )
        except Exception as e:
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=500,
                content={"error": {"code": "internal_error", "message": "An unexpected error occurred"}},
            )
