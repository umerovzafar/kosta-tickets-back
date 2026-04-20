"""Расчёт billable в валюте проекта с конвертацией по курсу ЦБ."""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.fx_cbu import (
    FxUnavailableError,
    cross_rate_to_project_currency,
    round_money,
)
from application.hourly_rate_logic import pick_rate_for_date
from infrastructure.config import get_settings
from infrastructure.models import TimeEntryModel, TimeManagerClientProjectModel, UserHourlyRateModel
from infrastructure.repository_shared import _to_decimal

if TYPE_CHECKING:
    pass

_LOG = logging.getLogger(__name__)


class FxBillableComputationError(Exception):
    """Невозможно посчитать billable (например, ЦБ недоступен при FX_SOFT_FAIL=false)."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def _norm_ccy(s: str | None, default: str = "USD") -> str:
    x = (s or default).strip().upper()[:10]
    return x if x else default


async def apply_billable_to_entry(session: AsyncSession, row: TimeEntryModel) -> None:
    """Заполняет billable_* на записи времени (и сбрасывает при нулевом billable)."""
    settings = get_settings()
    hours = _to_decimal(row.hours)
    proj_currency = "USD"
    brt: str | None = None

    if not row.is_billable:
        pc = "USD"
        if row.project_id:
            proj_nb = (
                await session.execute(
                    select(TimeManagerClientProjectModel).where(TimeManagerClientProjectModel.id == row.project_id)
                )
            ).scalar_one_or_none()
            if proj_nb:
                pc = _norm_ccy(proj_nb.currency, "USD")
        _clear_billable(row, pc)
        return

    if not row.project_id:
        await _billable_without_project(session, row, hours)
        return

    proj = (
        await session.execute(
            select(TimeManagerClientProjectModel).where(TimeManagerClientProjectModel.id == row.project_id)
        )
    ).scalar_one_or_none()
    if not proj:
        _clear_billable(row, "USD")
        return

    proj_currency = _norm_ccy(proj.currency, "USD")
    brt = (proj.billable_rate_type or "").strip().lower()
    if brt == "none":
        _zero_billable(row, proj_currency)
        return

    q = select(UserHourlyRateModel).where(
        UserHourlyRateModel.auth_user_id == row.auth_user_id,
        UserHourlyRateModel.rate_kind == "billable",
    )
    rates = list((await session.execute(q)).scalars().all())
    rate_row = pick_rate_for_date(rates, row.work_date)
    if not rate_row:
        _zero_billable(row, proj_currency)
        return

    rate_amount = _to_decimal(rate_row.amount)
    rate_ccy = _norm_ccy(rate_row.currency, "USD")
    fx_date = row.billable_fx_as_of or row.work_date

    try:
        mult, used_date = await cross_rate_to_project_currency(session, rate_ccy, proj_currency, fx_date)
        hourly_proj = (rate_amount * mult).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        billable = round_money(hours * hourly_proj, proj_currency)
        row.billable_amount = billable
        row.billable_currency = proj_currency
        row.rate_source_amount = rate_amount
        row.rate_source_currency = rate_ccy
        row.fx_cross_rate = mult
        row.fx_rate_date = used_date
        row.fx_rate_source = "CBU_RU_UZ"
    except FxUnavailableError as exc:
        _LOG.warning("FX unavailable for entry %s: %s", row.id, exc)
        if settings.fx_soft_fail:
            row.billable_amount = None
            row.billable_currency = proj_currency
            row.rate_source_amount = rate_amount
            row.rate_source_currency = rate_ccy
            row.fx_cross_rate = None
            row.fx_rate_date = None
            row.fx_rate_source = "CBU_UNAVAILABLE"
        else:
            raise FxBillableComputationError(
                f"Не удалось получить курс валют ({rate_ccy} → {proj_currency}) на {fx_date}. "
                f"Проверьте доступность ЦБ РУз или задайте FX_SOFT_FAIL=true."
            ) from exc


def _clear_billable(row: TimeEntryModel, proj_currency: str) -> None:
    row.billable_amount = Decimal(0)
    row.billable_currency = _norm_ccy(proj_currency, "USD")
    row.rate_source_amount = None
    row.rate_source_currency = None
    row.fx_cross_rate = None
    row.fx_rate_date = None
    row.fx_rate_source = None


def _zero_billable(row: TimeEntryModel, proj_currency: str) -> None:
    row.billable_amount = Decimal(0)
    row.billable_currency = _norm_ccy(proj_currency, "USD")
    row.rate_source_amount = None
    row.rate_source_currency = None
    row.fx_cross_rate = None
    row.fx_rate_date = None
    row.fx_rate_source = None


async def _billable_without_project(session: AsyncSession, row: TimeEntryModel, hours: Decimal) -> None:
    """Проект не указан: сумма в валюте ставки, без FX."""
    q = select(UserHourlyRateModel).where(
        UserHourlyRateModel.auth_user_id == row.auth_user_id,
        UserHourlyRateModel.rate_kind == "billable",
    )
    rates = list((await session.execute(q)).scalars().all())
    rate_row = pick_rate_for_date(rates, row.work_date)
    if not rate_row:
        row.billable_amount = Decimal(0)
        row.billable_currency = "USD"
        row.rate_source_amount = None
        row.rate_source_currency = None
        row.fx_cross_rate = None
        row.fx_rate_date = None
        row.fx_rate_source = None
        return
    rate_amount = _to_decimal(rate_row.amount)
    rate_ccy = _norm_ccy(rate_row.currency, "USD")
    row.billable_amount = round_money(hours * rate_amount, rate_ccy)
    row.billable_currency = rate_ccy
    row.rate_source_amount = rate_amount
    row.rate_source_currency = rate_ccy
    row.fx_cross_rate = Decimal(1)
    row.fx_rate_date = row.work_date
    row.fx_rate_source = "NO_PROJECT_NO_FX"


async def backfill_billable_for_all_entries(session: AsyncSession) -> int:
    """Пересчёт billable для записей, где billable_amount IS NULL. Возвращает число обновлённых строк."""
    q = select(TimeEntryModel).where(TimeEntryModel.billable_amount.is_(None))
    rows = list((await session.execute(q)).scalars().all())
    n = 0
    for row in rows:
        try:
            await apply_billable_to_entry(session, row)
            n += 1
        except ValueError as exc:
            _LOG.warning("Backfill skip entry %s: %s", row.id, exc)
        await session.flush()
    return n
