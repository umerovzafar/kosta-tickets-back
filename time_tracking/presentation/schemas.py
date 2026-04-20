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
    team_capacity_hours: Decimal = Field(
        ...,
        description="Ёмкость за период (Σ weekly×дней/7), для team_workload_percent",
    )
    team_weekly_capacity_hours: Decimal = Field(
        ...,
        description="Сумма недельных норм участников (ч/нед), карточка «Ёмкость команды»",
    )
    billable_hours: Decimal
    non_billable_hours: Decimal
    team_workload_percent: int


class TeamWorkloadMemberOut(BaseModel):
    auth_user_id: int
    display_name: Optional[str] = None
    email: str
    picture: Optional[str] = None
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
    project_id: Optional[str] = None
    client_id: Optional[str] = None
    project_name: Optional[str] = None


class TimeEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    auth_user_id: int
    work_date: date
    # Источник истины — целое число секунд (устраняет «1 секунду» на round-trip).
    duration_seconds: int = Field(..., alias="durationSeconds")
    # Фактические часы (для детальных экранов/экспорта).
    hours: Decimal
    # Округлённые часы (для сводных отчётов и счетов).
    rounded_hours: Decimal = Field(..., alias="roundedHours")
    is_billable: bool
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class TimeEntryCreateBody(BaseModel):
    """Тело POST; camelCase как на фронте (через gateway).

    Фронт должен присылать `durationSeconds` (источник истины). `hours` оставлено для обратной
    совместимости: если прислали только его, сервер сам посчитает секунды (round HALF_UP).
    """

    model_config = ConfigDict(populate_by_name=True)

    work_date: date = Field(..., alias="workDate")
    duration_seconds: Optional[int] = Field(
        None,
        alias="durationSeconds",
        ge=1,
        description="Длительность в секундах (канон). Приоритетнее hours.",
    )
    hours: Optional[Decimal] = Field(
        None,
        description="Длительность в часах (обратная совместимость). Если передано, seconds = round(hours*3600).",
    )
    is_billable: bool = Field(True, alias="isBillable")
    project_id: Optional[str] = Field(None, alias="projectId")
    task_id: Optional[str] = Field(None, alias="taskId")
    description: Optional[str] = None


class TimeEntryPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    work_date: Optional[date] = Field(None, alias="workDate")
    duration_seconds: Optional[int] = Field(None, alias="durationSeconds", ge=1)
    hours: Optional[Decimal] = None
    is_billable: Optional[bool] = Field(None, alias="isBillable")
    project_id: Optional[str] = Field(None, alias="projectId")
    task_id: Optional[str] = Field(None, alias="taskId")
    description: Optional[str] = None


class ProjectAccessOut(BaseModel):
    """Список id проектов, доступных пользователю для списания времени."""

    model_config = ConfigDict(populate_by_name=True)

    project_ids: list[str] = Field(..., alias="projectIds")


class ProjectAccessPutBody(BaseModel):
    """Полная замена списка проектов с доступом (пустой список — ни один проект недоступен)."""

    model_config = ConfigDict(populate_by_name=True)

    project_ids: list[str] = Field(default_factory=list, alias="projectIds")
    granted_by_auth_user_id: Optional[int] = Field(
        None,
        alias="grantedByAuthUserId",
        description="Кто выдал доступ (прокси gateway подставляет текущего пользователя).",
    )


class TimeManagerClientContactOut(BaseModel):
    """Дополнительное контактное лицо клиента."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    client_id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    sort_order: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


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
    phone: Optional[str] = None
    email: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    extra_contacts: list[TimeManagerClientContactOut] = Field(default_factory=list)
    is_archived: bool = Field(False, alias="isArchived")
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
    phone: Optional[str] = Field(None, max_length=64)
    email: Optional[str] = Field(None, max_length=320)
    contact_name: Optional[str] = Field(None, alias="contactName", max_length=500)
    contact_phone: Optional[str] = Field(None, alias="contactPhone", max_length=64)
    contact_email: Optional[str] = Field(None, alias="contactEmail", max_length=320)
    is_archived: bool = Field(False, alias="isArchived")


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
    phone: Optional[str] = Field(None, max_length=64)
    email: Optional[str] = Field(None, max_length=320)
    contact_name: Optional[str] = Field(None, alias="contactName", max_length=500)
    contact_phone: Optional[str] = Field(None, alias="contactPhone", max_length=64)
    contact_email: Optional[str] = Field(None, alias="contactEmail", max_length=320)
    is_archived: Optional[bool] = Field(None, alias="isArchived")


class TimeManagerClientContactCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=500)
    phone: Optional[str] = Field(None, max_length=64)
    email: Optional[str] = Field(None, max_length=320)
    sort_order: Optional[int] = Field(None, alias="sortOrder")


class TimeManagerClientContactPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=64)
    email: Optional[str] = Field(None, max_length=320)
    sort_order: Optional[int] = Field(None, alias="sortOrder")


class TimeManagerClientTaskOut(BaseModel):
    """Задача клиента (справочник для отчётов и форм)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    client_id: str
    name: str
    default_billable_rate: Optional[Decimal] = None
    billable_by_default: bool
    common_for_future_projects: bool
    add_to_existing_projects: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class TimeManagerClientTaskCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=500)
    default_billable_rate: Optional[Decimal] = Field(None, alias="defaultBillableRate", ge=0)
    billable_by_default: bool = Field(True, alias="billableByDefault")
    common_for_future_projects: bool = Field(False, alias="commonForFutureProjects")
    add_to_existing_projects: bool = Field(False, alias="addToExistingProjects")


class TimeManagerClientTaskPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(None, max_length=500)
    default_billable_rate: Optional[Decimal] = Field(None, alias="defaultBillableRate", ge=0)
    billable_by_default: Optional[bool] = Field(None, alias="billableByDefault")
    common_for_future_projects: Optional[bool] = Field(None, alias="commonForFutureProjects")
    add_to_existing_projects: Optional[bool] = Field(None, alias="addToExistingProjects")


class TimeManagerClientExpenseCategoryOut(BaseModel):
    """Категория расхода клиента (справочник)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    client_id: str
    name: str
    has_unit_price: bool
    is_archived: bool
    sort_order: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    usage_count: int = 0
    deletable: bool = True


class TimeManagerClientExpenseCategoryCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=500)
    has_unit_price: bool = Field(False, alias="hasUnitPrice")
    sort_order: Optional[int] = Field(None, alias="sortOrder")


class TimeManagerClientExpenseCategoryPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(None, max_length=500)
    has_unit_price: Optional[bool] = Field(None, alias="hasUnitPrice")
    is_archived: Optional[bool] = Field(None, alias="isArchived")
    sort_order: Optional[int] = Field(None, alias="sortOrder")


class ProjectReportVisibility(str, Enum):
    managers_only = "managers_only"
    all_assigned = "all_assigned"


class ProjectType(str, Enum):
    """Тип биллинга проекта (вкладки на UI)."""

    time_and_materials = "time_and_materials"
    fixed_fee = "fixed_fee"
    non_billable = "non_billable"


class ProjectCurrency(str, Enum):
    """Поддерживаемые валюты проекта."""

    USD = "USD"   # Доллар США ($)
    UZS = "UZS"   # Узбекский сум (сўм)
    EUR = "EUR"   # Евро (€)
    RUB = "RUB"   # Российский рубль (₽)
    GBP = "GBP"   # Британский фунт (£)


class TimeManagerClientProjectOut(BaseModel):
    """Проект клиента time manager."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    client_id: str
    name: str
    code: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None
    report_visibility: str
    project_type: str
    currency: str = "USD"
    billable_rate_type: Optional[str] = None
    budget_type: Optional[str] = None
    budget_amount: Optional[Decimal] = None
    budget_hours: Optional[Decimal] = None
    budget_resets_every_month: bool = False
    budget_includes_expenses: bool = False
    send_budget_alerts: bool = False
    budget_alert_threshold_percent: Optional[Decimal] = None
    fixed_fee_amount: Optional[Decimal] = None
    is_archived: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    usage_count: int = 0
    deletable: bool = True


class TimeManagerClientProjectCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=500)
    code: Optional[str] = Field(None, max_length=64)
    start_date: Optional[date] = Field(None, alias="startDate")
    end_date: Optional[date] = Field(None, alias="endDate")
    notes: Optional[str] = None
    report_visibility: ProjectReportVisibility = Field(
        ProjectReportVisibility.managers_only,
        alias="reportVisibility",
    )
    project_type: ProjectType = Field(ProjectType.time_and_materials, alias="projectType")
    currency: ProjectCurrency = Field(ProjectCurrency.USD, description="Валюта проекта")
    billable_rate_type: Optional[str] = Field(None, max_length=64, alias="billableRateType")
    budget_type: Optional[str] = Field(None, max_length=64, alias="budgetType")
    budget_amount: Optional[Decimal] = Field(None, ge=0, alias="budgetAmount")
    budget_hours: Optional[Decimal] = Field(None, ge=0, alias="budgetHours")
    budget_resets_every_month: bool = Field(False, alias="budgetResetsEveryMonth")
    budget_includes_expenses: bool = Field(False, alias="budgetIncludesExpenses")
    send_budget_alerts: bool = Field(False, alias="sendBudgetAlerts")
    budget_alert_threshold_percent: Optional[Decimal] = Field(
        None,
        ge=0,
        le=100,
        alias="budgetAlertThresholdPercent",
    )
    fixed_fee_amount: Optional[Decimal] = Field(None, ge=0, alias="fixedFeeAmount")
    is_archived: bool = Field(False, alias="isArchived")


class TimeManagerClientProjectPatchBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(None, max_length=500)
    code: Optional[str] = Field(None, max_length=64)
    start_date: Optional[date] = Field(None, alias="startDate")
    end_date: Optional[date] = Field(None, alias="endDate")
    notes: Optional[str] = None
    report_visibility: Optional[ProjectReportVisibility] = Field(None, alias="reportVisibility")
    project_type: Optional[ProjectType] = Field(None, alias="projectType")
    currency: Optional[ProjectCurrency] = Field(None, description="Валюта проекта")
    billable_rate_type: Optional[str] = Field(None, max_length=64, alias="billableRateType")
    budget_type: Optional[str] = Field(None, max_length=64, alias="budgetType")
    budget_amount: Optional[Decimal] = Field(None, ge=0, alias="budgetAmount")
    budget_hours: Optional[Decimal] = Field(None, ge=0, alias="budgetHours")
    budget_resets_every_month: Optional[bool] = Field(None, alias="budgetResetsEveryMonth")
    budget_includes_expenses: Optional[bool] = Field(None, alias="budgetIncludesExpenses")
    send_budget_alerts: Optional[bool] = Field(None, alias="sendBudgetAlerts")
    budget_alert_threshold_percent: Optional[Decimal] = Field(
        None,
        ge=0,
        le=100,
        alias="budgetAlertThresholdPercent",
    )
    fixed_fee_amount: Optional[Decimal] = Field(None, ge=0, alias="fixedFeeAmount")
    is_archived: Optional[bool] = Field(None, alias="isArchived")


class RoundingMode(str, Enum):
    up = "up"
    nearest = "nearest"


class RoundingSettingsOut(BaseModel):
    """Глобальные настройки округления учёта времени."""

    model_config = ConfigDict(populate_by_name=True)

    rounding_enabled: bool = Field(..., alias="roundingEnabled")
    rounding_mode: RoundingMode = Field(..., alias="roundingMode")
    rounding_step_minutes: int = Field(..., alias="roundingStepMinutes", ge=1, le=60)


class RoundingSettingsPutBody(BaseModel):
    """Тело PUT; все поля обязательны."""

    model_config = ConfigDict(populate_by_name=True)

    rounding_enabled: bool = Field(..., alias="roundingEnabled")
    rounding_mode: RoundingMode = Field(..., alias="roundingMode")
    rounding_step_minutes: int = Field(..., alias="roundingStepMinutes", ge=1, le=60)


class TimeManagerClientProjectCodeHintOut(BaseModel):
    """Подсказка для поля кода проекта (последний код и простой следующий)."""

    last_code: Optional[str] = None
    suggested_next: Optional[str] = None
