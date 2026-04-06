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


class WeeklyCapacityPatchBody(BaseModel):
    """Только норма часов в неделю (для профиля / gateway)."""

    weekly_capacity_hours: Decimal = Field(..., gt=0, le=168, description="Часов в неделю (ёмкость)")


class UserUpsertBody(BaseModel):
    """Тело запроса для создания/обновления пользователя (синхронизация из auth)."""

    model_config = ConfigDict(populate_by_name=True)

    auth_user_id: int = Field(..., alias="authUserId")
    email: str
    display_name: Optional[str] = Field(None, alias="displayName")
    picture: Optional[str] = None
    role: str = ""
    is_blocked: bool = Field(False, alias="isBlocked")
    is_archived: bool = Field(False, alias="isArchived")
    weekly_capacity_hours: Optional[Decimal] = Field(
        None,
        alias="weeklyCapacityHours",
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


class TimeManagerClientOut(BaseModel):
    """Клиент time manager (настройки биллинга)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    address: Optional[str] = None
    currency: str
    invoice_due_mode: str
    invoice_due_days_after_issue: Optional[int] = None
    tax_percent: Optional[Decimal] = None
    tax2_percent: Optional[Decimal] = None
    discount_percent: Optional[Decimal] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class TimeManagerClientCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=500)
    address: Optional[str] = None
    currency: str = Field("USD", max_length=10)
    invoice_due_mode: str = Field("custom", alias="invoiceDueMode", max_length=50)
    invoice_due_days_after_issue: Optional[int] = Field(
        None,
        alias="invoiceDueDaysAfterIssue",
        ge=0,
        le=3650,
    )
    tax_percent: Optional[Decimal] = Field(None, alias="taxPercent", ge=0, le=100)
    tax2_percent: Optional[Decimal] = Field(None, alias="tax2Percent", ge=0, le=100)
    discount_percent: Optional[Decimal] = Field(None, alias="discountPercent", ge=0, le=100)


class TimeManagerClientPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(None, max_length=500)
    address: Optional[str] = None
    currency: Optional[str] = Field(None, max_length=10)
    invoice_due_mode: Optional[str] = Field(None, alias="invoiceDueMode", max_length=50)
    invoice_due_days_after_issue: Optional[int] = Field(
        None,
        alias="invoiceDueDaysAfterIssue",
        ge=0,
        le=3650,
    )
    tax_percent: Optional[Decimal] = Field(None, alias="taxPercent", ge=0, le=100)
    tax2_percent: Optional[Decimal] = Field(None, alias="tax2Percent", ge=0, le=100)
    discount_percent: Optional[Decimal] = Field(None, alias="discountPercent", ge=0, le=100)
