import time
from collections import defaultdict

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/auth/admin", tags=["auth"])

# Rate limit: 5 попыток за 15 минут на IP
_ADMIN_LOGIN_LIMIT = 5
_ADMIN_LOGIN_WINDOW = 900  # 15 min
_admin_login_attempts: dict[str, list[float]] = defaultdict(list)


def _check_admin_rate_limit(client_ip: str) -> None:
    now = time.time()
    attempts = _admin_login_attempts[client_ip]
    attempts[:] = [t for t in attempts if now - t < _ADMIN_LOGIN_WINDOW]
    if len(attempts) >= _ADMIN_LOGIN_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again in 15 minutes.",
        )
    attempts.append(now)


class AdminLoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
async def admin_login(body: AdminLoginBody, request: Request):
    """Вход в админ-панель по логину и паролю (без Microsoft)."""
    client_ip = request.client.host if request.client else "unknown"
    _check_admin_rate_limit(client_ip)
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{settings.auth_service_url}/auth/admin-login",
                json={"username": body.username, "password": body.password},
            )
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise HTTPException(
            status_code=502,
            detail="Auth service unavailable",
        ) from e
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if r.status_code == 404:
        raise HTTPException(
            status_code=502,
            detail="Auth service does not support admin login. Rebuild and restart the auth service (docker-compose up -d --build auth).",
        )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Auth error")
    return r.json()
