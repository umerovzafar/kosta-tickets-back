"""Расчёт ставок и себестоимости по строке времени без привязки к ORM."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from application.hourly_rate_logic import filter_rates_by_currency, pick_rate_for_date
from application.money_amounts import money_product_hours_rate


def _d(v: Any) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v)) if v else Decimal(0)


def _scoped_rates(
    user_rates: list[Any] | None,
    project_currency: str | None,
) -> list[Any] | None:
    if not user_rates:
        return None
    if not (project_currency and str(project_currency).strip()):
        return user_rates
    s = filter_rates_by_currency(user_rates, project_currency)
    return s


def _billable_rate_for_entry(
    work_date: date,
    user_rates: list[Any] | None,
    *,
    project_currency: str | None = None,
) -> tuple[Decimal | None, str]:
    """Ставка за час (billable) в валюте проекта, действующая на дату."""
    base_cur = (project_currency or "USD").strip()[:10] or "USD"
    scoped = _scoped_rates(user_rates, project_currency)
    if not scoped:
        return None, base_cur
    rate = pick_rate_for_date(scoped, work_date)
    if not rate:
        return None, base_cur
    return _d(rate.amount), (rate.currency or base_cur).strip()[:10] or base_cur


def _cost_amount_for_entry(
    hours: Decimal,
    work_date: date,
    user_cost_rates: list[Any] | None,
    *,
    project_currency: str | None = None,
) -> tuple[Decimal, Decimal | None, str]:
    """(cost_amount, cost_rate_per_hour, currency) — в валюте проекта."""
    base_cur = (project_currency or "USD").strip()[:10] or "USD"
    scoped = _scoped_rates(user_cost_rates, project_currency)
    if not scoped:
        return Decimal(0), None, base_cur
    rate = pick_rate_for_date(scoped, work_date)
    if not rate:
        return Decimal(0), None, base_cur
    r_amt = _d(rate.amount)
    amt = money_product_hours_rate(hours, r_amt)
    return amt, r_amt, (rate.currency or base_cur).strip()[:10] or base_cur
