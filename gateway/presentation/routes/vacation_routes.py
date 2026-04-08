"""Прокси к сервису vacation (график отсутствий). Требует аутентификации."""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from infrastructure.auth_upstream import verify_bearer_and_get_user
from infrastructure.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/vacations", tags=["vacations"])

ROLES_CAN_VIEW = {
    "Главный администратор",
    "Администратор",
    "Партнер",
    "IT отдел",
    "Офис менеджер",
    "Сотрудник",
}


async def get_current_user(authorization: Optional[str] = Header(None, alias="Authorization")):
    user = await verify_bearer_and_get_user(authorization)
    role = (user.get("role") or "").strip()
    if role not in ROLES_CAN_VIEW:
        raise HTTPException(
            status_code=403,
            detail="Only authenticated staff roles can view the absence schedule",
        )
    return user


def _strip_hop(headers: dict) -> dict:
    skip = {
        "connection",
        "keep-alive",
        "transfer-encoding",
        "content-encoding",
        "host",
    }
    return {k: v for k, v in headers.items() if k.lower() not in skip}


def _base() -> str:
    settings = get_settings()
    base = (settings.vacation_service_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Vacation service not configured")
    return base


async def _forward(
    request: Request,
    upstream_path: str,
    authorization: Optional[str],
    timeout: float = 60.0,
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
    except httpx.RequestError as e:
        logger.warning("vacation upstream request failed: url=%s err=%s", url, e)
        raise HTTPException(
            status_code=503,
            detail="Vacation service unavailable. Check VACATION_SERVICE_URL and the vacation container.",
        )
    resp_headers = {k: v for k, v in r.headers.items() if k.lower() not in ("connection", "transfer-encoding")}
    return Response(content=r.content, status_code=r.status_code, headers=resp_headers)


@router.api_route("/{path:path}", methods=["GET"])
async def proxy_vacation(
    path: str,
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(get_current_user),
):
    return await _forward(request, path, authorization, timeout=60.0)
