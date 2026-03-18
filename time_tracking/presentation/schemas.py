from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime


class UserResponse(BaseModel):
    """Пользователь для списка учёта времени (совместимо с gateway UserResponse)."""

    id: int
    email: str
    display_name: Optional[str] = None
    picture: Optional[str] = None
    role: str = ""
    is_blocked: bool = False
    is_archived: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None


class UserUpsertBody(BaseModel):
    """Тело запроса для создания/обновления пользователя (синхронизация из auth)."""

    auth_user_id: int
    email: str
    display_name: Optional[str] = None
    picture: Optional[str] = None
    role: str = ""
    is_blocked: bool = False
    is_archived: bool = False
