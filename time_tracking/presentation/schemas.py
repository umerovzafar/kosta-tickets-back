from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
    weekly_capacity_hours: Decimal = Field(
        default=Decimal("35"),
        description="Норма часов в неделю (для ёмкости за период)",
    )
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
    weekly_capacity_hours: Optional[Decimal] = Field(
        None,
        description="Норма часов в неделю; по умолчанию 35 при создании",
    )


class RateKind(str, Enum):
    billable = "billable"
    cost = "cost"


class HourlyRateOut(BaseModel):
    """Почасовая ставка по умолчанию (оплачиваемая или себестоимость)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    auth_user_id: int
    rate_kind: str
    amount: Decimal
    currency: str
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class HourlyRateCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rate_kind: RateKind = Field(..., alias="rateKind")
    amount: Decimal
    currency: str = "USD"
    valid_from: Optional[date] = Field(None, alias="validFrom")
    valid_to: Optional[date] = Field(None, alias="validTo")


class HourlyRatePatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    valid_from: Optional[date] = Field(None, alias="validFrom")
    valid_to: Optional[date] = Field(None, alias="validTo")


class TeamWorkloadSummaryOut(BaseModel):
    total_hours: Decimal
    team_capacity_hours: Decimal
    billable_hours: Decimal
    non_billable_hours: Decimal
    team_workload_percent: int


class TeamWorkloadMemberOut(BaseModel):
    auth_user_id: int
    display_name: Optional[str] = None
    email: str
    capacity_hours: Decimal
    total_hours: Decimal
    billable_hours: Decimal
    non_billable_hours: Decimal
    workload_percent: int


class TeamWorkloadOut(BaseModel):
    date_from: date
    date_to: date
    period_days: int
    summary: TeamWorkloadSummaryOut
    members: list[TeamWorkloadMemberOut]


class TimeEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    auth_user_id: int
    work_date: date
    hours: Decimal
    is_billable: bool
    project_id: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class TimeEntryCreateBody(BaseModel):
    work_date: date
    hours: Decimal
    is_billable: bool = True
    project_id: Optional[str] = None
    description: Optional[str] = None


class TimeEntryPatchBody(BaseModel):
    work_date: Optional[date] = None
    hours: Optional[Decimal] = None
    is_billable: Optional[bool] = None
    project_id: Optional[str] = None
    description: Optional[str] = None
