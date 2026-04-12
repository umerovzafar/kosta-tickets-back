"""Правила для расхода партнёра (без согласования)."""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
_expenses = _root / "expenses"
if str(_expenses) not in sys.path:
    sys.path.insert(0, str(_expenses))

from application.expense_service import is_partner_expense, validate_submit_fields  # noqa: E402


def test_is_partner_expense():
    assert is_partner_expense("partner_expense") is True
    assert is_partner_expense(" food ") is False


def test_partner_submit_relaxes_reimbursable_requirements():
    """partner_expense: не требуются projectId и документ для оплаты даже при isReimbursable=true."""
    validate_submit_fields(
        description="Партнёр",
        expense_date=date(2026, 1, 10),
        payment_deadline=None,
        amount_uzs=Decimal("100.00"),
        exchange_rate=Decimal("12500"),
        expense_type="partner_expense",
        expense_subtype="partner_fuel",
        is_reimbursable=True,
        comment=None,
        project_id=None,
        attachment_count=0,
        expense_amount_limit_uzs=None,
        payment_document_count=0,
        payment_receipt_count=0,
    )


def test_partner_submit_still_enforces_amount_limit():
    with pytest.raises(ValueError, match="exceeds"):
        validate_submit_fields(
            description="Партнёр",
            expense_date=date(2026, 1, 10),
            payment_deadline=None,
            amount_uzs=Decimal("999999"),
            exchange_rate=Decimal("12500"),
            expense_type="partner_expense",
            expense_subtype="partner_fuel",
            is_reimbursable=False,
            comment=None,
            project_id=None,
            attachment_count=0,
            expense_amount_limit_uzs=Decimal("100"),
            payment_document_count=0,
            payment_receipt_count=0,
        )
