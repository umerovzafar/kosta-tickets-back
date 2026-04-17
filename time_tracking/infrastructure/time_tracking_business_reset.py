"""Полное удаление бизнес-данных учёта времени (клиенты, проекты, записи, счета, отчёты).

Таблица ``time_tracking_users`` не трогается — пользователи раздела TT остаются.
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from infrastructure.database import engine

_log = logging.getLogger(__name__)

# Порядок не критичен при CASCADE; перечислены явно для читаемости.
_TRUNCATE_SQL = """
TRUNCATE TABLE
    time_tracking_invoice_audit_logs,
    time_tracking_invoice_payments,
    time_tracking_invoice_line_items,
    time_tracking_invoices,
    time_tracking_invoice_counters,
    tt_report_snapshot_rows,
    tt_report_snapshots,
    tt_report_saved_views,
    time_tracking_entries,
    time_tracking_user_project_access,
    time_tracking_user_hourly_rates,
    time_tracking_client_projects,
    time_tracking_client_tasks,
    time_tracking_client_expense_categories,
    time_tracking_client_contacts,
    time_tracking_clients
RESTART IDENTITY CASCADE;
"""


async def wipe_time_tracking_business_data() -> None:
    async with engine.begin() as conn:
        await conn.execute(text(_TRUNCATE_SQL))
    _log.warning("time_tracking: TRUNCATE бизнес-данных выполнен (пользователи TT сохранены)")
