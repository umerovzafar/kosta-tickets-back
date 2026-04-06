"""Дополнение схемы для существующих БД (create_all не добавляет новые колонки в уже созданные таблицы)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def apply_team_workload_schema_patch(conn: AsyncConnection) -> None:
    """Соответствует scripts/add_time_tracking_team_workload.sql — идемпотентно."""
    await conn.execute(
        text(
            """
            ALTER TABLE time_tracking_users
                ADD COLUMN IF NOT EXISTS weekly_capacity_hours NUMERIC(10, 2) NOT NULL DEFAULT 35
            """
        )
    )
    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS time_tracking_entries (
                id VARCHAR(36) PRIMARY KEY,
                auth_user_id INTEGER NOT NULL REFERENCES time_tracking_users (auth_user_id) ON DELETE CASCADE,
                work_date DATE NOT NULL,
                hours NUMERIC(12, 2) NOT NULL,
                is_billable BOOLEAN NOT NULL DEFAULT TRUE,
                project_id VARCHAR(36),
                description TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ
            )
            """
        )
    )
    await conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_tt_entries_user_date
                ON time_tracking_entries (auth_user_id, work_date)
            """
        )
    )
