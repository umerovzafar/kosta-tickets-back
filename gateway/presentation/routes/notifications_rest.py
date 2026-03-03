from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
import httpx
from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

ROLES_CAN_WRITE = {"Партнер", "IT отдел", "Офис менеджер"}


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


def require_write_role(user: dict = Depends(get_current_user)):
    if (user.get("role") or "").strip() not in ROLES_CAN_WRITE:
        raise HTTPException(
            status_code=403,
            detail="Only Partner, IT department and Office manager can create, edit, archive or delete notifications.",
        )
    return user


def _notifications_url(path: str) -> str:
    base = get_settings().notifications_service_url.rstrip("/")
    return f"{base}/notifications{path}"


@router.get("")
async def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    include_archived: bool = False,
    user: dict = Depends(get_current_user),
):
    """Список уведомлений (любой авторизованный)."""
    url = _notifications_url("")
    params = {"skip": skip, "limit": limit, "include_archived": include_archived}
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, params=params)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Notifications service error")
    return r.json()


@router.get("/{notification_uuid}")
async def get_notification(
    notification_uuid: str,
    user: dict = Depends(get_current_user),
):
    """Получить уведомление по uuid."""
    url = _notifications_url(f"/{notification_uuid}")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Notification not found")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Notifications service error")
    return r.json()


@router.post("", status_code=201)
async def create_notification(
    body: dict,
    user: dict = Depends(require_write_role),
):
    """Создать уведомление (Партнер, IT, Офис менеджер)."""
    url = _notifications_url("")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(url, json=body)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=r.status_code, detail=r.text or "Notifications service error")
    return r.json()


@router.patch("/{notification_uuid}")
async def update_notification(
    notification_uuid: str,
    body: dict,
    user: dict = Depends(require_write_role),
):
    """Обновить уведомление."""
    url = _notifications_url(f"/{notification_uuid}")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.patch(url, json=body)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Notification not found")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Notifications service error")
    return r.json()


@router.post("/{notification_uuid}/archive")
async def archive_notification(
    notification_uuid: str,
    body: dict,
    user: dict = Depends(require_write_role),
):
    """Архивировать или радархивировать уведомление."""
    url = _notifications_url(f"/{notification_uuid}/archive")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(url, json=body)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Notification not found")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Notifications service error")
    return r.json()


@router.delete("/{notification_uuid}", status_code=204)
async def delete_notification(
    notification_uuid: str,
    user: dict = Depends(require_write_role),
):
    """Удалить уведомление."""
    url = _notifications_url(f"/{notification_uuid}")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.delete(url)
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Notification not found")
    if r.status_code != 204:
        raise HTTPException(status_code=r.status_code, detail=r.text or "Notifications service error")
