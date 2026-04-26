"""Отчётная неделя: сб..пт (суббота = первый день), сдача/блок в субботу 9:00 в WEEKLY_SUBMIT_TZ.

Автосдача Celery: в субботу 9:00 (Asia/Tashkent) закрывается *предыдущий* полный
блок сб–пт. Текущая сб..пт-неделя до следующей субботы 9:00 **открыта** для
полного редактирования (при отсутствии иного контроля доступа).
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

__all__ = [
    "local_today",
    "saturday_start_of_reporting_week",
    "work_week_start_end_inclusive",
    "previous_closed_saturday_fri_for_anchor",
    "now_in_submit_tz",
    "is_work_week_edit_deadline_passed",
]


def now_in_submit_tz() -> datetime:
    """Текущий момент в часовом поясе сдачи (WEEKLY_SUBMIT_TZ, иначе UTC)."""
    t = (os.environ.get("WEEKLY_SUBMIT_TZ", "UTC") or "UTC").strip() or "UTC"
    if t.upper() in ("UTC", "GMT", "Z"):
        return datetime.now(timezone.utc)
    return datetime.now(ZoneInfo(t))


def local_today(tz_name: str) -> date:
    """Сегодня (календарный день) в указанной зоне."""
    tz = (tz_name or "UTC").strip() or "UTC"
    if tz.upper() in ("UTC", "GMT", "Z"):
        return datetime.now(timezone.utc).date()
    return datetime.now(ZoneInfo(tz)).date()


def saturday_start_of_reporting_week(d: date) -> date:
    """Суббота, с которой начинается 7-дневный отчётный блок (сб..пт), в котором лежит дата d."""
    return d - timedelta(days=(d.weekday() + 2) % 7)


def work_week_start_end_inclusive(d: date) -> tuple[date, date]:
    """Диапазон [сб, пт] — одна отчётная неделя, содержащая день d (по гражданскому дню Tashkent)."""
    s = saturday_start_of_reporting_week(d)
    return s, s + timedelta(days=6)


def work_week_saturday_nine_closing_aware(week_start_saturday: date, *, tz_name: str) -> datetime:
    """Момент, после которого неделя s..(s+6) **закрыта** для правок: (s+7) 09:00 в tz."""
    t = (tz_name or "UTC").strip() or "UTC"
    day = week_start_saturday + timedelta(days=7)
    clock = time(9, 0, 0)
    if t.upper() in ("UTC", "GMT", "Z"):
        return datetime.combine(day, clock, tzinfo=timezone.utc)
    return datetime.combine(day, clock, tzinfo=ZoneInfo(t))


def is_work_week_edit_deadline_passed(
    work_date: date,
    *,
    now: datetime | None = None,
    submit_tz: str | None = None,
) -> bool:
    """
    True, если сейчас не раньше субботы 9:00 по submit_tz, следующей за отчётной неделей work_date
    (граница: после этой субботы 9:00 запись за прошлую сб-пт **недоступна** для правок).
    """
    w0, _w1 = work_week_start_end_inclusive(work_date)
    stz = (submit_tz or os.environ.get("WEEKLY_SUBMIT_TZ", "UTC") or "UTC").strip() or "UTC"
    n = now if now is not None else now_in_submit_tz()
    if n.tzinfo is None:
        raise ValueError("now must be timezone-aware when passed explicitly")
    close_at = work_week_saturday_nine_closing_aware(w0, tz_name=stz)
    return n >= close_at


def previous_closed_saturday_fri_for_anchor(anchor: date) -> tuple[date, date]:
    """Завершившаяся отчётная неделя (сб..пт) для **закрытия** в субботу, которой равен якорь.

    Если якорь — суббота 10-е: закрывается предыдущий ближайший блок, напр. 3–9, а не 10..16.
    """
    s = saturday_start_of_reporting_week(anchor)
    prev = s - timedelta(days=7)
    return prev, prev + timedelta(days=6)


# Обратная совместимость тестов/импортов: старые имена
def monday_of_same_iso_week(d: date) -> date:
    """Устар.: ISO-неделя (пн-вс). Предпочтительны saturday_start / work_week_*."""
    return d - timedelta(days=d.weekday())


def previous_closed_iso_week_range(anchor: date) -> tuple[date, date]:
    """Устр.: Mon-Sun. Используйте previous_closed_saturday_fri_for_anchor."""
    this_mon = monday_of_same_iso_week(anchor)
    prev_mon = this_mon - timedelta(days=7)
    prev_sun = prev_mon + timedelta(days=6)
    return prev_mon, prev_sun
