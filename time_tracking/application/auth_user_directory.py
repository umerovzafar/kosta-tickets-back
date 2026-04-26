"""Справочник auth для обогащения ответов time tracking (должность position)."""

from __future__ import annotations

import logging

import httpx

from infrastructure.config import get_settings

_log = logging.getLogger(__name__)


async def fetch_auth_user_positions_by_id(authorization: str) -> dict[int, str | None]:
    """GET {auth}/users с тем же Bearer — id -> position (или None). При ошибке/403 — пустой dict."""
    authz = (authorization or "").strip()
    if not authz:
        return {}
    base = (get_settings().auth_service_url or "").strip().rstrip("/")
    if not base:
        return {}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                f"{base}/users",
                params={"include_archived": "true"},
                headers={"Authorization": authz},
            )
    except httpx.RequestError as e:
        _log.debug("auth users list for position merge: %s", e)
        return {}
    if r.status_code != 200:
        _log.debug("auth users list: HTTP %s", r.status_code)
        return {}
    data = r.json()
    if not isinstance(data, list):
        return {}
    out: dict[int, str | None] = {}
    for u in data:
        try:
            uid = u.get("id")
            if uid is None:
                continue
            out[int(uid)] = u.get("position")
        except (TypeError, ValueError):
            continue
    return out


async def fetch_auth_user_position(authorization: str, auth_user_id: int) -> str | None:
    """GET {auth}/users/{id} — должность для одного пользователя."""
    authz = (authorization or "").strip()
    if not authz:
        return None
    base = (get_settings().auth_service_url or "").strip().rstrip("/")
    if not base:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{base}/users/{auth_user_id}",
                headers={"Authorization": authz},
            )
    except httpx.RequestError as e:
        _log.debug("auth user %s for position: %s", auth_user_id, e)
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    if not isinstance(data, dict):
        return None
    pos = data.get("position")
    if pos is None:
        return None
    s = str(pos).strip()
    return s if s else None
