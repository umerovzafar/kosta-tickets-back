from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException

from infrastructure.config import get_settings
from presentation.routes.users import require_admin, _auth_headers

router = APIRouter(prefix="/api/v1/roles", tags=["roles"])


@router.get("")
async def list_roles(authorization: Optional[str] = Header(None, alias="Authorization"), _: dict = Depends(require_admin)):
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{settings.auth_service_url}/roles", headers=_auth_headers(authorization))
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    r.raise_for_status()
    return r.json()


@router.post("")
async def create_role(
    body: dict,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_admin),
):
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{settings.auth_service_url}/roles",
            json=body,
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code == 400:
        raise HTTPException(status_code=400, detail=r.json().get("detail") or "Invalid role data")
    r.raise_for_status()
    return r.json()


@router.get("/{role_id}")
async def get_role(
    role_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_admin),
):
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{settings.auth_service_url}/roles/{role_id}",
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Role not found")
    r.raise_for_status()
    return r.json()


@router.patch("/{role_id}")
async def update_role(
    role_id: int,
    body: dict,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_admin),
):
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.patch(
            f"{settings.auth_service_url}/roles/{role_id}",
            json=body,
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code == 400:
        raise HTTPException(status_code=400, detail=r.json().get("detail") or "Invalid role data")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Role not found")
    r.raise_for_status()
    return r.json()


@router.delete("/{role_id}")
async def delete_role(
    role_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_admin),
):
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.delete(
            f"{settings.auth_service_url}/roles/{role_id}",
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Role not found")
    if r.status_code == 400:
        raise HTTPException(status_code=400, detail=r.json().get("detail") or "Cannot delete role")
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=r.status_code, detail=r.text or "Role delete error")
    return {"ok": True}


@router.get("/{role_id}/permissions")
async def get_role_permissions(
    role_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_admin),
):
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{settings.auth_service_url}/roles/{role_id}/permissions",
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Role not found")
    r.raise_for_status()
    return r.json()


@router.patch("/{role_id}/permissions")
async def set_role_permissions(
    role_id: int,
    body: dict,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    _: dict = Depends(require_admin),
):
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.patch(
            f"{settings.auth_service_url}/roles/{role_id}/permissions",
            json=body,
            headers=_auth_headers(authorization),
        )
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Role not found")
    r.raise_for_status()
    return r.json()

