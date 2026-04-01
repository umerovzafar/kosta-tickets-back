"""Бизнес-правила расчётов и статусов заявок на расход."""

from decimal import Decimal, ROUND_HALF_UP

ALLOWED_STATUSES = frozenset(
    {
        "draft",
        "pending_approval",
        "revision_required",
        "approved",
        "rejected",
        "paid",
        "closed",
        "not_reimbursable",
        "withdrawn",
    }
)


def calc_equivalent(amount_uzs: Decimal, exchange_rate: Decimal) -> Decimal:
    if exchange_rate <= 0:
        raise ValueError("exchange_rate must be positive")
    return (amount_uzs / exchange_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_submit_fields(
    *,
    description: str,
    expense_date,
    amount_uzs: Decimal,
    exchange_rate: Decimal,
    expense_type: str,
    is_reimbursable: bool,
    comment: str | None,
    attachment_count: int,
    expense_amount_limit_uzs: Decimal | None,
) -> None:
    if not (description or "").strip():
        raise ValueError("description is required")
    if expense_date is None:
        raise ValueError("expenseDate is required")
    if amount_uzs is None or amount_uzs <= 0:
        raise ValueError("amountUzs must be greater than 0")
    if exchange_rate is None or exchange_rate <= 0:
        raise ValueError("exchangeRate must be greater than 0")
    if not (expense_type or "").strip():
        raise ValueError("expenseType is required")
    if is_reimbursable is None:
        raise ValueError("isReimbursable is required")
    if expense_amount_limit_uzs is not None and amount_uzs > expense_amount_limit_uzs:
        raise ValueError("amountUzs exceeds allowed limit; additional approval may be required")
    if is_reimbursable and attachment_count < 1:
        raise ValueError("At least one attachment is required for reimbursable expenses")
    if (expense_type or "").strip() == "other" and not (comment or "").strip():
        raise ValueError("comment is required when expenseType is other")
