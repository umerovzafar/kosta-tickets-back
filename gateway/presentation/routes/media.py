from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse

from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/media", tags=["media"])


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


@router.get("/{subpath:path}")
async def get_media(subpath: str, _: dict = Depends(get_current_user)):
    settings = get_settings()
    base_dir = Path(settings.media_path).resolve()
    target_path = (base_dir / subpath).resolve()

    if not str(target_path).startswith(str(base_dir)):
        raise HTTPException(status_code=400, detail="Invalid media path")

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")

    return FileResponse(target_path)

