import uuid
from pathlib import Path

from infrastructure.config import get_settings


def get_expenses_upload_dir(request_id: int) -> Path:
    path = Path(get_settings().media_path) / "expenses" / str(request_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_attachment(request_id: int, filename: str, content: bytes) -> str:
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise ValueError(f"File size exceeds {get_settings().max_upload_mb}MB")
    upload_dir = get_expenses_upload_dir(request_id)
    ext = Path(filename).suffix if filename else ""
    unique_name = f"{uuid.uuid4().hex}{ext}"
    path = upload_dir / unique_name
    path.write_bytes(content)
    return str(path.relative_to(Path(get_settings().media_path)))
