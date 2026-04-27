from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: Optional[str]
    picture: Optional[str]
    role: str
    position: Optional[str] = None  # должность
    is_blocked: bool = False
    is_archived: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    permissions: Optional[dict] = None  # оставлено для совместимости
    time_tracking_role: Optional[str] = None  # user | manager — роль в учёте времени
    desktop_background: Optional[str] = None  # путь к фону рабочего стола


class UserDetailResponse(BaseModel):
    id: int
    azure_oid: str
    email: str
    display_name: Optional[str]
    picture: Optional[str]
    role: str
    position: Optional[str] = None  # должность
    is_blocked: bool
    is_archived: bool
    time_tracking_role: Optional[str] = None
    desktop_background: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SetRoleRequest(BaseModel):
    role: str


class BlockUserRequest(BaseModel):
    is_blocked: bool


class ArchiveUserRequest(BaseModel):
    is_archived: bool


class TimeTrackingRoleRequest(BaseModel):
    """Роль в модуле учёта времени: user — ведение учёта, manager — управление списком пользователей."""

    time_tracking_role: Optional[str] = None  # "user" | "manager" | null
    position: Optional[str] = Field(
        None,
        description="При назначении user/manager — непустая должность в теле или уже в профиле.",
    )


class SetPositionRequest(BaseModel):
    """Должность пользователя."""

    position: Optional[str] = None


class SetDesktopBackgroundRequest(BaseModel):
    """Путь к файлу фона рабочего стола (относительно media)."""

    path: str


class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    picture: Optional[str] = None
    role: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminBootstrapRequest(BaseModel):
    """Секрет из переменной окружения ADMIN_BOOTSTRAP_SECRET на сервере."""

    secret: str


class AdminBootstrapResponse(BaseModel):
    username: str
    password: str
    message: str = (
        "Сохраните пароль в надёжном месте. Повторный запрос вернёт ошибку. "
        "Секрет ADMIN_BOOTSTRAP_SECRET после этого можно убрать из окружения."
    )


class AdminBootstrapStatusResponse(BaseModel):
    """bootstrapAvailable — можно вызвать POST /auth/admin-bootstrap (секрет задан и запись в БД ещё не создана)."""

    bootstrap_available: bool
    credentials_in_database: bool


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime


class RoleItem(BaseModel):
    value: str
    label: str


class RoleResponse(BaseModel):
    id: int
    name: str


class RoleCreateRequest(BaseModel):
    name: str


class RoleUpdateRequest(BaseModel):
    name: str


class RolePermissionsResponse(BaseModel):
    permissions: dict


class RolePermissionsUpdateRequest(BaseModel):
    """Ключи — названия прав (например time_tracking), значения — bool."""
    permissions: Optional[dict] = None
