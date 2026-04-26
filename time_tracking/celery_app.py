"""Celery — автоотправка недельного отчёта (блокировка дат).

Отчётная неделя: **сб..пт**; граница в WEEKLY_SUBMIT_TZ: **суббота 9:00** (после неё
прошлую сб-пт-неделю нельзя править; до этого открыт полный ввод/редактирование).

Переменные окружения (пример):
  REDIS_URL=redis://redis:6379/0
  WEEKLY_SUBMIT_TZ=Asia/Tashkent
  WEEKLY_SUBMIT_HOUR=9
  WEEKLY_SUBMIT_MINUTE=0
  WEEKLY_SUBMIT_DOW=6        # 0=вс … 6=сб (crontab Celery; см. их док)
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

REDIS = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
app = Celery(
    "time_tracking",
    broker=REDIS,
    backend=REDIS,
    include=["celery_tasks.weekly_report"],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=os.environ.get("WEEKLY_SUBMIT_TZ", "UTC"),
    enable_utc=True,
)

H = int(os.environ.get("WEEKLY_SUBMIT_HOUR", "6"))
M = int(os.environ.get("WEEKLY_SUBMIT_MINUTE", "0"))
# По умолчанию суббота (6), как в docker-compose; понедельник = 1 (см. crontab Celery: 0=вс … 6=сб)
_dow = os.environ.get("WEEKLY_SUBMIT_DOW", "6")
try:
    DOW: int | str = int(_dow)
except ValueError:
    DOW = _dow

app.conf.beat_schedule = {
    "weekly-time-submit": {
        "task": "tt.weekly.submit_last_closed_iso_weeks",
        "schedule": crontab(hour=H, minute=M, day_of_week=DOW),
    },
}
