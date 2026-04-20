"""Утилиты конверсии секунд↔часов и округления длительности по настройкам компании.

Источник истины для учёта времени — целое число секунд (`duration_seconds`). Часы (`hours`) выводятся из
секунд с фиксированной точностью 6 знаков (NUMERIC(16,6)), чтобы не было потерь на round-trip.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import ceil

# Соответствует NUMERIC(16,6) у time_tracking_entries.hours / rounded_hours.
_HOURS_QUANT = Decimal("0.000001")
_SECONDS_PER_HOUR = Decimal(3600)


@dataclass(frozen=True)
class RoundingSettings:
    """Настройки округления длительности (одна глобальная запись в БД)."""

    rounding_enabled: bool
    rounding_mode: str  # "up" | "nearest"
    rounding_step_minutes: int

    def validate(self) -> None:
        if self.rounding_mode not in ("up", "nearest"):
            raise ValueError("rounding_mode must be 'up' or 'nearest'")
        if not (1 <= int(self.rounding_step_minutes) <= 60):
            raise ValueError("rounding_step_minutes must be between 1 and 60")


def seconds_from_hours(hours: Decimal | float | int | str) -> int:
    """Часы → целое число секунд (HALF_UP, чтобы не терять секунду на границе)."""
    h = hours if isinstance(hours, Decimal) else Decimal(str(hours))
    seconds = (h * _SECONDS_PER_HOUR).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(seconds)


def hours_from_seconds(seconds: int) -> Decimal:
    """Целое число секунд → часы с точностью NUMERIC(16,6)."""
    h = (Decimal(int(seconds)) / _SECONDS_PER_HOUR).quantize(_HOURS_QUANT, rounding=ROUND_HALF_UP)
    return h


def round_seconds(seconds: int, mode: str, step_minutes: int) -> int:
    """Округление длительности (в секундах) по шагу в минутах и режиму."""
    step_sec = int(step_minutes) * 60
    if step_sec <= 0:
        return int(seconds)
    s = int(seconds)
    if s <= 0:
        return 0
    if mode == "up":
        return int(ceil(s / step_sec)) * step_sec
    # nearest — HALF_UP
    q = (Decimal(s) / Decimal(step_sec)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(q) * step_sec


def compute_rounded_hours(duration_seconds: int, settings: RoundingSettings) -> Decimal:
    """Считает `rounded_hours` для записи согласно настройкам; если округление выключено — возвращает фактические."""
    if not settings.rounding_enabled:
        return hours_from_seconds(duration_seconds)
    rounded_sec = round_seconds(duration_seconds, settings.rounding_mode, settings.rounding_step_minutes)
    return hours_from_seconds(rounded_sec)
