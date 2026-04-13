"""Маршруты пользователей учёта времени (список из БД и синхронизация)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import get_session
from infrastructure.repositories import TimeTrackingUserRepository, UserProjectAccessRepository
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


@router.get(
    "/managed-scope/{manager_auth_user_id}",
    response_model=list[UserResponse],
    summary="Пользователи в зоне видимости менеджера TT (общие проекты)",
)
async def list_users_in_manager_scope(
    manager_auth_user_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[UserResponse]:
    """Список auth_user_id: менеджер + все, у кого есть доступ хотя бы к одному из проектов менеджера."""
    par = UserProjectAccessRepository(session)
    ur = TimeTrackingUserRepository(session)
    scope_ids = set(await par.list_peer_auth_user_ids_for_manager(manager_auth_user_id))
    rows = await ur.list_users()
    out: list[UserResponse] = []
    for row in rows:
        if row.auth_user_id not in scope_ids:
            continue
        out.append(
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
        )
    return out


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
    try:
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
    except ProgrammingError as e:
        await session.rollback()
        orig = getattr(e, "orig", None)
        hint = (
            "Проверьте, что в БД применён скрипт scripts/add_time_tracking_team_workload.sql "
            "(колонка weekly_capacity_hours и таблица time_tracking_entries)."
        )
        raise HTTPException(
            status_code=503,
            detail=f"{hint} Ошибка СУБД: {orig or e}",
        ) from e
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(getattr(e, "orig", None) or e)) from e
    except DBAPIError as e:
        await session.rollback()
        raise HTTPException(status_code=503, detail=str(getattr(e, "orig", None) or e)) from e
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
