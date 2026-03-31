"""Прокси к сервису расходов (expenses). Требует аутентификации."""

from typing import Any, Optional

import httpx
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/expenses", tags=["expenses"])


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


def _auth_headers(authorization: Optional[str]) -> dict[str, str]:
    return {"Authorization": authorization} if authorization else {}


def _base() -> str:
    settings = get_settings()
    base = (settings.expenses_service_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Expenses service not configured")
    return base


@router.get("/requests")
async def list_requests(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_base()}/requests",
                params=dict(request.query_params),
                headers=_auth_headers(authorization),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Expenses service error")
    return r.json()


@router.post("/requests")
async def create_request(
    body: dict[str, Any] = Body(...),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{_base()}/requests",
                json=body,
                headers=_auth_headers(authorization),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Expenses service error")
    return r.json()


@router.get("/requests/{request_id}")
async def get_request(
    request_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_base()}/requests/{request_id}",
                headers=_auth_headers(authorization),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Expenses service error")
    return r.json()


@router.patch("/requests/{request_id}")
async def patch_request(
    request_id: int,
    body: dict[str, Any] = Body(...),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.patch(
                f"{_base()}/requests/{request_id}",
                json=body,
                headers=_auth_headers(authorization),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Expenses service error")
    return r.json()


@router.post("/requests/{request_id}/submit")
async def submit_request(
    request_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{_base()}/requests/{request_id}/submit",
                headers=_auth_headers(authorization),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Expenses service error")
    return r.json()


class StatusBody(BaseModel):
    status: str
    rejection_reason: str | None = None


@router.patch("/requests/{request_id}/status")
async def set_status(
    request_id: int,
    body: StatusBody,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.patch(
                f"{_base()}/requests/{request_id}/status",
                json=body.model_dump(exclude_none=True),
                headers=_auth_headers(authorization),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Expenses service error")
    return r.json()


@router.post("/requests/{request_id}/attachments")
async def upload_attachment(
    request_id: int,
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    body = await request.body()
    ct = request.headers.get("content-type", "")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                f"{_base()}/requests/{request_id}/attachments",
                content=body,
                headers={**_auth_headers(authorization), "Content-Type": ct},
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Expenses service error")
    return r.json()


@router.delete("/requests/{request_id}/attachments/{attachment_id}")
async def delete_attachment(
    request_id: int,
    attachment_id: str,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.delete(
                f"{_base()}/requests/{request_id}/attachments/{attachment_id}",
                headers=_auth_headers(authorization),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Expenses service error")
    return r.json()


@router.get("/reports/summary")
async def report_summary(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_base()}/reports/summary",
                params=dict(request.query_params),
                headers=_auth_headers(authorization),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Expenses service error")
    return r.json()


@router.get("/reports/dynamics")
async def report_dynamics(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(
                f"{_base()}/reports/dynamics",
                params=dict(request.query_params),
                headers=_auth_headers(authorization),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Expenses service error")
    return r.json()


@router.get("/reports/calendar")
async def report_calendar(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_base()}/reports/calendar",
                params=dict(request.query_params),
                headers=_auth_headers(authorization),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Expenses service error")
    return r.json()


@router.get("/reports/by-date")
async def report_by_date(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                f"{_base()}/reports/by-date",
                params=dict(request.query_params),
                headers=_auth_headers(authorization),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Expenses service error")
    return r.json()
