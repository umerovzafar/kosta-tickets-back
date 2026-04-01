"""Единые вызовы auth-сервиса из gateway (токен, прокси к /users, /roles, …)."""

from __future__ import annotations

from typing import Any, Optional

import httpx
from fastapi import HTTPException

from infrastructure.config import get_settings


def auth_service_base() -> str:
    return get_settings().auth_service_url.rstrip("/")


async def verify_bearer_and_get_user(authorization: Optional[str]) -> dict:
    """GET /users/me — валидный Bearer или 401/503."""
    if not authorization or not authorization.strip():
        raise HTTPException(status_code=401, detail="Authorization required")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{auth_service_base()}/users/me",
                headers={"Authorization": authorization},
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Auth service unavailable")
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code >= 400:
        raise HTTPException(status_code=503, detail="Auth service error")
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
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(method, url, headers=headers, **kwargs)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Auth service unavailable")
