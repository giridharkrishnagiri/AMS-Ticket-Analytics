import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.security import (
    api_key_is_valid,
    extract_bearer_token,
    is_public_path,
    session_token_is_valid,
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        settings = get_settings()

        if not settings.log_requests:
            return await call_next(request)

        start = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        print(
            f"{request.method} {request.url.path} "
            f"status={response.status_code} duration_ms={duration_ms}"
        )

        return response


class ApiKeyProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        settings = get_settings()

        if not settings.api_auth_enabled:
            return await call_next(request)

        if is_public_path(request.url.path):
            return await call_next(request)

        if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await call_next(request)

        if not settings.auth_is_ready:
            return Response(
                content='{"detail":"API authentication is enabled but API_AUTH_KEY is not configured."}',
                media_type="application/json",
                status_code=500,
            )

        x_api_key = request.headers.get("X-API-Key")

        if api_key_is_valid(x_api_key, settings):
            return await call_next(request)

        x_session_token = request.headers.get("X-Session-Token")
        bearer_token = extract_bearer_token(request.headers.get("Authorization"))
        session_token = x_session_token or bearer_token

        if session_token_is_valid(session_token, settings):
            return await call_next(request)

        return Response(
            content='{"detail":"Missing or invalid API key or session token."}',
            media_type="application/json",
            status_code=401,
        )