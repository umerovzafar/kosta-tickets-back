"""Публичная раздача файлов фона рабочего стола по URL из поля desktop_background.

Путь в БД: `desktop_backgrounds/{user_id}/{uuid}.{ext}` — фронт собирает
`https://<gateway>/<этот путь>`. Ранее маршрута не было (только `/api/v1/media/...` с Bearer,
что не подходит для <img src> без обходных решений).
"""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from infrastructure.config import get_settings

router = APIRouter(tags=["desktop_backgrounds"])

# Имена задаёт gateway при загрузке: uuid4().hex + допустимое расширение
_SAFE_FILENAME = re.compile(
    r"^[a-f0-9]{32}\.(jpg|jpeg|png|gif|webp)$",
    re.IGNORECASE,
)


@router.get("/desktop_backgrounds/{user_id}/{filename}")
async def serve_desktop_background(user_id: int, filename: str):
    if not _SAFE_FILENAME.match(filename):
        raise HTTPException(status_code=404, detail="Not found")
    settings = get_settings()
    base_dir = Path(settings.media_path).resolve()
    target = (base_dir / "desktop_backgrounds" / str(user_id) / filename).resolve()
    if not str(target).startswith(str(base_dir)):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)
