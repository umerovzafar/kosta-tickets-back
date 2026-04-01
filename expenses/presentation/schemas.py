from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime


# --- Вложения / история / аудит ---


class AttachmentOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    expense_request_id: str = Field(serialization_alias="expenseRequestId")
    file_name: str = Field(serialization_alias="fileName")
    storage_key: str = Field(serialization_alias="storageKey")
    mime_type: Optional[str] = Field(None, serialization_alias="mimeType")
    size_bytes: int = Field(serialization_alias="sizeBytes")
    uploaded_by_user_id: int = Field(serialization_alias="uploadedByUserId")
    uploaded_at: datetime = Field(serialization_alias="uploadedAt")


class StatusHistoryOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    expense_request_id: str = Field(serialization_alias="expenseRequestId")
    from_status: Optional[str] = Field(None, serialization_alias="fromStatus")
    to_status: str = Field(serialization_alias="toStatus")
    changed_by_user_id: int = Field(serialization_alias="changedByUserId")
    comment: Optional[str] = None
    changed_at: datetime = Field(serialization_alias="changedAt")


class AuditLogOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    expense_request_id: str = Field(serialization_alias="expenseRequestId")
    action: str
    field_name: Optional[str] = Field(None, serialization_alias="fieldName")
    old_value: Optional[str] = Field(None, serialization_alias="oldValue")
    new_value: Optional[str] = Field(None, serialization_alias="newValue")
    performed_by_user_id: int = Field(serialization_alias="performedByUserId")
    performed_at: datetime = Field(serialization_alias="performedAt")


class ExpenseRequestListItemOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    description: str
    expense_date: date = Field(serialization_alias="expenseDate")
    amount_uzs: Decimal = Field(serialization_alias="amountUzs")
    exchange_rate: Decimal = Field(serialization_alias="exchangeRate")
    equivalent_amount: Decimal = Field(serialization_alias="equivalentAmount")
    expense_type: str = Field(serialization_alias="expenseType")
    expense_subtype: Optional[str] = Field(None, serialization_alias="expenseSubtype")
    is_reimbursable: bool = Field(serialization_alias="isReimbursable")
    payment_method: Optional[str] = Field(None, serialization_alias="paymentMethod")
    department_id: Optional[str] = Field(None, serialization_alias="departmentId")
    project_id: Optional[str] = Field(None, serialization_alias="projectId")
    vendor: Optional[str] = None
    business_purpose: Optional[str] = Field(None, serialization_alias="businessPurpose")
    comment: Optional[str] = None
    status: str
    current_approver_id: Optional[int] = Field(None, serialization_alias="currentApproverId")
    created_by_user_id: int = Field(serialization_alias="createdByUserId")
    updated_by_user_id: int = Field(serialization_alias="updatedByUserId")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
    submitted_at: Optional[datetime] = Field(None, serialization_alias="submittedAt")
    approved_at: Optional[datetime] = Field(None, serialization_alias="approvedAt")
    rejected_at: Optional[datetime] = Field(None, serialization_alias="rejectedAt")
    paid_at: Optional[datetime] = Field(None, serialization_alias="paidAt")
    closed_at: Optional[datetime] = Field(None, serialization_alias="closedAt")
    withdrawn_at: Optional[datetime] = Field(None, serialization_alias="withdrawnAt")
    attachments_count: int = Field(0, serialization_alias="attachmentsCount")


class ExpenseRequestDetailOut(ExpenseRequestListItemOut):
    attachments: list[AttachmentOut] = Field(default_factory=list)
    status_history: list[StatusHistoryOut] = Field(default_factory=list, serialization_alias="statusHistory")
    audit_logs: list[AuditLogOut] = Field(default_factory=list, serialization_alias="auditLog")


class ExpenseListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[ExpenseRequestListItemOut]
    total: int
    skip: int
    limit: int


class ExpenseCreateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    description: str = ""
    expense_date: Optional[date] = Field(None, validation_alias=AliasChoices("expenseDate", "expense_date"))
    amount_uzs: Optional[Decimal] = Field(None, validation_alias=AliasChoices("amountUzs", "amount_uzs"))
    exchange_rate: Optional[Decimal] = Field(None, validation_alias=AliasChoices("exchangeRate", "exchange_rate"))
    expense_type: str = "other"
    expense_subtype: Optional[str] = Field(None, validation_alias=AliasChoices("expenseSubtype", "expense_subtype"))
    is_reimbursable: bool = Field(True, validation_alias=AliasChoices("isReimbursable", "is_reimbursable"))
    payment_method: Optional[str] = Field(None, validation_alias=AliasChoices("paymentMethod", "payment_method"))
    department_id: Optional[str] = Field(None, validation_alias=AliasChoices("departmentId", "department_id"))
    project_id: Optional[str] = Field(None, validation_alias=AliasChoices("projectId", "project_id"))
    vendor: Optional[str] = None
    business_purpose: Optional[str] = Field(None, validation_alias=AliasChoices("businessPurpose", "business_purpose"))
    comment: Optional[str] = None
    current_approver_id: Optional[int] = Field(None, validation_alias=AliasChoices("currentApproverId", "current_approver_id"))

    @field_validator("amount_uzs", "exchange_rate", mode="before")
    @classmethod
    def empty_to_none(cls, v: Any) -> Any:
        return v


class ExpenseUpdateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    description: Optional[str] = None
    expense_date: Optional[date] = Field(None, validation_alias=AliasChoices("expenseDate", "expense_date"))
    amount_uzs: Optional[Decimal] = Field(None, validation_alias=AliasChoices("amountUzs", "amount_uzs"))
    exchange_rate: Optional[Decimal] = Field(None, validation_alias=AliasChoices("exchangeRate", "exchange_rate"))
    expense_type: Optional[str] = Field(None, validation_alias=AliasChoices("expenseType", "expense_type"))
    expense_subtype: Optional[str] = Field(None, validation_alias=AliasChoices("expenseSubtype", "expense_subtype"))
    is_reimbursable: Optional[bool] = Field(None, validation_alias=AliasChoices("isReimbursable", "is_reimbursable"))
    payment_method: Optional[str] = Field(None, validation_alias=AliasChoices("paymentMethod", "payment_method"))
    department_id: Optional[str] = Field(None, validation_alias=AliasChoices("departmentId", "department_id"))
    project_id: Optional[str] = Field(None, validation_alias=AliasChoices("projectId", "project_id"))
    vendor: Optional[str] = None
    business_purpose: Optional[str] = Field(None, validation_alias=AliasChoices("businessPurpose", "business_purpose"))
    comment: Optional[str] = None
    current_approver_id: Optional[int] = Field(None, validation_alias=AliasChoices("currentApproverId", "current_approver_id"))


class RejectBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reason: str = Field(..., min_length=1, validation_alias=AliasChoices("reason", "rejectionReason", "rejection_reason"))


class ReviseBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    comment: str = Field(..., min_length=1)


class ExpenseTypeRefOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    label: str
    sort_order: int = Field(serialization_alias="sortOrder")


class DepartmentRefOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str


class ProjectRefOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str


class ExchangeRateOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: date
    rate: Decimal
    pair_label: str = Field(serialization_alias="pairLabel")
