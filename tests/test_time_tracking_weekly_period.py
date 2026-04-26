"""ISO-неделя для автосдачи (weekly_period)."""

from datetime import date

import pytest

from service_path import ensure_service_in_path

ensure_service_in_path("time_tracking")

from application.weekly_period import ( 
    monday_of_same_iso_week,
    previous_closed_iso_week_range,
)


def test_monday_of_iso_week_wednesday_jan_2024() -> None:
    assert monday_of_same_iso_week(date(2024, 1, 10)) == date(2024, 1, 8)


def test_previous_closed_iso_week() -> None:
    d0, d1 = previous_closed_iso_week_range(date(2024, 1, 10))
    assert d0 == date(2024, 1, 1)
    assert d1 == date(2024, 1, 7)
