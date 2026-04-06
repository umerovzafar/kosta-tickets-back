"""Записи списанного времени (для расчёта загрузки команды)."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import get_session
from infrastructure.repositories import TimeEntryRepository, TimeTrackingUserRepository
from presentation.schemas import TimeEntryCreateBody, TimeEntryOut, TimeEntryPatchBody

router = APIRouter(prefix="/users", tags=["time_entries"])


async def _ensure_user(session: AsyncSession, auth_user_id: int) -> None:
    ur = TimeTrackingUserRepository(session)
    if not await ur.get_by_auth_user_id(auth_user_id):
        raise HTTPException(status_code=404, detail="Пользователь не найден")


@router.get("/{auth_user_id}/time-entries", response_model=list[TimeEntryOut])
async def list_time_entries(
    auth_user_id: int,
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    session: AsyncSession = Depends(get_session),
) -> list[TimeEntryOut]:
    await _ensure_user(session, auth_user_id)
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="Параметр to не может быть раньше from")
    repo = TimeEntryRepository(session)
    rows = await repo.list_for_user(auth_user_id, date_from, date_to)
    return [TimeEntryOut.model_validate(r) for r in rows]


@router.post("/{auth_user_id}/time-entries", response_model=TimeEntryOut)
async def create_time_entry(
    auth_user_id: int,
    body: TimeEntryCreateBody,
    session: AsyncSession = Depends(get_session),
) -> TimeEntryOut:
    await _ensure_user(session, auth_user_id)
    repo = TimeEntryRepository(session)
    try:
        row = await repo.create(
            entry_id=str(uuid.uuid4()),
            auth_user_id=auth_user_id,
            work_date=body.work_date,
            hours=body.hours,
            is_billable=body.is_billable,
            project_id=body.project_id,
            description=body.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await session.commit()
    await session.refresh(row)
    return TimeEntryOut.model_validate(row)


@router.patch("/{auth_user_id}/time-entries/{entry_id}", response_model=TimeEntryOut)
async def patch_time_entry(
    auth_user_id: int,
    entry_id: str,
    body: TimeEntryPatchBody,
    session: AsyncSession = Depends(get_session),
) -> TimeEntryOut:
    await _ensure_user(session, auth_user_id)
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="Нет полей для обновления")
    repo = TimeEntryRepository(session)
    try:
        row = await repo.update(auth_user_id=auth_user_id, entry_id=entry_id, patch=patch)
    except LookupError as e:
        if str(e) == "not_found":
            raise HTTPException(status_code=404, detail="Запись не найдена") from e
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await session.commit()
    await session.refresh(row)
    return TimeEntryOut.model_validate(row)


@router.delete("/{auth_user_id}/time-entries/{entry_id}")
async def delete_time_entry(
    auth_user_id: int,
    entry_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _ensure_user(session, auth_user_id)
    repo = TimeEntryRepository(session)
    ok = await repo.delete(auth_user_id, entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    await session.commit()
    return {"ok": True}
