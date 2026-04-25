"""Microsoft Graph: служебный ящик, токен client credentials, кэш в памяти процесса."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from infrastructure.config import get_settings

_log = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

# Кэш токена (без БД). После согласия admin consent в Entra старый token может остаться
# до истечения (до ~1 ч) с устаревшим набором roles — сбрасываем кэш при 401/403 от Graph.
_lock = asyncio.Lock()
_cached_token: str | None = None
_cached_expires: datetime | None = None
_credential_fingerprint: str | None = None
# обновлять чуть раньше истечения
_SKEW = timedelta(minutes=2)

# Явно запрашиваем ссылки: webLink, onlineMeeting.joinUrl (Teams) — иначе calendarView может отдать срез по умолчанию
_EVENT_SELECT = (
    "id,subject,bodyPreview,webLink,start,end,location,organizer,"
    "isOnlineMeeting,onlineMeetingProvider,onlineMeeting,showAs,isCancelled,"
    "createdDateTime,lastModifiedDateTime"
)


def _user_segment(mailbox: str) -> str:
    return quote(mailbox.strip(), safe="")


def _cred_fp(tenant: str, client_id: str, client_secret: str) -> str:
    return f"{tenant}:{client_id}:{hash(client_secret) & 0xFFFF_FFFF_FFFF_FFFF}"


def invalidate_graph_token_cache() -> None:
    global _cached_token, _cached_expires, _credential_fingerprint
    _cached_token = None
    _cached_expires = None
    _credential_fingerprint = None


async def get_app_access_token() -> str:
    """Client credentials: scope .default, кэш до expires."""
    global _cached_token, _cached_expires, _credential_fingerprint
    s = get_settings()
    tenant_id, client_id, client_secret = s.graph_client_credentials()
    if not tenant_id or not client_id or not client_secret:
        raise ValueError(
            "Задайте MICROSOFT_TENANT_ID, MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET "
            "(или CALL_SCHEDULE_MICROSOFT_*) и в Azure: Application Calendars.Read + Calendars.ReadWrite, admin consent"
        )
    now = datetime.now(timezone.utc)
    fp = _cred_fp(tenant_id, client_id, client_secret)
    async with _lock:
        if fp != _credential_fingerprint:
            _cached_token = None
            _cached_expires = None
            _credential_fingerprint = fp

        if (
            _cached_token
            and _cached_expires
            and _cached_expires - _SKEW > now
        ):
            return _cached_token

        url = TOKEN_URL_TPL.format(tenant=tenant_id)
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
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


async def _graph_get_once(path_after_v1: str) -> Any:
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


async def _graph_get(path_after_v1: str) -> Any:
    try:
        return await _graph_get_once(path_after_v1)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            _log.warning(
                "Graph GET retry after %s: %s",
                e.response.status_code,
                (e.response.text or "")[:500],
            )
            invalidate_graph_token_cache()
            return await _graph_get_once(path_after_v1)
        raise


def _graph_post_headers(
    token: str,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


async def _graph_post_once(
    path_after_v1: str,
    payload: dict,
    *,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    token = await get_app_access_token()
    url = f"{GRAPH}{path_after_v1}" if path_after_v1.startswith("/") else f"{GRAPH}/{path_after_v1}"
    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            json=payload,
            headers=_graph_post_headers(token, extra_headers),
            timeout=60.0,
        )
    r.raise_for_status()
    if r.text:
        return r.json()
    return {}


async def _graph_post(
    path_after_v1: str,
    payload: dict,
    *,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    try:
        return await _graph_post_once(path_after_v1, payload, extra_headers=extra_headers)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            _log.warning(
                "Graph POST retry after %s: %s",
                e.response.status_code,
                (e.response.text or "")[:500],
            )
            invalidate_graph_token_cache()
            return await _graph_post_once(path_after_v1, payload, extra_headers=extra_headers)
        raise


def _enrich_event_with_join_url(ev: dict[str, Any]) -> dict[str, Any]:
    """Добавляет meetingJoinUrl: Teams joinUrl приоритетно, иначе ссылка на событие в Outlook (webLink)."""
    out = dict(ev)
    join: str | None = None
    om = out.get("onlineMeeting")
    if isinstance(om, dict):
        ju = (om.get("joinUrl") or "").strip()
        if ju:
            join = ju
    if not join:
        wl = (out.get("webLink") or "").strip()
        if wl:
            join = wl
    if join:
        out["meetingJoinUrl"] = join
    return out


async def list_calendars_for_mailbox(mailbox: str) -> list[dict[str, Any]]:
    """GET /users/{upn}/calendars — список календарей ящика."""
    seg = _user_segment(mailbox)
    j = await _graph_get(f"/users/{seg}/calendars?$top=100")
    return j.get("value", []) if isinstance(j, dict) else []


def _calendar_view_query_string(start: datetime, end: datetime) -> str:
    return urlencode(
        {
            "startDateTime": _iso(start),
            "endDateTime": _iso(end),
            "$select": _EVENT_SELECT,
            "$top": "200",
        }
    )


async def list_calendar_view(
    mailbox: str,
    calendar_id: str,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """
    События в интервале (calendarView).
    calendar_id: id календаря (из list_calendars) или "default" — по умолчанию основной.
    В каждом элементе добавляется meetingJoinUrl (Teams или webLink), если ссылка есть.
    """
    seg = _user_segment(mailbox)
    q = _calendar_view_query_string(start, end)
    if calendar_id in ("", "default"):
        j = await _graph_get(f"/users/{seg}/calendar/calendarView?{q}")
    else:
        cal = quote(calendar_id, safe="")
        j = await _graph_get(f"/users/{seg}/calendars/{cal}/calendarView?{q}")
    raw = j.get("value", []) if isinstance(j, dict) else []
    return [
        _enrich_event_with_join_url(x) if isinstance(x, dict) else x
        for x in raw
    ]


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

    s = get_settings()
    if s.call_schedule_create_as_teams_meeting:
        payload["isOnlineMeeting"] = True
        prov = (s.call_schedule_online_meeting_provider or "teamsForBusiness").strip()
        if prov:
            payload["onlineMeetingProvider"] = prov

    # Часовой пояс в теле и в Prefer — как в примерах Microsoft для online meeting
    prefer_tz = f'outlook.timezone="{time_zone}"'
    extra_headers = {"Prefer": prefer_tz}

    if not calendar_id or calendar_id in ("default",):
        ev = await _graph_post(
            f"/users/{seg}/calendar/events",
            payload,
            extra_headers=extra_headers,
        )
    else:
        cal = quote(calendar_id, safe="")
        ev = await _graph_post(
            f"/users/{seg}/calendars/{cal}/events",
            payload,
            extra_headers=extra_headers,
        )
    if isinstance(ev, dict):
        return _enrich_event_with_join_url(ev)
    return ev
