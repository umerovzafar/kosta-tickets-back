"""Утилиты конверсии длительности: секунды ↔ часы, квантование до целых минут.

Логика учёта времени:
  * пользователь вводит длительность (таймер/ручной ввод) в произвольных секундах,
  * на входе мы приводим длительность к **целым минутам** (HALF_UP: 30 секунд → +1 минута),
  * дальше `duration_seconds` ВСЕГДА кратно 60, `hours = duration_seconds / 3600`.

Никакого округления до 15/6/30-минутного шага больше нет.
`rounded_hours` в модели сохраняется для обратной совместимости и всегда равен `hours`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# Соответствует NUMERIC(16,6) у time_tracking_entries.hours / rounded_hours.
_HOURS_QUANT = Decimal("0.000001")
_SECONDS_PER_HOUR = Decimal(3600)


def seconds_from_hours(hours: Decimal | float | int | str) -> int:
    """Часы → целое число секунд (HALF_UP, чтобы не терять секунду на границе)."""
    h = hours if isinstance(hours, Decimal) else Decimal(str(hours))
    seconds = (h * _SECONDS_PER_HOUR).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(seconds)


def hours_from_seconds(seconds: int) -> Decimal:
    """Целое число секунд → часы с точностью NUMERIC(16,6)."""
    h = (Decimal(int(seconds)) / _SECONDS_PER_HOUR).quantize(_HOURS_QUANT, rounding=ROUND_HALF_UP)
    return h


def quantize_seconds_to_minute(seconds: int) -> int:
    """Округляет произвольные секунды до целых минут по мат. принципу (HALF_UP: 30с → +1мин).

    Примеры:
      0    → 0
      29   → 0
      30   → 60
      59   → 60
      90   → 120 (1.5 мин → 2 мин)
      4053 → 4080 (67.55 мин → 68 мин)
    """
    s = int(seconds)
    if s <= 0:
        return 0
    minutes = (Decimal(s) / Decimal(60)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(minutes) * 60
