"""Прокси к сервису time_tracking. Требует аутентификации."""

from datetime import date
from decimal import Decimal
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from infrastructure.auth_upstream import verify_bearer_and_get_user
from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/time-tracking", tags=["time_tracking"])

ROLES_CAN_VIEW = {"Главный администратор", "Администратор", "Партнер", "IT отдел", "Офис менеджер"}
ROLES_CAN_MANAGE = {"Главный администратор", "Администратор", "Партнер"}
ROLES_ADMIN_ONLY = {"Главный администратор", "Администратор"}


async def get_current_user(authorization: Optional[str] = Header(None, alias="Authorization")):
    return await verify_bearer_and_get_user(authorization)


def _role(user: dict) -> str:
    return (user.get("role") or "").strip()


def _ensure_billable_rates_view(user: dict) -> None:
    if _role(user) not in ROLES_CAN_VIEW:
        raise HTTPException(
            status_code=403,
            detail="Оплачиваемые ставки доступны администраторам и менеджерам",
        )


def _ensure_cost_rates_view(user: dict) -> None:
    if _role(user) not in ROLES_ADMIN_ONLY:
        raise HTTPException(
            status_code=403,
            detail="Ставки себестоимости доступны только администраторам",
        )


def _ensure_manage_billable_rates(user: dict) -> None:
    if _role(user) not in ROLES_CAN_MANAGE:
        raise HTTPException(
            status_code=403,
            detail="Недостаточно прав для изменения оплачиваемых ставок",
        )


def _ensure_manage_cost_rates(user: dict) -> None:
    if _role(user) not in ROLES_ADMIN_ONLY:
        raise HTTPException(
            status_code=403,
            detail="Ставки себестоимости может менять только администратор",
        )


def _time_tracking_base() -> str:
    settings = get_settings()
    base = (settings.time_tracking_service_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Time tracking service not configured")
    return base


async def _tt_get_hourly_rate(base: str, auth_user_id: int, rate_id: str) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base}/users/{auth_user_id}/hourly-rates/{rate_id}")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code == 404:
        return None
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
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


class HourlyRateCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rate_kind: str = Field(..., alias="rateKind")
    amount: Decimal
    currency: str = "USD"
    valid_from: Optional[date] = Field(None, alias="validFrom")
    valid_to: Optional[date] = Field(None, alias="validTo")


class HourlyRatePatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    valid_from: Optional[date] = Field(None, alias="validFrom")
    valid_to: Optional[date] = Field(None, alias="validTo")


@router.get("/users/{auth_user_id}/hourly-rates")
async def list_hourly_rates(
    auth_user_id: int,
    kind: str = Query(..., description="billable | cost"),
    user: dict = Depends(get_current_user),
):
    if kind not in ("billable", "cost"):
        raise HTTPException(status_code=400, detail="kind must be billable or cost")
    if kind == "cost":
        _ensure_cost_rates_view(user)
    else:
        _ensure_billable_rates_view(user)
    base = _time_tracking_base()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base}/users/{auth_user_id}/hourly-rates", params={"kind": kind})
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.get("/users/{auth_user_id}/hourly-rates/{rate_id}")
async def get_hourly_rate(
    auth_user_id: int,
    rate_id: str,
    user: dict = Depends(get_current_user),
):
    base = _time_tracking_base()
    data = await _tt_get_hourly_rate(base, auth_user_id, rate_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Ставка не найдена")
    if data.get("rate_kind") == "cost":
        _ensure_cost_rates_view(user)
    else:
        _ensure_billable_rates_view(user)
    return data


@router.post("/users/{auth_user_id}/hourly-rates")
async def create_hourly_rate(
    auth_user_id: int,
    body: HourlyRateCreateBody,
    user: dict = Depends(get_current_user),
):
    rk = (body.rate_kind or "").strip()
    if rk == "cost":
        _ensure_manage_cost_rates(user)
    elif rk == "billable":
        _ensure_manage_billable_rates(user)
    else:
        raise HTTPException(status_code=400, detail="rateKind must be billable or cost")
    base = _time_tracking_base()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{base}/users/{auth_user_id}/hourly-rates",
                json=body.model_dump(mode="json", by_alias=False),
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.patch("/users/{auth_user_id}/hourly-rates/{rate_id}")
async def patch_hourly_rate(
    auth_user_id: int,
    rate_id: str,
    body: HourlyRatePatchBody,
    user: dict = Depends(get_current_user),
):
    base = _time_tracking_base()
    existing = await _tt_get_hourly_rate(base, auth_user_id, rate_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Ставка не найдена")
    if existing.get("rate_kind") == "cost":
        _ensure_manage_cost_rates(user)
    else:
        _ensure_manage_billable_rates(user)
    payload = body.model_dump(exclude_unset=True, mode="json")
    if not payload:
        raise HTTPException(status_code=400, detail="Нет полей для обновления")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.patch(
                f"{base}/users/{auth_user_id}/hourly-rates/{rate_id}",
                json=payload,
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.delete("/users/{auth_user_id}/hourly-rates/{rate_id}")
async def delete_hourly_rate(
    auth_user_id: int,
    rate_id: str,
    user: dict = Depends(get_current_user),
):
    base = _time_tracking_base()
    existing = await _tt_get_hourly_rate(base, auth_user_id, rate_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Ставка не найдена")
    if existing.get("rate_kind") == "cost":
        _ensure_manage_cost_rates(user)
    else:
        _ensure_manage_billable_rates(user)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.delete(f"{base}/users/{auth_user_id}/hourly-rates/{rate_id}")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


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
