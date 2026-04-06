"""Эндпоинты интеграции с календарём Microsoft Outlook."""

import logging
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.config import get_settings
from infrastructure.database import get_session
from infrastructure.microsoft_graph import (
    create_calendar_event as graph_create_event,
    exchange_code_for_tokens,
    get_authorize_url,
    list_calendar_events as graph_list_events,
    refresh_tokens,
)
from infrastructure.models import OutlookCalendarTokenModel
from infrastructure.repositories import OutlookCalendarTokenRepository
from presentation.dependencies import get_current_user_id

router = APIRouter(prefix="/calendar", tags=["calendar"])
_log = logging.getLogger(__name__)


def _encode_state(user_id: int) -> str:
    return urlsafe_b64encode(str(user_id).encode()).decode()


def _decode_state(state: str) -> int | None:
    try:
        return int(urlsafe_b64decode(state.encode()).decode())
    except Exception:
        return None


async def _get_valid_token(
    repo: OutlookCalendarTokenRepository,
    user_id: int,
    session: AsyncSession,
) -> OutlookCalendarTokenModel | None:
    row = await repo.get_by_user_id(user_id)
    if not row:
        return None
    now = datetime.now(timezone.utc)
    if row.expires_at and row.expires_at <= now:
        try:
            refreshed = await refresh_tokens(row.refresh_token)
            await repo.upsert(
                user_id=user_id,
                access_token=refreshed["access_token"],
                refresh_token=refreshed["refresh_token"],
                expires_at=refreshed["expires_at"],
            )
            await session.commit()
            row = await repo.get_by_user_id(user_id)
        except Exception:
            return None
    return row


@router.get("/connect", summary="Подключение календаря Outlook")
async def calendar_connect(
    user_id: Annotated[int, Depends(get_current_user_id)],
):
    """
    Возвращает URL входа Microsoft. Всегда JSON — не HTTP-редирект: иначе fetch() на
    фронте следует за 302 на login.microsoftonline.com и падает по CORS.
    Редирект браузера выполняет клиент: window.location = data.url.
    """
    settings = get_settings()
    cid = (settings.microsoft_client_id or "").strip()
    ruri = (settings.microsoft_redirect_uri or "").strip()
    if not cid or not ruri:
        raise HTTPException(
            status_code=503,
            detail=(
                "Calendar OAuth is not configured: set MICROSOFT_CLIENT_ID and MICROSOFT_REDIRECT_URI "
                "for the todos service (see docker-compose / .env). "
                "MICROSOFT_REDIRECT_URI must be the gateway callback URL, e.g. "
                "http://localhost:1234/api/v1/todos/calendar/callback (not http://localhost:5173/...)."
            ),
        )
    try:
        state = _encode_state(user_id)
        url = get_authorize_url(state)
    except ValueError as e:
        _log.warning("calendar connect: invalid OAuth settings: %s", e)
        raise HTTPException(
            status_code=503,
            detail=str(e),
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        _log.exception("calendar connect: unexpected error building authorize URL")
        raise HTTPException(
            status_code=503,
            detail=f"Could not build Microsoft sign-in URL: {e!s}",
        ) from e
    return JSONResponse(content={"url": url})


@router.get("/callback", summary="OAuth callback от Microsoft")
async def calendar_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Принимает code от Microsoft, сохраняет токены, редирект на фронт."""
    if error or not code or not state:
        redirect_url = get_settings().calendar_connected_redirect_url or "/"
        return RedirectResponse(url=f"{redirect_url}?calendar=error")
    user_id = _decode_state(state)
    if user_id is None:
        redirect_url = get_settings().calendar_connected_redirect_url or "/"
        return RedirectResponse(url=f"{redirect_url}?calendar=error")
    try:
        tokens = await exchange_code_for_tokens(code)
    except Exception:
        redirect_url = get_settings().calendar_connected_redirect_url or "/"
        return RedirectResponse(url=f"{redirect_url}?calendar=error")
    repo = OutlookCalendarTokenRepository(session)
    await repo.upsert(
        user_id=user_id,
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
        expires_at=tokens["expires_at"],
    )
    await session.commit()
    redirect_url = get_settings().calendar_connected_redirect_url or "/"
    return RedirectResponse(url=f"{redirect_url}?calendar=connected")


@router.get("/status", summary="Статус подключения календаря")
async def calendar_status(
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_session),
):
    """Проверка, подключён ли календарь Outlook для текущего пользователя. Всегда JSON."""
    try:
        repo = OutlookCalendarTokenRepository(session)
        row = await repo.get_by_user_id(user_id)
        return JSONResponse(content={"connected": row is not None})
    except HTTPException:
        raise
    except Exception as e:
        _log.warning("calendar status: DB or query failed: %s", e, exc_info=True)
        # Не отдаём 500: фронт может опросить статус до готовности БД
        return JSONResponse(
            status_code=503,
            content={"connected": False, "error": "unavailable", "detail": str(e)[:500]},
        )


class CreateCalendarEventBody(BaseModel):
    subject: str
    start: datetime
    end: datetime
    body: str | None = None


@router.get("/events", summary="Список событий календаря")
async def list_events(
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_session),
    start: datetime | None = Query(None, description="Начало периода"),
    end: datetime | None = Query(None, description="Конец периода"),
):
    """Возвращает события из календаря Outlook за период (если указаны start/end)."""
    try:
        repo = OutlookCalendarTokenRepository(session)
        row = await _get_valid_token(repo, user_id, session)
        if not row:
            raise HTTPException(status_code=403, detail="Calendar not connected")
        if not (row.access_token or "").strip():
            raise HTTPException(status_code=403, detail="Calendar token missing")
        try:
            events = await graph_list_events(row.access_token, start=start, end=end)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Calendar API error: {e!s}")
        return {"value": events}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error loading calendar events") from e


@router.post("/events", summary="Создание события в календаре")
async def create_event(
    user_id: Annotated[int, Depends(get_current_user_id)],
    body: CreateCalendarEventBody,
    session: AsyncSession = Depends(get_session),
):
    """Создаёт событие в календаре Outlook текущего пользователя."""
    repo = OutlookCalendarTokenRepository(session)
    row = await _get_valid_token(repo, user_id, session)
    if not row:
        raise HTTPException(status_code=403, detail="Calendar not connected")
    try:
        event = await graph_create_event(
            row.access_token,
            subject=body.subject,
            start=body.start,
            end=body.end,
            body=body.body,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Calendar API error: {e}")
    return event
