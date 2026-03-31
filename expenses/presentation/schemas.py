from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime


class AttachmentOut(BaseModel):
    id: str
    kind: str
    file_path: str

    model_config = {"from_attributes": False}


class ExpenseRequestOut(BaseModel):
    id: int
    public_id: str
    status: str
    request_date: date
    created_by_user_id: int
    initiator_name: str
    department: Optional[str] = None
    budget_category: Optional[str] = None
    counterparty: Optional[str] = None
    amount: Decimal
    currency: str
    expense_date: date
    description: Optional[str] = None
    reimbursement_type: str
    rejection_reason: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by_user_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    attachments: list[AttachmentOut] = Field(default_factory=list)


class ExpenseRequestCreateBody(BaseModel):
    """По умолчанию заявка сразу уходит на модерацию (pending). Черновик (draft) — опционально."""

    request_date: date
    department: Optional[str] = None
    budget_category: Optional[str] = None
    counterparty: Optional[str] = None
    amount: Decimal = Field(gt=0)
    currency: str = "UZS"
    expense_date: date
    description: Optional[str] = None
    reimbursement_type: Literal["reimbursable", "non_reimbursable"]
    status: Literal["draft", "pending"] = "pending"


class ExpenseRequestPatchBody(BaseModel):
    request_date: Optional[date] = None
    department: Optional[str] = None
    budget_category: Optional[str] = None
    counterparty: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    expense_date: Optional[date] = None
    description: Optional[str] = None
    reimbursement_type: Optional[Literal["reimbursable", "non_reimbursable"]] = None


class ExpenseStatusBody(BaseModel):
    """Одобрение или отклонение. При отклонении обязателен комментарий (rejection_reason)."""

    status: Literal["approved", "rejected"]
    rejection_reason: Optional[str] = Field(None, description="Комментарий при отклонении (обязателен)")

    @model_validator(mode="after")
    def reject_requires_comment(self):
        if self.status == "rejected":
            if not (self.rejection_reason or "").strip():
                raise ValueError("Укажите комментарий с причиной отклонения заявки")
        return self


class ExpenseListResponse(BaseModel):
    items: list[ExpenseRequestOut]
    total: int
    skip: int
    limit: int


class SummaryReportOut(BaseModel):
    date_from: date
    date_to: date
    currency: str
    total_amount: Decimal
    operations_count: int
    approved_count: int


class DynamicsPoint(BaseModel):
    date: date
    total_amount: Decimal
    count: int


class CalendarDayOut(BaseModel):
    date: date
    total_amount: Decimal
    count: int
    has_expenses: bool


class CalendarReportOut(BaseModel):
    year: int
    month: int
    days: list[CalendarDayOut]


class ByDateReportOut(BaseModel):
    date: date
    total_amount: Decimal
    approved_total: Decimal
    approved_count: int
    items: list[ExpenseRequestOut]
