"""Бизнес-правила расчётов и статусов заявок на расход (ТЗ TZ-expenses-backend.md)."""

from decimal import Decimal, ROUND_HALF_UP

# §5.1
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

# §4 — коды типов расходов
ALLOWED_EXPENSE_TYPES = frozenset(
    {
        "transport",
        "food",
        "accommodation",
        "purchase",
        "services",
        "entertainment",
        "client_expense",
        "other",
    }
)

# Старые коды из ранних версий — приводим к актуальным при записи
_EXPENSE_TYPE_ALIASES = {"meals": "food", "office": "services"}

# §3.2 paymentMethod
ALLOWED_PAYMENT_METHODS = frozenset({"cash", "card", "transfer", "other_payment"})

# Реестр «утверждённых» (§10)
REGISTRY_STATUSES = frozenset({"approved", "paid", "closed"})


def calc_equivalent(amount_uzs: Decimal, exchange_rate: Decimal) -> Decimal:
    """equivalentAmount в USD: UZS / (UZS за 1 USD)."""
    if exchange_rate <= 0:
        raise ValueError("exchange_rate must be positive")
    return (amount_uzs / exchange_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def validate_expense_type(code: str) -> str:
    c = (code or "").strip()
    c = _EXPENSE_TYPE_ALIASES.get(c, c)
    if c not in ALLOWED_EXPENSE_TYPES:
        raise ValueError(
            f"Недопустимый expenseType: {code!r}. Допустимо: {', '.join(sorted(ALLOWED_EXPENSE_TYPES))}"
        )
    return c


def normalize_payment_method(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    k = s.lower()
    if k not in ALLOWED_PAYMENT_METHODS:
        raise ValueError(
            f"Недопустимый paymentMethod: {v!r}. Допустимо: {', '.join(sorted(ALLOWED_PAYMENT_METHODS))} или пусто"
        )
    return k


def validate_submit_fields(
    *,
    description: str,
    expense_date,
    payment_deadline=None,
    amount_uzs: Decimal,
    exchange_rate: Decimal,
    expense_type: str,
    is_reimbursable: bool,
    comment: str | None,
    attachment_count: int,
    expense_amount_limit_uzs: Decimal | None,
    payment_document_count: int = 0,
    payment_receipt_count: int = 0,
) -> None:
    if not (description or "").strip():
        raise ValueError("description is required")
    if expense_date is None:
        raise ValueError("expenseDate is required")
    if payment_deadline is not None and expense_date is not None and payment_deadline < expense_date:
        raise ValueError("Конечный срок оплаты не может быть раньше даты расхода")
    if amount_uzs is None or amount_uzs <= 0:
        raise ValueError("amountUzs must be greater than 0")
    if exchange_rate is None or exchange_rate <= 0:
        raise ValueError("exchangeRate must be greater than 0")
    validate_expense_type(expense_type)
    if is_reimbursable is None:
        raise ValueError("isReimbursable is required")
    if expense_amount_limit_uzs is not None and amount_uzs > expense_amount_limit_uzs:
        raise ValueError("amountUzs exceeds allowed limit; additional approval may be required")
    if is_reimbursable:
        # Этап 1: до отправки нужен документ на оплату. Квитанция — после подтверждения выплаты (статус paid).
        has_typed = payment_document_count > 0 or payment_receipt_count > 0
        if has_typed:
            if payment_document_count < 1:
                raise ValueError(
                    "Для возмещаемого расхода загрузите документ на оплату (attachmentKind=payment_document) перед отправкой на согласование"
                )
        elif attachment_count < 1:
            raise ValueError("At least one attachment is required for reimbursable expenses")
    if (expense_type or "").strip() == "other" and not (comment or "").strip():
        raise ValueError("comment is required when expenseType is other")


def assert_attachment_upload_allowed(
    *,
    status: str,
    attachment_kind: str | None,
    is_admin: bool,
) -> None:
    """Правила двухэтапных вложений: документ на оплату до выплаты; квитанция — после подтверждения оплаты."""
    if is_admin:
        return
    kind = (attachment_kind or "").strip() or None
    if kind == "payment_document":
        if status not in ("draft", "revision_required", "pending_approval", "approved"):
            raise ValueError(
                "Документ на оплату можно загрузить до подтверждения выплаты (статусы: черновик, на согласовании, утверждена)."
            )
    elif kind == "payment_receipt":
        if status not in ("paid", "closed"):
            raise ValueError(
                "Квитанцию об оплате загружают после того, как модератор подтвердит выплату (статус «Выплачено»)."
            )
    else:
        if status in ("paid", "closed"):
            raise ValueError(
                "После оплаты загружайте только квитанцию и укажите attachmentKind=payment_receipt"
            )
        if status not in ("draft", "revision_required", "pending_approval", "approved"):
            raise ValueError("Вложения в этом статусе недоступны")


def reimbursable_requires_receipt_before_close(payment_receipt_count: int) -> None:
    """После выплаты автор должен приложить квитанцию; закрытие — только с квитанцией."""
    if payment_receipt_count < 1:
        raise ValueError(
            "Загрузите квитанцию об оплате (attachmentKind=payment_receipt) перед закрытием возмещаемой заявки"
        )
