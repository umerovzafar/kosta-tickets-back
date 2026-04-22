"""Удаление мок-данных, созданных seed_mock_data.py (клиенты с префиксом имени, проекты, записи времени, доступ).

Порядок в БД time tracking: счета по мок-клиентам → только сид-записи времени (тот же description, что в seed_mock_data.py)
по мок-проектам → строки user_project_access по мок-проектам → сами клиенты (каскадом проекты, контакты, задачи, категории).

Expenses: удаляются только заявки, у которых одновременно совпадают все маркеры сида: comment, vendor, description
(как в INSERT в seed_mock_data) — без удаления «по project_id».

Переменные окружения: TIME_TRACKING_DATABASE_URL или DATABASE_URL; опционально EXPENSES_DATABASE_URL.
Скрипт сида ранее **заменял** у всех TT-пользователей весь project access только на мок-проекты; этот скрипт
**не восстанавливает** старые назначения — их нужно выставить вручную/другим процессом.

Запуск (из корня репозитория tickets-back):

  set PYTHONPATH=time_tracking
  python time_tracking/scripts/delete_mock_data.py
  python time_tracking/scripts/delete_mock_data.py --apply
  python time_tracking/scripts/delete_mock_data.py --apply --skip-expenses
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# .env из корня репозитория
_ROOT = Path(__file__).resolve().parent.parent.parent
try:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
except Exception:
    pass
if "DATABASE_URL" not in os.environ and os.environ.get("TIME_TRACKING_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TIME_TRACKING_DATABASE_URL"]

_TT = Path(__file__).resolve().parent.parent
if str(_TT) not in sys.path:
    sys.path.insert(0, str(_TT))

from sqlalchemy import and_, delete, func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from infrastructure.database import async_session_factory  # noqa: E402
from infrastructure.models import (  # noqa: E402
    TimeEntryModel,
    TimeManagerClientModel,
    TimeManagerClientProjectModel,
    TimeTrackingUserProjectAccessModel,
)
from infrastructure.models_invoices import InvoiceModel  # noqa: E402

MOCK_PREFIX = "[mock] "

# Как в seed_mock_data: await ter.create(..., description=...)
SEED_TIME_ENTRY_DESCRIPTION = "Мок-запись (seed_mock_data.py)"


def _make_async_pg_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _expense_where_sql() -> str:
    """Те же поля, что в INSERT seed_mock_data._seed_expenses_mocks — все три, чтобы не снести чужие заявки."""
    return (
        "comment = 'seed_mock_data.py' "
        "AND vendor = 'Mock vendor (seed)' "
        "AND description LIKE '[mock] seed_mock_data%'"
    )


async def _delete_time_tracking(*, apply: bool) -> dict:
    like_mock = TimeManagerClientModel.name.like(f"{MOCK_PREFIX}%")

    async with async_session_factory() as session:
        r = await session.execute(select(TimeManagerClientModel.id).where(like_mock))
        mock_cids: list[str] = [row[0] for row in r.all()]
        if not mock_cids:
            if not apply:
                await session.rollback()
            return {
                "mock_clients": 0,
                "mock_projects": 0,
                "time_entries": 0,
                "user_project_access_rows": 0,
                "invoices": 0,
            }

        r2 = await session.execute(
            select(TimeManagerClientProjectModel.id).where(TimeManagerClientProjectModel.client_id.in_(mock_cids))
        )
        mock_pids: list[str] = [row[0] for row in r2.all()]

        n_entries = 0
        n_upa = 0
        if mock_pids:
            entry_where = and_(
                TimeEntryModel.project_id.in_(mock_pids),
                TimeEntryModel.description == SEED_TIME_ENTRY_DESCRIPTION,
            )
            n_entries = int(
                (await session.execute(select(func.count()).select_from(TimeEntryModel).where(entry_where))).scalar_one()
            )
            n_upa = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(TimeTrackingUserProjectAccessModel)
                        .where(TimeTrackingUserProjectAccessModel.project_id.in_(mock_pids))
                    )
                ).scalar_one()
            )
        else:
            entry_where = None

        n_inv = int(
            (
                await session.execute(
                    select(func.count()).select_from(InvoiceModel).where(InvoiceModel.client_id.in_(mock_cids))
                )
            ).scalar_one()
        )

        out: dict = {
            "mock_clients": len(mock_cids),
            "mock_projects": len(mock_pids),
            "time_entries": n_entries,
            "user_project_access_rows": n_upa,
            "invoices": n_inv,
        }

        if not apply:
            await session.rollback()
            return out

        await session.execute(delete(InvoiceModel).where(InvoiceModel.client_id.in_(mock_cids)))
        if mock_pids and entry_where is not None:
            await session.execute(delete(TimeEntryModel).where(entry_where))
            await session.execute(
                delete(TimeTrackingUserProjectAccessModel).where(
                    TimeTrackingUserProjectAccessModel.project_id.in_(mock_pids)
                )
            )
        await session.execute(delete(TimeManagerClientModel).where(TimeManagerClientModel.id.in_(mock_cids)))
        await session.commit()
        return out


async def _expense_count_and_maybe_delete(
    expenses_database_url: str,
    *,
    apply: bool,
) -> int:
    engine = create_async_engine(_make_async_pg_url(expenses_database_url), echo=False, pool_pre_ping=True)
    try:
        w = _expense_where_sql()
        async with engine.begin() as conn:
            c = (await conn.execute(text(f"SELECT COUNT(*)::int FROM expense_requests WHERE {w}"))).scalar_one()
            if not apply or c == 0:
                return int(c)
            r = await conn.execute(text(f"DELETE FROM expense_requests WHERE {w}"))
            n = r.rowcount if r.rowcount is not None and r.rowcount >= 0 else c
            return int(n)
    finally:
        await engine.dispose()


async def _main(*, apply: bool, skip_expenses: bool) -> None:
    if not (os.environ.get("DATABASE_URL") or "").strip():
        print("Задайте TIME_TRACKING_DATABASE_URL или DATABASE_URL в окружении / .env.", file=sys.stderr)
        raise SystemExit(1)

    tt = await _delete_time_tracking(apply=apply)
    ex_url = (os.environ.get("EXPENSES_DATABASE_URL") or "").strip()
    n_ex = 0
    if not skip_expenses and ex_url:
        try:
            n_ex = await _expense_count_and_maybe_delete(ex_url, apply=apply)
        except Exception as e:
            print(f"expenses: ошибка ({e}).", file=sys.stderr)
            n_ex = -1
    elif not skip_expenses and not ex_url and apply:
        print("EXPENSES_DATABASE_URL не задан — мок-расходы в БД expenses пропущены.", file=sys.stderr)

    label = "Удалено" if apply else "Будет удалено (dry-run, без --apply ничего не пишет в БД)"
    print(
        f"{label} (time tracking): клиентов {tt['mock_clients']}, проектов {tt['mock_projects']}, "
        f"счетов {tt['invoices']}, записей времени {tt['time_entries']}, "
        f"строк user_project_access {tt['user_project_access_rows']}"
    )
    if n_ex == -1:
        pass
    else:
        ex_s = f", expense_requests: {n_ex}" if (not skip_expenses and ex_url) else ""
        if ex_s:
            print(f"  {label} (expenses){ex_s}.")

    if not apply and tt["mock_clients"]:
        print("Повторите с --apply для фактического удаления.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--apply",
        action="store_true",
        help="Выполнить DELETE в БД. Без флага только печать подсчётов (dry-run).",
    )
    p.add_argument(
        "--skip-expenses",
        action="store_true",
        help="Не трогать БД expenses даже при EXPENSES_DATABASE_URL",
    )
    args = p.parse_args()
    asyncio.run(_main(apply=bool(args.apply), skip_expenses=bool(args.skip_expenses)))


if __name__ == "__main__":
    main()
