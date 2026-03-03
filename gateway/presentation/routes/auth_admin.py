from fastapi import APIRouter, HTTPException
import httpx
from pydantic import BaseModel
from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/auth/admin", tags=["auth"])


class AdminLoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
async def admin_login(body: AdminLoginBody):
    """Вход в админ-панель по логину и паролю (без Microsoft)."""
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
