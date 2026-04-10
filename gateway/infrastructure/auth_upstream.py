"""Единые вызовы auth-сервиса из gateway (токен, прокси к /users, /roles, …)."""

from __future__ import annotations

from typing import Any, Optional

import httpx
from fastapi import HTTPException

from infrastructure.config import get_settings
from infrastructure.upstream_http import (
    raise_for_upstream_status,
    send_upstream_request,
    service_base_url,
)


def auth_service_base() -> str:
    return service_base_url(get_settings().auth_service_url, "Auth")


async def verify_bearer_and_get_user(authorization: Optional[str]) -> dict:
    """GET /users/me — валидный Bearer или 401/503."""
    if not authorization or not authorization.strip():
        raise HTTPException(status_code=401, detail="Authorization required")
    r = await send_upstream_request(
        "GET",
        f"{auth_service_base()}/users/me",
        headers={"Authorization": authorization},
        timeout=10.0,
        unavailable_status=503,
        unavailable_detail="Auth service unavailable",
    )
    raise_for_upstream_status(
        r,
        "Auth service error",
        status_detail_map={
            401: "Invalid or expired token",
        },
    )
    return r.json()


async def auth_service_request(
    method: str,
    path: str,
    authorization: Optional[str],
    *,
    timeout: float = 30.0,
    **kwargs: Any,
) -> httpx.Response:
    """HTTP-запрос к auth. path с ведущим слэшем, например /users или /roles/1."""
    base = auth_service_base()
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base}{path}"
    headers = dict(kwargs.pop("headers", None) or {})
    if authorization:
        headers["Authorization"] = authorization
    return await send_upstream_request(
        method,
        url,
        headers=headers,
        timeout=timeout,
        unavailable_status=503,
        unavailable_detail="Auth service unavailable",
        **kwargs,
    )
