from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: Optional[str]
    picture: Optional[str]
    role: str
    position: Optional[str] = None
    is_blocked: bool = False
    is_archived: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    time_tracking_role: Optional[str] = None
    desktop_background: Optional[str] = None


class UserDetailResponse(BaseModel):
    id: int
    azure_oid: str
    email: str
    display_name: Optional[str]
    picture: Optional[str]
    role: str
    position: Optional[str] = None
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

    time_tracking_role: Optional[str] = None


class SetPositionRequest(BaseModel):
    """Должность пользователя."""

    position: Optional[str] = None
