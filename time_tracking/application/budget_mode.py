"""Правила бюджета проекта: часы, сумма или оба лимита сразу."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from application.services.reports._base import _d, _ZERO


def budget_mode(p: Any) -> str:
    """Режим по фактическим лимитам: none | hours | money | hours_and_money."""
    h = p.budget_hours is not None and _d(p.budget_hours) > 0
    m = p.budget_amount is not None and _d(p.budget_amount) > 0
    if h and m:
        return "hours_and_money"
    if h:
        return "hours"
    if m:
        return "money"
    return "none"


def normalize_budget_type_for_persist(
    budget_hours: Decimal | None,
    budget_amount: Decimal | None,
) -> str | None:
    """Значение для колонки budget_type: при двух лимитах — hours_and_money; иначе None если бюджета нет."""
    h = budget_hours is not None and _d(budget_hours) > 0
    m = budget_amount is not None and _d(budget_amount) > 0
    if h and m:
        return "hours_and_money"
    if h:
        return "hours"
    if m:
        return "money"
    return None


def budget_limit_hours(p: Any) -> Decimal:
    v = p.budget_hours
    if v is None or _d(v) <= 0:
        return _ZERO
    return _d(v)


def budget_limit_money(p: Any) -> Decimal:
    v = p.budget_amount
    if v is None or _d(v) <= 0:
        return _ZERO
    return _d(v)
