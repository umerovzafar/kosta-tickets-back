"""Расписание звонков: календари и события ящика info@ (Microsoft Graph, без БД)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from infrastructure.config import get_settings
from infrastructure.graph_mailbox import (
    create_calendar_event,
    list_calendar_view,
    list_calendars_for_mailbox,
)
from presentation.deps import get_current_user_id

_log = logging.getLogger(__name__)

router = APIRouter(tags=["call_schedule"])


def _parse_dt(raw: str) -> datetime:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty datetime")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    d = datetime.fromisoformat(raw)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


@router.get("/calendars", summary="Список календарей почтового ящика")
async def get_calendars(
    _: Annotated[int, Depends(get_current_user_id)],
) -> dict[str, Any]:
    s = get_settings()
    m = s.call_schedule_mailbox
    if not m:
        raise HTTPException(
            status_code=503,
            detail="CALL_SCHEDULE_MAILBOX не задан (например info@kostalegal.com)",
        )
    try:
        cals = await list_calendars_for_mailbox(m)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        _log.warning("Graph calendars: %s", e.response.text[:800])
        raise HTTPException(
            status_code=502,
            detail=f"Microsoft Graph: {e.response.status_code} — проверьте права Calendars.Read на приложение",
        ) from e
    return {
        "mailbox": m,
        "calendars": cals,
    }


@router.get("/events", summary="События календаря за период")
async def get_events(
    _: Annotated[int, Depends(get_current_user_id)],
    start: str = Query(..., description="Начало периода (ISO 8601, UTC)"),
    end: str = Query(..., description="Конец периода (ISO 8601)"),
    calendar_id: str = Query(
        "default",
        description="id календаря из GET /calendars или default — основной",
        alias="calendarId",
    ),
) -> dict[str, Any]:
    s = get_settings()
    m = s.call_schedule_mailbox
    if not m:
        raise HTTPException(status_code=503, detail="CALL_SCHEDULE_MAILBOX не задан")
    try:
        t0, t1 = _parse_dt(start), _parse_dt(end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Неверные даты: {e}") from e
    if t1 <= t0:
        raise HTTPException(status_code=400, detail="end должен быть позже start")
    try:
        events = await list_calendar_view(m, calendar_id, t0, t1)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        _log.warning("Graph events: %s", e.response.text[:800])
        raise HTTPException(
            status_code=502,
            detail=f"Microsoft Graph: {e.response.status_code}",
        ) from e
    return {
        "mailbox": m,
        "calendarId": calendar_id,
        "start": t0.isoformat(),
        "end": t1.isoformat(),
        "events": events,
    }


class CreateCallBody(BaseModel):
    """Создать слот (звонок) в календаре ящика."""

    model_config = {"populate_by_name": True}

    subject: str = Field(..., min_length=1, max_length=500)
    start: str = Field(..., description="Начало (ISO 8601)")
    end: str = Field(..., description="Конец (ISO 8601)")
    body: str | None = Field(None, description="Текст приглашения / заметка")
    calendar_id: str | None = Field(
        None,
        description="id календаря; не задано = основной",
        alias="calendarId",
    )
    time_zone: str = Field("UTC", alias="timeZone")


@router.post("/events", summary="Создать событие (запись звонка)")
async def post_event(
    body: CreateCallBody,
    _: Annotated[int, Depends(get_current_user_id)],
) -> dict[str, Any]:
    s = get_settings()
    m = s.call_schedule_mailbox
    if not m:
        raise HTTPException(status_code=503, detail="CALL_SCHEDULE_MAILBOX не задан")
    try:
        t0, t1 = _parse_dt(body.start), _parse_dt(body.end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Неверные даты: {e}") from e
    if t1 <= t0:
        raise HTTPException(status_code=400, detail="end должен быть позже start")
    try:
        ev = await create_calendar_event(
            m,
            subject=body.subject.strip(),
            start=t0,
            end=t1,
            body=body.body,
            calendar_id=body.calendar_id,
            time_zone=body.time_zone or "UTC",
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        _log.warning("Graph create: %s", e.response.text[:800])
        raise HTTPException(
            status_code=502,
            detail=f"Microsoft Graph: {e.response.status_code}",
        ) from e
    return ev
