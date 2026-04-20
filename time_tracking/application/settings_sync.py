"""Одноразовая ренормализация записей времени: квантование duration_seconds до целых минут.

Выполняется на старте сервиса одним SQL-UPDATE. После миграции на minute-квант:
  * duration_seconds ВСЕГДА кратно 60 (HALF_UP: 30 секунд → +1 минута),
  * hours = duration_seconds / 3600 (NUMERIC(16,6)),
  * rounded_hours = hours (устаревшее поле сохранено ради совместимости схемы).

UPDATE идемпотентен: фильтр WHERE отсекает уже нормализованные строки.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def renormalize_time_entries_to_minute(session: AsyncSession) -> int:
    """Квантует duration_seconds до целых минут и приводит hours / rounded_hours в согласованное состояние.

    Возвращает количество затронутых строк. Выставленные счета не трогаются (поля в invoice_line_items
    хранятся независимо). Записи, которые уже кратны 60 и имеют согласованные hours/rounded_hours, —
    пропускаются благодаря фильтру в WHERE.
    """
    sql = text(
        """
        WITH src AS (
            SELECT
                id,
                ROUND(duration_seconds::numeric / 60.0)::int * 60 AS q_sec
            FROM time_tracking_entries
        )
        UPDATE time_tracking_entries AS te
        SET
            duration_seconds = src.q_sec,
            hours = ROUND(src.q_sec::numeric / 3600.0, 6),
            rounded_hours = ROUND(src.q_sec::numeric / 3600.0, 6),
            updated_at = now()
        FROM src
        WHERE te.id = src.id
          AND (
              te.duration_seconds IS DISTINCT FROM src.q_sec
              OR te.hours IS DISTINCT FROM ROUND(src.q_sec::numeric / 3600.0, 6)
              OR te.rounded_hours IS DISTINCT FROM ROUND(src.q_sec::numeric / 3600.0, 6)
          )
        """
    )
    result = await session.execute(sql)
    return int(result.rowcount or 0)
