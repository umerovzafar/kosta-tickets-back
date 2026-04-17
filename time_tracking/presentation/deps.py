"""Проверка JWT через auth (как в expenses) — для админ-операций."""

from __future__ import annotations

from typing import Optional

import httpx
from fastapi import Header, HTTPException

from infrastructure.config import get_settings

MAIN_ADMIN_ROLE = "Главный администратор"


async def get_current_user(authorization: Optional[str] = Header(None, alias="Authorization")):
    if not authorization or not authorization.strip():
        raise HTTPException(status_code=401, detail="Authorization required")
    settings = get_settings()
    base = settings.auth_service_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{base}/users/me", headers={"Authorization": authorization})
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Auth service unavailable")
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code >= 400:
        raise HTTPException(status_code=503, detail="Auth service error")
    return r.json()


def check_main_admin(user: dict) -> None:
    if (user.get("role") or "").strip() != MAIN_ADMIN_ROLE:
        raise HTTPException(
            status_code=403,
            detail="Действие доступно только главному администратору",
        )
