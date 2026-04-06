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


async def apply_time_manager_clients_schema_patch(conn: AsyncConnection) -> None:
    """Таблица клиентов time manager — идемпотентно."""
    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS time_tracking_clients (
                id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(500) NOT NULL,
                address TEXT,
                currency VARCHAR(10) NOT NULL DEFAULT 'USD',
                invoice_due_mode VARCHAR(50) NOT NULL DEFAULT 'custom',
                invoice_due_days_after_issue INTEGER,
                tax_percent NUMERIC(8, 4),
                tax2_percent NUMERIC(8, 4),
                discount_percent NUMERIC(8, 4),
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ
            )
            """
        )
    )
    await conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_tt_clients_name ON time_tracking_clients (name)
            """
        )
    )


async def apply_client_tasks_schema_patch(conn: AsyncConnection) -> None:
    """Задачи по клиентам — идемпотентно."""
    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS time_tracking_client_tasks (
                id VARCHAR(36) PRIMARY KEY,
                client_id VARCHAR(36) NOT NULL REFERENCES time_tracking_clients (id) ON DELETE CASCADE,
                name VARCHAR(500) NOT NULL,
                default_billable_rate NUMERIC(18, 4),
                billable_by_default BOOLEAN NOT NULL DEFAULT TRUE,
                common_for_future_projects BOOLEAN NOT NULL DEFAULT FALSE,
                add_to_existing_projects BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ
            )
            """
        )
    )
    await conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_tt_client_tasks_client
                ON time_tracking_client_tasks (client_id)
            """
        )
    )


async def apply_client_expense_categories_schema_patch(conn: AsyncConnection) -> None:
    """Категории расходов по клиентам — идемпотентно (PostgreSQL)."""
    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS time_tracking_client_expense_categories (
                id VARCHAR(36) PRIMARY KEY,
                client_id VARCHAR(36) NOT NULL REFERENCES time_tracking_clients (id) ON DELETE CASCADE,
                name VARCHAR(500) NOT NULL,
                has_unit_price BOOLEAN NOT NULL DEFAULT FALSE,
                is_archived BOOLEAN NOT NULL DEFAULT FALSE,
                sort_order INTEGER,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ
            )
            """
        )
    )
    await conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_tt_client_exp_cat_client
                ON time_tracking_client_expense_categories (client_id)
            """
        )
    )
    await conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_tt_client_exp_cat_active_name
                ON time_tracking_client_expense_categories (client_id, lower(trim(name)))
                WHERE NOT is_archived
            """
        )
    )
