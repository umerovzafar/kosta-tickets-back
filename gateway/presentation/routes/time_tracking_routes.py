"""Прокси к сервису time_tracking. Требует аутентификации."""

import json
from decimal import Decimal
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from infrastructure.config import get_settings
from presentation.schemas.time_manager_clients import (
    TimeManagerClientCreateBody,
    TimeManagerClientPatchBody,
)
from presentation.schemas.time_manager_client_expense_categories import (
    TimeManagerClientExpenseCategoryCreateBody,
    TimeManagerClientExpenseCategoryPatchBody,
)
from presentation.schemas.time_manager_client_tasks import (
    TimeManagerClientTaskCreateBody,
    TimeManagerClientTaskPatchBody,
)

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
from presentation.routes.time_tracking_te_proxy import (
    TimeEntryCreateBody,
    TimeEntryPatchBody,
    time_entries_create_gateway,
    time_entries_delete_gateway,
    time_entries_list_gateway,
    time_entries_patch_gateway,
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
    """Тело синхронизации пользователя. Принимает snake_case и camelCase; в time_tracking уходит JSON с snake_case."""

    model_config = ConfigDict(populate_by_name=True)

    auth_user_id: int = Field(..., alias="authUserId")
    email: str
    display_name: Optional[str] = Field(None, alias="displayName")
    picture: Optional[str] = None
    role: str = ""
    is_blocked: bool = Field(False, alias="isBlocked")
    is_archived: bool = Field(False, alias="isArchived")
    weekly_capacity_hours: Optional[Decimal] = Field(None, alias="weeklyCapacityHours")


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


@router.get("/team-workload")
async def proxy_team_workload(request: Request, _: dict = Depends(require_view_role)):
    settings = get_settings()
    base = (settings.time_tracking_service_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Time tracking service not configured")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(f"{base}/team-workload", params=request.query_params)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.get("/users/{auth_user_id}/time-entries")
async def proxy_list_time_entries(
    auth_user_id: int,
    request: Request,
    _: dict = Depends(require_view_role),
):
    return await time_entries_list_gateway(auth_user_id, request)


@router.post("/users/{auth_user_id}/time-entries")
async def proxy_create_time_entry(
    auth_user_id: int,
    body: TimeEntryCreateBody,
    _: dict = Depends(require_manage_role),
):
    return await time_entries_create_gateway(auth_user_id, body)


@router.patch("/users/{auth_user_id}/time-entries/{entry_id}")
async def proxy_patch_time_entry(
    auth_user_id: int,
    entry_id: str,
    body: TimeEntryPatchBody,
    _: dict = Depends(require_manage_role),
):
    return await time_entries_patch_gateway(auth_user_id, entry_id, body)


@router.delete("/users/{auth_user_id}/time-entries/{entry_id}")
async def proxy_delete_time_entry(
    auth_user_id: int,
    entry_id: str,
    _: dict = Depends(require_manage_role),
):
    return await time_entries_delete_gateway(auth_user_id, entry_id)


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
        payload = json.loads(body.model_dump_json(by_alias=False))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Invalid user upsert payload: {e}") from e
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{base}/users", json=payload)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


def _time_tracking_base_url() -> str:
    settings = get_settings()
    base = (settings.time_tracking_service_url or "").strip().rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Time tracking service not configured")
    return base


@router.get("/clients")
async def list_time_manager_clients(_: dict = Depends(require_view_role)):
    base = _time_tracking_base_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base}/clients")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.get("/clients/{client_id}/tasks")
async def list_client_tasks(client_id: str, _: dict = Depends(require_view_role)):
    base = _time_tracking_base_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base}/clients/{client_id}/tasks")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.get("/clients/{client_id}/tasks/{task_id}")
async def get_client_task(
    client_id: str,
    task_id: str,
    _: dict = Depends(require_view_role),
):
    base = _time_tracking_base_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base}/clients/{client_id}/tasks/{task_id}")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.post("/clients/{client_id}/tasks")
async def create_client_task(
    client_id: str,
    body: TimeManagerClientTaskCreateBody,
    _: dict = Depends(require_manage_role),
):
    base = _time_tracking_base_url()
    try:
        payload = json.loads(body.model_dump_json(by_alias=False))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Invalid task payload: {e}") from e
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{base}/clients/{client_id}/tasks", json=payload)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.patch("/clients/{client_id}/tasks/{task_id}")
async def patch_client_task(
    client_id: str,
    task_id: str,
    body: TimeManagerClientTaskPatchBody,
    _: dict = Depends(require_manage_role),
):
    base = _time_tracking_base_url()
    try:
        payload = json.loads(body.model_dump_json(by_alias=False))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Invalid task payload: {e}") from e
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.patch(f"{base}/clients/{client_id}/tasks/{task_id}", json=payload)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.delete("/clients/{client_id}/tasks/{task_id}", status_code=204)
async def delete_client_task(
    client_id: str,
    task_id: str,
    _: dict = Depends(require_manage_role),
):
    base = _time_tracking_base_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.delete(f"{base}/clients/{client_id}/tasks/{task_id}")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return None


@router.get("/clients/{client_id}/expense-categories")
async def list_client_expense_categories(
    client_id: str,
    include_archived: bool = Query(False, alias="includeArchived"),
    _: dict = Depends(require_view_role),
):
    base = _time_tracking_base_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{base}/clients/{client_id}/expense-categories",
                params={"includeArchived": "true" if include_archived else "false"},
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.get("/clients/{client_id}/expense-categories/{category_id}")
async def get_client_expense_category(
    client_id: str,
    category_id: str,
    _: dict = Depends(require_view_role),
):
    base = _time_tracking_base_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base}/clients/{client_id}/expense-categories/{category_id}")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.post("/clients/{client_id}/expense-categories")
async def create_client_expense_category(
    client_id: str,
    body: TimeManagerClientExpenseCategoryCreateBody,
    _: dict = Depends(require_manage_role),
):
    base = _time_tracking_base_url()
    try:
        payload = json.loads(body.model_dump_json(by_alias=False))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Invalid expense category payload: {e}") from e
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{base}/clients/{client_id}/expense-categories", json=payload)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.patch("/clients/{client_id}/expense-categories/{category_id}")
async def patch_client_expense_category(
    client_id: str,
    category_id: str,
    body: TimeManagerClientExpenseCategoryPatchBody,
    _: dict = Depends(require_manage_role),
):
    base = _time_tracking_base_url()
    try:
        payload = json.loads(body.model_dump_json(by_alias=False))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Invalid expense category payload: {e}") from e
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.patch(
                f"{base}/clients/{client_id}/expense-categories/{category_id}",
                json=payload,
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.delete("/clients/{client_id}/expense-categories/{category_id}", status_code=204)
async def delete_client_expense_category(
    client_id: str,
    category_id: str,
    _: dict = Depends(require_manage_role),
):
    base = _time_tracking_base_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.delete(f"{base}/clients/{client_id}/expense-categories/{category_id}")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return None


@router.get("/clients/{client_id}")
async def get_time_manager_client(client_id: str, _: dict = Depends(require_view_role)):
    base = _time_tracking_base_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base}/clients/{client_id}")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.post("/clients")
async def create_time_manager_client(
    body: TimeManagerClientCreateBody,
    _: dict = Depends(require_manage_role),
):
    base = _time_tracking_base_url()
    try:
        payload = json.loads(body.model_dump_json(by_alias=False))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Invalid client payload: {e}") from e
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{base}/clients", json=payload)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.patch("/clients/{client_id}")
async def patch_time_manager_client(
    client_id: str,
    body: TimeManagerClientPatchBody,
    _: dict = Depends(require_manage_role),
):
    base = _time_tracking_base_url()
    try:
        payload = json.loads(body.model_dump_json(by_alias=False))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Invalid client payload: {e}") from e
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.patch(f"{base}/clients/{client_id}", json=payload)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


@router.delete("/clients/{client_id}", status_code=204)
async def delete_time_manager_client(client_id: str, _: dict = Depends(require_manage_role)):
    base = _time_tracking_base_url()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.delete(f"{base}/clients/{client_id}")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return None


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
