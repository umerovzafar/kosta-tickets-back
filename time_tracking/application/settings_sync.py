"""Массовый пересчёт `rounded_hours` для всех записей при смене настроек округления.

Выполняется одним SQL-UPDATE на стороне Postgres: исключает Python-цикл по миллионам строк.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from application.time_rounding import RoundingSettings
from infrastructure.repository_settings import TimeTrackingSettingsRepository


def _build_rounded_hours_expression(settings: RoundingSettings) -> str:
    """Собирает SQL-выражение для `rounded_hours` исходя из duration_seconds и настроек округления."""
    if not settings.rounding_enabled:
        return "ROUND((duration_seconds::numeric) / 3600.0, 6)"
    step_sec = int(settings.rounding_step_minutes) * 60
    if settings.rounding_mode == "up":
        # Округление вверх: CEIL(duration_seconds / step_sec) * step_sec / 3600.
        return (
            f"ROUND(("
            f"CEIL((duration_seconds::numeric) / {step_sec}.0) * {step_sec}"
            f") / 3600.0, 6)"
        )
    # nearest
    return (
        f"ROUND(("
        f"ROUND((duration_seconds::numeric) / {step_sec}.0) * {step_sec}"
        f") / 3600.0, 6)"
    )


async def recalc_rounded_hours_for_all_entries(
    session: AsyncSession, settings: RoundingSettings
) -> int:
    """Пересчитать `rounded_hours` у ВСЕХ записей одним UPDATE. Возвращает количество затронутых строк."""
    expr = _build_rounded_hours_expression(settings)
    sql = text(
        f"""
        UPDATE time_tracking_entries
        SET rounded_hours = {expr},
            updated_at = now()
        WHERE rounded_hours IS DISTINCT FROM ({expr})
        """
    )
    result = await session.execute(sql)
    return int(result.rowcount or 0)


async def resync_rounded_hours_for_all_entries(session: AsyncSession) -> int:
    """Одноразовая синхронизация на старте сервиса: читает текущие настройки и пересчитывает отличающиеся строки."""
    settings = await TimeTrackingSettingsRepository(session).get()
    return await recalc_rounded_hours_for_all_entries(session, settings)
