"""Ёмкость и процент загрузки (team_workload_math)."""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
_tt = _root / "time_tracking"
if str(_tt) not in sys.path:
    sys.path.insert(0, str(_tt))

from application.team_workload_math import (  # noqa: E402
    capacity_for_period,
    period_days_inclusive,
    workload_percent,
)


def test_period_days_inclusive() -> None:
    assert period_days_inclusive(date(2024, 1, 1), date(2024, 1, 1)) == 1
    assert period_days_inclusive(date(2024, 1, 1), date(2024, 1, 7)) == 7


def test_period_days_rejects_inverted() -> None:
    with pytest.raises(ValueError, match="раньше"):
        period_days_inclusive(date(2024, 1, 10), date(2024, 1, 1))


def test_capacity_for_period_one_iso_week() -> None:
    c = capacity_for_period(Decimal("35"), date(2024, 1, 1), date(2024, 1, 7))
    assert c == Decimal("35")  # 7/7 * 35


def test_workload_percent_clamped() -> None:
    assert workload_percent(Decimal("10"), Decimal("40")) == 25
    assert workload_percent(Decimal("50"), Decimal("40")) == 100
    assert workload_percent(Decimal("0"), Decimal("0")) == 0
