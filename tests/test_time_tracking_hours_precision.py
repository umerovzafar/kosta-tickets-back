"""Точность часов в записях учёта времени (секунды в долях часа)."""

import sys
from decimal import Decimal
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent
_tt = _root / "time_tracking"
if str(_tt) not in sys.path:
    sys.path.insert(0, str(_tt))

from infrastructure.repository_shared import normalize_time_entry_hours  # noqa: E402


def test_ten_seconds_nonzero():
    h = Decimal("10") / Decimal("3600")
    n = normalize_time_entry_hours(h)
    assert n == Decimal("0.002778")
    assert n > 0


def test_subsecond_fraction():
    h = Decimal("1") / Decimal("3600")  # 1 second
    n = normalize_time_entry_hours(h)
    assert n == Decimal("0.000278")


def test_rejects_zero_after_quantize():
    with pytest.raises(ValueError, match="больше нуля"):
        normalize_time_entry_hours(Decimal("0.0000001"))
