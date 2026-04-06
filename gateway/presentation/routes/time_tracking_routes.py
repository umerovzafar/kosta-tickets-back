"""Прокси к сервису time_tracking. Требует аутентификации."""

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from infrastructure.config import get_settings

from presentation.routes.time_tracking_hourly_proxy import (
    HourlyRateCreateBody,
    HourlyRatePatchBody,
    get_current_user,
    hourly_rates_create_gateway,
    hourly_rates_delete_gateway,
    hourly_rates_get_gateway,
    hourly_rates_list_gateway,
    hourly_rates_patch_gateway,
)

router = APIRouter(prefix="/api/v1/time-tracking", tags=["time_tracking"])


def require_view_role(user: dict = Depends(get_current_user)):
    role = (user.get("role") or "").strip()
    if role not in {
        "Главный администратор",
        "Администратор",
        "Партнер",
        "IT отдел",
        "Офис менеджер",
    }:
        raise HTTPException(
            status_code=403,
            detail="Only administrators and office managers can view time tracking users",
        )
    return user


def require_manage_role(user: dict = Depends(get_current_user)):
    role = (user.get("role") or "").strip()
    if role not in {"Главный администратор", "Администратор", "Партнер"}:
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


@router.get("/users/{auth_user_id}/hourly-rates")
async def list_hourly_rates(
    auth_user_id: int,
    kind: str = Query(..., description="billable | cost"),
    user: dict = Depends(get_current_user),
):
    return await hourly_rates_list_gateway(auth_user_id, kind, user)


@router.get("/users/{auth_user_id}/hourly-rates/{rate_id}")
async def get_hourly_rate(
    auth_user_id: int,
    rate_id: str,
    user: dict = Depends(get_current_user),
):
    return await hourly_rates_get_gateway(auth_user_id, rate_id, user)


@router.post("/users/{auth_user_id}/hourly-rates")
async def create_hourly_rate(
    auth_user_id: int,
    body: HourlyRateCreateBody,
    user: dict = Depends(get_current_user),
):
    return await hourly_rates_create_gateway(auth_user_id, body, user)


@router.patch("/users/{auth_user_id}/hourly-rates/{rate_id}")
async def patch_hourly_rate(
    auth_user_id: int,
    rate_id: str,
    body: HourlyRatePatchBody,
    user: dict = Depends(get_current_user),
):
    return await hourly_rates_patch_gateway(auth_user_id, rate_id, body, user)


@router.delete("/users/{auth_user_id}/hourly-rates/{rate_id}")
async def delete_hourly_rate(
    auth_user_id: int,
    rate_id: str,
    user: dict = Depends(get_current_user),
):
    return await hourly_rates_delete_gateway(auth_user_id, rate_id, user)


@router.get("/users")
async def list_users(_: dict = Depends(require_view_role)):
    settings = get_settings()
    base = (settings.time_tracking_service_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Time tracking service not configured")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base}/users")
    except httpx.RequestError:
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
    except httpx.RequestError:
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
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()
