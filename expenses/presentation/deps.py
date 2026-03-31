from typing import Optional

import httpx
from fastapi import Header, HTTPException

from infrastructure.config import get_settings

ROLES_VIEW = {
    "Главный администратор",
    "Администратор",
    "Партнер",
    "IT отдел",
    "Офис менеджер",
    "Сотрудник",
}
# Принять / отклонить заявку — только партнёр и администраторы (не офис-менеджер и др.)
ROLES_MODERATE = {"Главный администратор", "Администратор", "Партнер"}


async def get_current_user(authorization: Optional[str] = Header(None, alias="Authorization")):
    if not authorization or not authorization.strip():
        raise HTTPException(status_code=401, detail="Authorization required")
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{settings.auth_service_url}/users/me",
                headers={"Authorization": authorization},
            )
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise HTTPException(status_code=503, detail="Auth service unavailable")
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    r.raise_for_status()
    return r.json()


def check_view_role(user: dict) -> None:
    role = (user.get("role") or "").strip()
    if role not in ROLES_VIEW:
        raise HTTPException(status_code=403, detail="Недостаточно прав для раздела расходов")


def check_moderate_role(user: dict) -> None:
    role = (user.get("role") or "").strip()
    if role not in ROLES_MODERATE:
        raise HTTPException(
            status_code=403,
            detail="Принимать и отклонять заявки могут только администратор или партнёр",
        )


def created_by_filter_for_user(user: dict) -> int | None:
    """Сотрудник видит только свои заявки; остальные роли — все."""
    role = (user.get("role") or "").strip()
    if role == "Сотрудник":
        return int(user["id"])
    return None
