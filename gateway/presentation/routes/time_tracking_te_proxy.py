"""Прокси записей времени → сервис time_tracking."""

from datetime import date
from decimal import Decimal
from typing import Any, Optional

import httpx
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from infrastructure.config import get_settings


def _base() -> str:
    settings = get_settings()
    base = (settings.time_tracking_service_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Time tracking service not configured")
    return base


class TimeEntryCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    work_date: date = Field(..., alias="workDate")
    hours: Decimal
    is_billable: bool = Field(True, alias="isBillable")
    project_id: Optional[str] = Field(None, alias="projectId")
    description: Optional[str] = None


class TimeEntryPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    work_date: Optional[date] = Field(None, alias="workDate")
    hours: Optional[Decimal] = None
    is_billable: Optional[bool] = Field(None, alias="isBillable")
    project_id: Optional[str] = Field(None, alias="projectId")
    description: Optional[str] = None


async def time_entries_list_gateway(auth_user_id: int, request: Request) -> Any:
    base = _base()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{base}/users/{auth_user_id}/time-entries",
                params=request.query_params,
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


async def time_entries_create_gateway(auth_user_id: int, body: TimeEntryCreateBody) -> Any:
    base = _base()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{base}/users/{auth_user_id}/time-entries",
                json=body.model_dump(mode="json", by_alias=False),
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


async def time_entries_patch_gateway(auth_user_id: int, entry_id: str, body: TimeEntryPatchBody) -> Any:
    base = _base()
    payload = body.model_dump(exclude_unset=True, mode="json", by_alias=False)
    if not payload:
        raise HTTPException(status_code=400, detail="Нет полей для обновления")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.patch(
                f"{base}/users/{auth_user_id}/time-entries/{entry_id}",
                json=payload,
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


async def time_entries_delete_gateway(auth_user_id: int, entry_id: str) -> Any:
    base = _base()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.delete(f"{base}/users/{auth_user_id}/time-entries/{entry_id}")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


class ProjectAccessPutBody(BaseModel):
    """Тело замены списка проектов с доступом (только projectIds; кто выдал — подставляет gateway)."""

    model_config = ConfigDict(populate_by_name=True)

    project_ids: list[str] = Field(default_factory=list, alias="projectIds")


async def project_access_get_gateway(auth_user_id: int) -> Any:
    base = _base()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(f"{base}/users/{auth_user_id}/project-access")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()


async def project_access_put_gateway(
    auth_user_id: int,
    body: ProjectAccessPutBody,
    *,
    granted_by_auth_user_id: int,
) -> Any:
    base = _base()
    payload = {
        "project_ids": list(body.project_ids),
        "granted_by_auth_user_id": granted_by_auth_user_id,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.put(
                f"{base}/users/{auth_user_id}/project-access",
                json=payload,
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Time tracking service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Time tracking service error")
    return r.json()
