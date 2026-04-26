"""Правила доступа к данным других пользователей (согласовано с gateway time_tracking_routes)."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import TimeTrackingUserRepository, UserProjectAccessRepository

# Организационные роли (auth users.role)
_VIEW_ROLES_TIME_ENTRIES = frozenset(
    {
        "Главный администратор",
        "Администратор",
        "Партнер",
        "IT отдел",
        "Офис менеджер",
    }
)
_MANAGE_ROLES_TIME_ENTRIES = frozenset({"Главный администратор", "Администратор", "Партнер"})


async def viewer_can_bypass_work_week_submission_lock(
    session: AsyncSession,
    viewer: dict,
) -> bool:
    """Закрытая отчётная неделя (сдача / сб 9:00): правки разрешены менеджеру TT и орг-админам.

    Обычные пользователи не обходят блок — только роль ``manager`` в ``time_tracking_users``
    (менеджер учёта времени) и роли с полным доступом к чужим записям (партнёр/админ).
    """
    if _org_role(viewer) in _MANAGE_ROLES_TIME_ENTRIES:
        return True
    ur = TimeTrackingUserRepository(session)
    row = await ur.get_by_auth_user_id(_viewer_id(viewer))
    return bool(row and (row.role or "").strip() == "manager")


def _org_role(viewer: dict) -> str:
    return (viewer.get("role") or "").strip()


def _viewer_id(viewer: dict) -> int:
    uid = viewer.get("id")
    if uid is None:
        raise HTTPException(status_code=403, detail="В токене нет id пользователя")
    return int(uid)


async def ensure_time_entry_subject_allowed(
    session: AsyncSession,
    viewer: dict,
    target_auth_user_id: int,
    *,
    write: bool,
) -> None:
    """Можно ли читать/менять записи времени для target_auth_user_id."""
    if _viewer_id(viewer) == target_auth_user_id:
        return
    role = _org_role(viewer)
    if write:
        if role in _MANAGE_ROLES_TIME_ENTRIES:
            return
    else:
        if role in _VIEW_ROLES_TIME_ENTRIES:
            return

    ur = TimeTrackingUserRepository(session)
    row = await ur.get_by_auth_user_id(_viewer_id(viewer))
    tt_role = (row.role or "").strip() if row else ""
    if tt_role != "manager":
        raise HTTPException(
            status_code=403,
            detail=(
                "Можно изменять только свои записи времени либо нужны права администратора или менеджера учёта времени"
                if write
                else "Можно просматривать только свои записи времени либо нужна роль офиса или менеджера учёта времени"
            ),
        )

    par = UserProjectAccessRepository(session)
    scope = set(await par.list_peer_auth_user_ids_for_manager(_viewer_id(viewer)))
    if target_auth_user_id in scope:
        return
    raise HTTPException(
        status_code=403,
        detail=(
            "Менеджер учёта времени может менять записи только сотрудников с общими проектами доступа"
            if write
            else "Менеджер учёта времени видит записи только сотрудников с общими проектами доступа"
        ),
    )


async def ensure_can_read_tt_user_row(
    session: AsyncSession,
    viewer: dict,
    target_auth_user_id: int,
) -> None:
    """Доступ к GET /users/{id} (роль TT, email и т.д.)."""
    if _viewer_id(viewer) == target_auth_user_id:
        return
    role = _org_role(viewer)
    if role in _VIEW_ROLES_TIME_ENTRIES:
        return
    ur = TimeTrackingUserRepository(session)
    row = await ur.get_by_auth_user_id(_viewer_id(viewer))
    tt_role = (row.role or "").strip() if row else ""
    if tt_role != "manager":
        raise HTTPException(status_code=403, detail="Недостаточно прав для просмотра профиля другого пользователя")
    par = UserProjectAccessRepository(session)
    scope = set(await par.list_peer_auth_user_ids_for_manager(_viewer_id(viewer)))
    if target_auth_user_id in scope:
        return
    raise HTTPException(status_code=403, detail="Менеджер видит только пользователей с общими проектами доступа")


async def ensure_can_list_all_tt_users(viewer: dict) -> None:
    """GET /users — полный список (только офис/админ; менеджеры используют /users/managed-scope/{id})."""
    role = _org_role(viewer)
    if role in _VIEW_ROLES_TIME_ENTRIES:
        return
    raise HTTPException(
        status_code=403,
        detail="Полный список пользователей учёта времени доступен только офису и администраторам",
    )


async def ensure_managed_scope_allowed(viewer: dict, manager_auth_user_id: int) -> None:
    """GET /users/managed-scope/{manager_auth_user_id}."""
    if _viewer_id(viewer) == manager_auth_user_id:
        return
    if _org_role(viewer) in _VIEW_ROLES_TIME_ENTRIES:
        return
    raise HTTPException(status_code=403, detail="Недостаточно прав для зоны видимости менеджера")


async def ensure_weekly_capacity_patch_allowed(viewer: dict, target_auth_user_id: int) -> None:
    """PATCH /users/{id}/weekly-capacity-hours."""
    if _viewer_id(viewer) == target_auth_user_id:
        return
    if _org_role(viewer) in _MANAGE_ROLES_TIME_ENTRIES:
        return
    raise HTTPException(
        status_code=403,
        detail="Норму часов может менять только сам пользователь или администратор",
    )


def ensure_upsert_user_allowed(viewer: dict, body_auth_user_id: int) -> None:
    """POST /users — синхронизация профиля."""
    if _viewer_id(viewer) == body_auth_user_id:
        return
    if _org_role(viewer) in _MANAGE_ROLES_TIME_ENTRIES:
        return
    raise HTTPException(
        status_code=403,
        detail="Синхронизировать другого пользователя могут только администратор или партнёр",
    )


def ensure_delete_tt_user_allowed(viewer: dict) -> None:
    if _org_role(viewer) in _MANAGE_ROLES_TIME_ENTRIES:
        return
    raise HTTPException(status_code=403, detail="Удаление из учёта времени — только для администраторов")
