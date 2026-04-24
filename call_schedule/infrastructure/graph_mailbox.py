"""Microsoft Graph: служебный ящик, токен client credentials, кэш в памяти процесса."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

from infrastructure.config import get_settings

_log = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

# Кэш токена (без БД)
_lock = asyncio.Lock()
_cached_token: str | None = None
_cached_expires: datetime | None = None
# обновлять чуть раньше истечения
_SKEW = timedelta(minutes=2)


def _user_segment(mailbox: str) -> str:
    return quote(mailbox.strip(), safe="")


async def get_app_access_token() -> str:
    """Client credentials: scope .default, кэш до expires."""
    global _cached_token, _cached_expires
    s = get_settings()
    if not s.microsoft_tenant_id or not s.microsoft_client_id or not s.microsoft_client_secret:
        raise ValueError(
            "Задайте MICROSOFT_TENANT_ID, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET "
            "и в Azure: Application permissions Calendars.Read + Calendars.ReadWrite (создание), admin consent"
        )
    now = datetime.now(timezone.utc)
    async with _lock:
        if (
            _cached_token
            and _cached_expires
            and _cached_expires - _SKEW > now
        ):
            return _cached_token

        url = TOKEN_URL_TPL.format(tenant=s.microsoft_tenant_id)
        data = {
            "client_id": s.microsoft_client_id,
            "client_secret": s.microsoft_client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30.0,
            )
        r.raise_for_status()
        j = r.json()
        token = j["access_token"]
        exp_sec = int(j.get("expires_in", 3600))
        _cached_token = token
        _cached_expires = now + timedelta(seconds=exp_sec)
        _log.debug("Graph app token obtained, expires in %ss", exp_sec)
        return token


async def _graph_get(path_after_v1: str) -> Any:
    token = await get_app_access_token()
    url = f"{GRAPH}{path_after_v1}" if path_after_v1.startswith("/") else f"{GRAPH}/{path_after_v1}"
    async with httpx.AsyncClient() as client:
        r = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0,
        )
    r.raise_for_status()
    if r.text:
        return r.json()
    return {}


async def _graph_post(path_after_v1: str, payload: dict) -> Any:
    token = await get_app_access_token()
    url = f"{GRAPH}{path_after_v1}" if path_after_v1.startswith("/") else f"{GRAPH}/{path_after_v1}"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )
    r.raise_for_status()
    if r.text:
        return r.json()
    return {}


async def list_calendars_for_mailbox(mailbox: str) -> list[dict[str, Any]]:
    """GET /users/{upn}/calendars — список календарей ящика."""
    seg = _user_segment(mailbox)
    j = await _graph_get(f"/users/{seg}/calendars?$top=100")
    return j.get("value", []) if isinstance(j, dict) else []


async def list_calendar_view(
    mailbox: str,
    calendar_id: str,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """
    События в интервале (calendarView).
    calendar_id: id календаря (из list_calendars) или "default" — по умолчанию основной.
    """
    seg = _user_segment(mailbox)
    if calendar_id in ("", "default"):
        j = await _graph_get(
            f"/users/{seg}/calendar/calendarView?startDateTime={_iso(start)}&endDateTime={_iso(end)}&$top=200"
        )
    else:
        cal = quote(calendar_id, safe="")
        j = await _graph_get(
            f"/users/{seg}/calendars/{cal}/calendarView?startDateTime={_iso(start)}&endDateTime={_iso(end)}&$top=200"
        )
    return j.get("value", []) if isinstance(j, dict) else []


def _iso(d: datetime) -> str:
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat().replace("+00:00", "Z")


async def create_calendar_event(
    mailbox: str,
    *,
    subject: str,
    start: datetime,
    end: datetime,
    body: str | None = None,
    calendar_id: str | None = None,
    time_zone: str = "UTC",
) -> dict[str, Any]:
    """
    Создать событие (звонок).
    calendar_id: None / default — основной календарь: POST /users/.../calendar/events
    иначе POST .../calendars/{id}/events
    """
    seg = _user_segment(mailbox)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    payload: dict[str, Any] = {
        "subject": subject,
        "start": {
            "dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": time_zone,
        },
        "end": {
            "dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": time_zone,
        },
    }
    if body:
        payload["body"] = {"contentType": "text", "content": body}
    if not calendar_id or calendar_id in ("default",):
        return await _graph_post(f"/users/{seg}/calendar/events", payload)
    cal = quote(calendar_id, safe="")
    return await _graph_post(f"/users/{seg}/calendars/{cal}/events", payload)
