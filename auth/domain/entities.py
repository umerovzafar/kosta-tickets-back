from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    id: int
    azure_oid: str
    email: str
    display_name: Optional[str]
    picture: Optional[str]
    role: str
    position: Optional[str]  # должность
    is_blocked: bool
    is_archived: bool
    time_tracking_role: Optional[str]  # "user" | "manager" | None — отдельная роль в учёте времени
    desktop_background: Optional[str]  # путь к фону рабочего стола (media/desktop_backgrounds/...)
    created_at: datetime
    updated_at: datetime
