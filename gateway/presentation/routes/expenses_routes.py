"""Прокси к сервису расходов (expenses). Требует аутентификации."""

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["expenses"])


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


def _strip_hop(headers: dict) -> dict:
    skip = {
        "connection",
        "keep-alive",
        "transfer-encoding",
        "content-encoding",
        "host",
    }
    return {k: v for k, v in headers.items() if k.lower() not in skip}


async def _forward(
    request: Request,
    upstream_path: str,
    authorization: Optional[str],
    timeout: float = 120.0,
) -> Response:
    url = f"{_base()}/{upstream_path.lstrip('/')}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    body = await request.body()
    headers = _strip_hop(dict(request.headers))
    headers.pop("host", None)
    if authorization:
        headers["Authorization"] = authorization
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Expenses service unavailable")
    resp_headers = {k: v for k, v in r.headers.items() if k.lower() not in ("connection", "transfer-encoding")}
    return Response(content=r.content, status_code=r.status_code, headers=resp_headers)


# --- Заявки /expenses ---


@router.api_route("/expenses", methods=["GET", "POST"])
async def proxy_expenses_root(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    return await _forward(request, "expenses", authorization, timeout=60.0)


@router.api_route("/expenses/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_expenses_subpath(
    path: str,
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    return await _forward(request, f"expenses/{path}", authorization, timeout=120.0)


# --- Справочники (корень сервиса expenses) ---


@router.get("/expense-types")
async def proxy_expense_types(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    return await _forward(request, "expense-types", authorization, timeout=30.0)


@router.get("/departments")
async def proxy_departments(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    return await _forward(request, "departments", authorization, timeout=30.0)


@router.get("/projects")
async def proxy_projects(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    return await _forward(request, "projects", authorization, timeout=30.0)


@router.get("/exchange-rates")
async def proxy_exchange_rates(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    return await _forward(request, "exchange-rates", authorization, timeout=30.0)
