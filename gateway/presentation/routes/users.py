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
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])

ADMIN_ROLE = "Администратор"
PARTNER_ROLE = "Партнер"


async def require_admin(authorization: Optional[str] = Header(None, alias="Authorization")):
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
    user = r.json()
    role = (user.get("role") or "").strip()
    if role not in {ADMIN_ROLE, PARTNER_ROLE}:
        raise HTTPException(
            status_code=403,
            detail="Only Administrator or Partner can manage users and roles",
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
    _: dict = Depends(require_admin),
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
    _: dict = Depends(require_admin),
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
    _: dict = Depends(require_admin),
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
