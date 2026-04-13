"""Pydantic-схемы для модуля отчётов time_tracking."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReportType(str, Enum):
    time = "time"
    detailed_time = "detailed-time"
    detailed_expense = "detailed-expense"
    contractor = "contractor"
    uninvoiced = "uninvoiced"


class GroupOption(str, Enum):
    tasks = "tasks"
    clients = "clients"
    projects = "projects"
    team = "team"


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


class MoneyOut(BaseModel):
    value: float
    currency: str = "USD"


class PeriodOut(BaseModel):
    dateFrom: str
    dateTo: str


# ---------------------------------------------------------------------------
# Summary responses (polymorphic by report_type)
# ---------------------------------------------------------------------------


class ReportSummaryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reportType: str = Field(alias="reportType")
    period: PeriodOut

    totalHours: Optional[float] = None
    billableHours: Optional[float] = None
    nonBillableHours: Optional[float] = None
    billableAmount: Optional[MoneyOut] = None
    unbilledAmount: Optional[MoneyOut] = None
    lineCount: Optional[int] = None

    # detailed-expense specific
    totalExpenseUzs: Optional[float] = None
    reimbursableUzs: Optional[float] = None
    nonReimbursableUzs: Optional[float] = None

    # contractor specific
    contractorHours: Optional[float] = None
    contractorCost: Optional[MoneyOut] = None

    # uninvoiced specific
    uninvoicedHours: Optional[float] = None
    amountToInvoice: Optional[MoneyOut] = None


# ---------------------------------------------------------------------------
# Table responses
# ---------------------------------------------------------------------------


class ReportTableOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rows: list[dict[str, Any]]
    totalCount: int
    page: int
    pageSize: int
    hasMore: bool


# ---------------------------------------------------------------------------
# Saved views
# ---------------------------------------------------------------------------


class SavedViewFilters(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reportType: Optional[str] = None
    group: Optional[str] = None
    dateFrom: Optional[str] = None
    dateTo: Optional[str] = None
    userIds: Optional[list[int]] = None
    projectIds: Optional[list[str]] = None
    clientIds: Optional[list[str]] = None
    includeFixedFeeProjects: Optional[bool] = None
    sort: Optional[str] = None


class SavedViewCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=500)
    filters: SavedViewFilters


class SavedViewPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(None, max_length=500)
    filters: Optional[SavedViewFilters] = None


class SavedViewOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    ownerUserId: int
    filters: dict[str, Any]
    createdAt: datetime
    updatedAt: Optional[datetime] = None

    @field_validator("filters", mode="before")
    @classmethod
    def parse_filters(cls, v: Any) -> Any:
        if isinstance(v, str):
            return json.loads(v)
        return v


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


class SnapshotCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=500)
    reportType: str
    group: Optional[str] = None
    filters: SavedViewFilters


class SnapshotRowPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    overrides: dict[str, Any]


class SnapshotRowOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    sortOrder: int
    sourceType: str
    sourceId: str
    data: dict[str, Any]
    overrides: Optional[dict[str, Any]] = None
    editedByUserId: Optional[int] = None
    editedAt: Optional[datetime] = None

    @field_validator("data", mode="before")
    @classmethod
    def parse_data(cls, v: Any) -> Any:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("overrides", mode="before")
    @classmethod
    def parse_overrides(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            return json.loads(v)
        return v


class SnapshotOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    reportType: str
    groupBy: Optional[str] = None
    filters: dict[str, Any]
    version: int
    createdByUserId: int
    createdAt: datetime
    updatedAt: Optional[datetime] = None
    rowCount: Optional[int] = None
    rows: Optional[list[SnapshotRowOut]] = None

    @field_validator("filters", mode="before")
    @classmethod
    def parse_filters(cls, v: Any) -> Any:
        if isinstance(v, str):
            return json.loads(v)
        return v


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


class ReportMetaOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reportTypes: list[str]
    groupOptions: list[str]
    pageSizeMax: int = 500
    currencies: list[str] = ["UZS", "USD", "EUR"]


class ReportUserForFilterOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    displayName: Optional[str] = None
    email: Optional[str] = None
