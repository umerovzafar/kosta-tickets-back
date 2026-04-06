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
