"""Календарные ISO-недели (Пн–Вс) для сдачи учёта: прошлая полная неделя.

Если сдача в **субботу 09:00**, закрывается **предыдущая** Mon–Sun (та, что
закончилась в прошлое воскресенье), а текущая неделя, включая текущую
субботу и воскресенье, **ещё открыта** — учёт в выходные в рамках
«текущей» недели остаётся корректным.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def monday_of_same_iso_week(d: date) -> date:
    """Понедельник календарной ISO-недели, которой принадлежит дата `d` (Mon=0 в Python)."""
    return d - timedelta(days=d.weekday())


def previous_closed_iso_week_range(anchor: date) -> tuple[date, date]:
    """Mon–Sun **завершившейся** недели, строго до «текущей» ISO-недели, к которой относится `anchor`.

    Пример: anchor = суббота 10-я. Текущий понедельник = 6-е → предыдущая
    полная неделя: 30-е (пн) – 5-е (вс) предыдущего месяца, если 6-е = пн
    той же недели что и 10-е. Факт: monday(10) = 6, previous = 29-30 dec? 
    this_mon = monday(10) = Jan 6. previous_mon = Jan 6 - 7d = Dec 30.
    previous_sun = Jan 5. Range Dec 30 – Jan 5.
    """
    this_mon = monday_of_same_iso_week(anchor)
    prev_mon = this_mon - timedelta(days=7)
    prev_sun = prev_mon + timedelta(days=6)
    return prev_mon, prev_sun


def local_today(tz_name: str) -> date:
    """Сегодня в указанной зоне (для расчёта «какая сейчас неделя»)."""
    tz = (tz_name or "UTC").strip() or "UTC"
    if tz.upper() in ("UTC", "GMT"):
        return datetime.now(timezone.utc).date()
    return datetime.now(ZoneInfo(tz)).date()
