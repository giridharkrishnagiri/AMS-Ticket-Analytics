import base64
import hashlib
import hmac
import json
import time
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings


PUBLIC_PATH_PREFIXES = (
    "/api/health",
    "/api/auth/login",
    "/docs",
    "/openapi.json",
    "/redoc",
)

PROTECTED_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def is_public_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES)


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign_payload(payload_part: str, secret_key: str) -> str:
    signature = hmac.new(
        secret_key.encode("utf-8"),
        payload_part.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _base64url_encode(signature)


def create_session_token(
    *,
    username: str,
    display_name: str,
    settings: Settings,
) -> str:
    issued_at = int(time.time())
    expires_at = issued_at + settings.app_session_duration_minutes * 60

    payload = {
        "sub": username,
        "display_name": display_name,
        "iat": issued_at,
        "exp": expires_at,
        "token_type": "asm_session",
    }

    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_part = _base64url_encode(payload_json.encode("utf-8"))
    signature_part = _sign_payload(payload_part, settings.app_session_secret_key)

    return f"{payload_part}.{signature_part}"


def verify_session_token(token: str, settings: Settings) -> dict[str, Any]:
    if not token or "." not in token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid session token.",
        )

    payload_part, signature_part = token.split(".", 1)
    expected_signature = _sign_payload(payload_part, settings.app_session_secret_key)

    if not hmac.compare_digest(signature_part, expected_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token signature.",
        )

    try:
        payload = json.loads(_base64url_decode(payload_part).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token payload.",
        ) from exc

    if payload.get("token_type") != "asm_session":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
        )

    expires_at = int(payload.get("exp", 0))

    if expires_at < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired.",
        )

    return payload


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None

    parts = authorization.strip().split(" ", 1)

    if len(parts) != 2:
        return None

    scheme, token = parts

    if scheme.lower() != "bearer":
        return None

    return token.strip() or None


def api_key_is_valid(x_api_key: str | None, settings: Settings) -> bool:
    if not settings.api_auth_enabled:
        return False

    if not settings.api_auth_key:
        return False

    return bool(x_api_key and hmac.compare_digest(x_api_key, settings.api_auth_key))


def session_token_is_valid(token: str | None, settings: Settings) -> bool:
    if not token:
        return False

    try:
        verify_session_token(token, settings)
        return True
    except HTTPException:
        return False


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.api_auth_enabled:
        return

    if not settings.auth_is_ready:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API authentication is enabled but API_AUTH_KEY is not configured.",
        )

    if not api_key_is_valid(x_api_key, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
        )


def require_authenticated_request(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    x_session_token: Annotated[str | None, Header(alias="X-Session-Token")] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if not settings.api_auth_enabled:
        return {
            "authenticated": False,
            "auth_type": "disabled",
            "username": None,
            "display_name": None,
        }

    if not settings.auth_is_ready:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API authentication is enabled but API_AUTH_KEY is not configured.",
        )

    if api_key_is_valid(x_api_key, settings):
        return {
            "authenticated": True,
            "auth_type": "api_key",
            "username": "api_key_user",
            "display_name": "API Key User",
        }

    bearer_token = extract_bearer_token(authorization)
    token = x_session_token or bearer_token

    if token:
        payload = verify_session_token(token, settings)
        return {
            "authenticated": True,
            "auth_type": "session",
            "username": payload.get("sub"),
            "display_name": payload.get("display_name"),
            "expires_at": payload.get("exp"),
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid API key or session token.",
    )