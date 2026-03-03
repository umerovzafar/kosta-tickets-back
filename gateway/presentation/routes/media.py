from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/media", tags=["media"])


@router.get("/{subpath:path}")
async def get_media(subpath: str):
    settings = get_settings()
    base_dir = Path(settings.media_path).resolve()
    target_path = (base_dir / subpath).resolve()

    if not str(target_path).startswith(str(base_dir)):
        raise HTTPException(status_code=400, detail="Invalid media path")

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")

    return FileResponse(target_path)

