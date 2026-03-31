"""Прокси к сервису time_tracking. Требует аутентификации."""

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/time-tracking", tags=["time_tracking"])

ROLES_CAN_VIEW = {"Главный администратор", "Администратор", "Партнер", "IT отдел", "Офис менеджер"}
ROLES_CAN_MANAGE = {"Главный администратор", "Администратор", "Партнер"}


async def get_current_user(authorization: Optional[str] = Header(None, alias="Authorization")):
    if not authorization or not authorization.strip():
        raise HTTPException(status_code=401, detail="Authorization required")
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{settings.auth_service_url}/users/me",
                headers={"Authorization": authorization},
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Auth service unavailable")
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    r.raise_for_status()
    return r.json()


def require_view_role(user: dict = Depends(get_current_user)):
    role = (user.get("role") or "").strip()
    if role not in ROLES_CAN_VIEW:
        raise HTTPException(
            status_code=403,
            detail="Only administrators and office managers can view time tracking users",
        )
    return user


def require_manage_role(user: dict = Depends(get_current_user)):
    role = (user.get("role") or "").strip()
    if role not in ROLES_CAN_MANAGE:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can update or delete time tracking users",
        )
    return user


class UserUpsertBody(BaseModel):
    auth_user_id: int
    email: str
    display_name: Optional[str] = None
    picture: Optional[str] = None
    role: str = ""
    is_blocked: bool = False
    is_archived: bool = False


@router.get("/users")
async def list_users(_: dict = Depends(require_view_role)):
    settings = get_settings()
    base = (settings.time_tracking_service_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Time tracking service not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base}/users")
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.post("/users")
async def upsert_user(
    body: UserUpsertBody,
    _: dict = Depends(require_manage_role),
):
    settings = get_settings()
    base = (settings.time_tracking_service_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Time tracking service not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{base}/users", json=body.model_dump())
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.delete("/users/{auth_user_id}")
async def delete_user(
    auth_user_id: int,
    _: dict = Depends(require_manage_role),
):
    settings = get_settings()
    base = (settings.time_tracking_service_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Time tracking service not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.delete(f"{base}/users/{auth_user_id}")
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()
