"""Прокси: сброс бизнес-данных time_tracking (только главный администратор)."""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from infrastructure.config import get_settings
from infrastructure.upstream_http import service_base_url
from presentation.routes.users import require_main_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _tt_base() -> str:
    return service_base_url(get_settings().time_tracking_service_url, "Time tracking")


def _strip_hop(headers: dict) -> dict:
    skip = {"connection", "keep-alive", "transfer-encoding", "content-encoding", "host"}
    return {k: v for k, v in headers.items() if k.lower() not in skip}


@router.post("/time-tracking/business-data/reset")
async def proxy_time_tracking_business_reset(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_main_admin),
):
    """Прокси на time_tracking: POST /admin/time-tracking/business-data/reset."""
    url = f"{_tt_base()}/admin/time-tracking/business-data/reset"
    body = await request.body()
    headers = _strip_hop(dict(request.headers))
    headers.pop("host", None)
    if authorization:
        headers["Authorization"] = authorization
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.request(method="POST", url=url, headers=headers, content=body)
    except httpx.RequestError as e:
        logger.warning("time_tracking reset upstream failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Time tracking service unavailable",
        ) from e
    resp_headers = {k: v for k, v in r.headers.items() if k.lower() not in ("connection", "transfer-encoding")}
    return Response(content=r.content, status_code=r.status_code, headers=resp_headers)
