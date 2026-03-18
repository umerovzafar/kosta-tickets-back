from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
import httpx
from infrastructure.config import get_settings
from presentation.schemas.user_schemas import (
    UserResponse,
    UserDetailResponse,
    SetRoleRequest,
    BlockUserRequest,
    ArchiveUserRequest,
    TimeTrackingRoleRequest,
    SetPositionRequest,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])

MAIN_ADMIN_ROLE = "Главный администратор"
ADMIN_ROLE = "Администратор"
PARTNER_ROLE = "Партнер"
IT_ROLE = "IT отдел"

ROLES_CAN_VIEW_USERS = {MAIN_ADMIN_ROLE, ADMIN_ROLE, PARTNER_ROLE, IT_ROLE}
ROLES_CAN_MANAGE_USERS = {MAIN_ADMIN_ROLE, ADMIN_ROLE, PARTNER_ROLE}


async def _get_current_user_optional(authorization: Optional[str]) -> dict:
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


async def require_auth(authorization: Optional[str] = Header(None, alias="Authorization")):
    """Любой авторизованный пользователь (только проверка токена)."""
    return await _get_current_user_optional(authorization)


async def require_admin(authorization: Optional[str] = Header(None, alias="Authorization")):
    """Главный администратор, Администратор или Партнер — управление пользователями (блок, архив, роль в учёте времени)."""
    user = await _get_current_user_optional(authorization)
    role = (user.get("role") or "").strip()
    if role not in ROLES_CAN_MANAGE_USERS:
        raise HTTPException(
            status_code=403,
            detail="Only Main Administrator, Administrator or Partner can manage users",
        )
    return user


async def require_main_admin(authorization: Optional[str] = Header(None, alias="Authorization")):
    """Только Главный администратор — назначение ролей пользователям."""
    user = await _get_current_user_optional(authorization)
    role = (user.get("role") or "").strip()
    if role != MAIN_ADMIN_ROLE:
        raise HTTPException(
            status_code=403,
            detail="Only Main Administrator can assign user roles",
        )
    return user


async def require_admin_or_it(authorization: Optional[str] = Header(None, alias="Authorization")):
    """Администратор, Партнер или IT отдел — просмотр списка и деталей пользователей."""
    user = await _get_current_user_optional(authorization)
    role = (user.get("role") or "").strip()
    if role not in ROLES_CAN_VIEW_USERS:
        raise HTTPException(
            status_code=403,
            detail="Only Administrator, Partner or IT department can view user details",
        )
    return user


def _auth_headers(authorization: Optional[str]) -> dict:
    headers = {}
    if authorization:
        headers["Authorization"] = authorization
    return headers


@router.get("/me", response_model=UserResponse)
async def get_me(authorization: Optional[str] = Header(None, alias="Authorization")):
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.auth_service_url}/users/me",
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    r.raise_for_status()
    return r.json()


@router.get("", response_model=list[UserResponse])
async def list_users(
    include_archived: bool = Query(False, description="Include archived users"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_auth),
):
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.auth_service_url}/users",
            params={"include_archived": include_archived},
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    r.raise_for_status()
    return r.json()


@router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user_detail(
    user_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_auth),
):
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{settings.auth_service_url}/users/{user_id}",
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="User not found")
    r.raise_for_status()
    return r.json()


@router.patch("/{user_id}/role", response_model=UserDetailResponse)
async def set_user_role(
    user_id: int,
    body: SetRoleRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_main_admin),
):
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{settings.auth_service_url}/users/{user_id}/role",
            json=body.model_dump(),
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="User not found")
    r.raise_for_status()
    return r.json()


@router.patch("/{user_id}/block", response_model=UserDetailResponse)
async def block_user(
    user_id: int,
    body: BlockUserRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_admin),
):
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{settings.auth_service_url}/users/{user_id}/block",
            json=body.model_dump(),
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="User not found")
    r.raise_for_status()
    return r.json()


@router.patch("/{user_id}/archive", response_model=UserDetailResponse)
async def archive_user(
    user_id: int,
    body: ArchiveUserRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_admin),
):
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{settings.auth_service_url}/users/{user_id}/archive",
            json=body.model_dump(),
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="User not found")
    r.raise_for_status()
    return r.json()


@router.patch("/{user_id}/time-tracking-role", response_model=UserDetailResponse)
async def set_time_tracking_role(
    user_id: int,
    body: TimeTrackingRoleRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_admin),
):
    """Назначить роль в учёте времени (user / manager). Главный администратор или Администратор."""
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{settings.auth_service_url}/users/{user_id}/time-tracking-role",
            json=body.model_dump(),
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="User not found")
    r.raise_for_status()
    return r.json()


@router.patch("/{user_id}/position", response_model=UserDetailResponse)
async def set_position(
    user_id: int,
    body: SetPositionRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_admin),
):
    """Установить должность пользователя. Главный администратор, Администратор или Партнер."""
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{settings.auth_service_url}/users/{user_id}/position",
            json=body.model_dump(),
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="User not found")
    r.raise_for_status()
    return r.json()
