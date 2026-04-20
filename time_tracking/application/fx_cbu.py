"""Курсы валют ЦБ РУз: база UZS, кросс-курсы через uzs_per_unit."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.config import get_settings

_LOG = logging.getLogger(__name__)

# Валюты проекта / ставок (ISO 4217), согласованы с ProjectCurrency.
SUPPORTED_FX_CCY = frozenset({"USD", "UZS", "EUR", "RUB", "GBP"})


class FxUnavailableError(Exception):
    """Не удалось получить курс для пары валют на дату (и исчерпан fallback)."""


def _parse_cbu_json(payload: Any) -> dict[str, Decimal]:
    """Строки JSON ЦБ → { Ccy: uzs_per_one_unit }."""
    if not isinstance(payload, list):
        raise ValueError("CBU JSON: ожидался массив")
    out: dict[str, Decimal] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        ccy = str(row.get("Ccy", "")).strip().upper()
        if not ccy:
            continue
        try:
            rate_s = str(row.get("Rate", "0")).replace(" ", "").replace(",", ".")
            nom_s = str(row.get("Nominal", "1")).replace(" ", "").replace(",", ".")
            rate = Decimal(rate_s)
            nom = Decimal(nom_s)
            if nom <= 0:
                nom = Decimal(1)
            out[ccy] = (rate / nom).quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)
        except Exception:
            continue
    # UZS: в справочнике может отсутствовать — 1 сум = 1 сум
    if "UZS" not in out:
        out["UZS"] = Decimal(1)
    return out


async def _fetch_cbu_json(url: str, timeout: float) -> Any:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


async def fetch_and_cache_rates_for_date(session: AsyncSession, on_date: date) -> dict[str, Decimal]:
    """Загружает курсы с ЦБ на дату, пишет в кеш, возвращает map Ccy → uzs_per_unit."""
    settings = get_settings()
    base = settings.fx_cbu_base_url.rstrip("/")
    url = f"{base}/ru/arkhiv-kursov-valyut/json/all/{on_date.isoformat()}/"
    payload = await _fetch_cbu_json(url, settings.fx_http_timeout_sec)
    rates = _parse_cbu_json(payload)
    for ccy, uzs_per in rates.items():
        await session.execute(
            text(
                """
                INSERT INTO time_tracking_fx_rate_cache (currency_code, rate_date, source, uzs_per_unit, fetched_at)
                VALUES (:ccy, :rd, 'CBU_RU_UZ', :uzs, now())
                ON CONFLICT (currency_code, rate_date, source) DO UPDATE
                SET uzs_per_unit = EXCLUDED.uzs_per_unit, fetched_at = EXCLUDED.fetched_at
                """
            ),
            {"ccy": ccy, "rd": on_date, "uzs": str(uzs_per)},
        )
    return rates


async def get_uzs_per_unit(
    session: AsyncSession,
    currency: str,
    on_date: date,
    *,
    fallback_days: int | None = None,
) -> Decimal:
    """Сколько UZS за 1 единицу валюты `currency` на дату (с учётом fallback назад)."""
    ccy = (currency or "USD").strip().upper()[:10]
    if ccy not in SUPPORTED_FX_CCY:
        raise FxUnavailableError(f"Неподдерживаемая валюта для FX: {ccy}")
    if ccy == "UZS":
        return Decimal(1)

    settings = get_settings()
    fd = fallback_days if fallback_days is not None else settings.fx_fallback_days

    for back in range(0, fd + 1):
        d = on_date - timedelta(days=back)
        row = (
            await session.execute(
                text(
                    """
                    SELECT uzs_per_unit FROM time_tracking_fx_rate_cache
                    WHERE currency_code = :ccy AND rate_date = :rd AND source = 'CBU_RU_UZ'
                    """
                ),
                {"ccy": ccy, "rd": d},
            )
        ).scalar_one_or_none()
        if row is not None:
            return Decimal(str(row))

        try:
            rates = await fetch_and_cache_rates_for_date(session, d)
            if ccy in rates:
                return rates[ccy]
            _LOG.warning("В ответе ЦБ на %s нет валюты %s", d, ccy)
        except Exception as exc:
            _LOG.warning("CBU fetch failed for %s: %s", d, exc)
            continue

    raise FxUnavailableError(f"Нет курса ЦБ для {ccy} на {on_date} (±{fd} дн.)")


async def cross_rate_to_project_currency(
    session: AsyncSession,
    rate_currency: str,
    project_currency: str,
    fx_date: date,
) -> tuple[Decimal, date]:
    """Множитель: 1 единица валюты ставки выражена в project_currency.

    hourly_in_proj = rate_amount * multiplier
    Возвращает (multiplier, дата ряда ЦБ, с которой реально взяли курс — первый успешный день fallback).
    """
    rc = (rate_currency or "USD").strip().upper()[:10]
    pc = (project_currency or "USD").strip().upper()[:10]
    if rc not in SUPPORTED_FX_CCY or pc not in SUPPORTED_FX_CCY:
        raise FxUnavailableError(f"Неподдерживаемая пара валют: {rc} → {pc}")
    if rc == pc:
        return Decimal(1), fx_date

    uzs_r = await get_uzs_per_unit(session, rc, fx_date)
    uzs_p = await get_uzs_per_unit(session, pc, fx_date)
    if uzs_p <= 0:
        raise FxUnavailableError("Некорректный uzs_per для валюты проекта")
    mult = (uzs_r / uzs_p).quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_UP)
    return mult, fx_date


def round_money(amount: Decimal, currency: str) -> Decimal:
    c = (currency or "USD").strip().upper()
    if c == "UZS":
        return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
