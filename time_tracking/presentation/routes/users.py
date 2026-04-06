"""Маршруты пользователей учёта времени (список из БД и синхронизация)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import get_session
from infrastructure.repositories import TimeTrackingUserRepository
from presentation.schemas import UserResponse, UserUpsertBody, WeeklyCapacityPatchBody

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse], summary="Список пользователей")
async def list_users(
    session: AsyncSession = Depends(get_session),
) -> list[UserResponse]:
    """Возвращает пользователей из БД time_tracking."""
    repo = TimeTrackingUserRepository(session)
    rows = await repo.list_users()
    return [
        UserResponse(
            id=row.auth_user_id,
            email=row.email,
            display_name=row.display_name,
            picture=row.picture,
            role=row.role,
            is_blocked=row.is_blocked,
            is_archived=row.is_archived,
            weekly_capacity_hours=row.weekly_capacity_hours,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get("/{auth_user_id}", response_model=UserResponse, summary="Один пользователь учёта времени")
async def get_user(
    auth_user_id: int,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    repo = TimeTrackingUserRepository(session)
    row = await repo.get_by_auth_user_id(auth_user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not in time tracking")
    return UserResponse(
        id=row.auth_user_id,
        email=row.email,
        display_name=row.display_name,
        picture=row.picture,
        role=row.role,
        is_blocked=row.is_blocked,
        is_archived=row.is_archived,
        weekly_capacity_hours=row.weekly_capacity_hours,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.patch(
    "/{auth_user_id}/weekly-capacity-hours",
    response_model=UserResponse,
    summary="Обновить только норму часов в неделю",
)
async def patch_weekly_capacity(
    auth_user_id: int,
    body: WeeklyCapacityPatchBody,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    repo = TimeTrackingUserRepository(session)
    row = await repo.patch_weekly_capacity_hours(auth_user_id, body.weekly_capacity_hours)
    if not row:
        raise HTTPException(status_code=404, detail="User not in time tracking")
    await session.commit()
    return UserResponse(
        id=row.auth_user_id,
        email=row.email,
        display_name=row.display_name,
        picture=row.picture,
        role=row.role,
        is_blocked=row.is_blocked,
        is_archived=row.is_archived,
        weekly_capacity_hours=row.weekly_capacity_hours,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("", status_code=200, summary="Создать/обновить пользователя (синхронизация)")
async def upsert_user(
    body: UserUpsertBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Добавляет или обновляет пользователя в БД time_tracking. Вызывать из auth или скрипта синхронизации."""
    repo = TimeTrackingUserRepository(session)
    await repo.upsert_user(
        auth_user_id=body.auth_user_id,
        email=body.email,
        display_name=body.display_name,
        picture=body.picture,
        role=body.role,
        is_blocked=body.is_blocked,
        is_archived=body.is_archived,
        weekly_capacity_hours=body.weekly_capacity_hours,
    )
    await session.commit()
    return {"ok": True}


@router.delete("/{auth_user_id}", status_code=200, summary="Удалить пользователя из списка")
async def delete_user(
    auth_user_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Удаляет пользователя из БД time_tracking по auth_user_id."""
    repo = TimeTrackingUserRepository(session)
    deleted = await repo.delete_by_auth_user_id(auth_user_id)
    await session.commit()
    return {"ok": True, "deleted": deleted}
