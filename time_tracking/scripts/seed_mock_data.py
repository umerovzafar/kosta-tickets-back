"""Мок-данные: клиенты, проекты, доступ TT-пользователей, записи времени.

Запуск (из корня репозитория tickets-back, с .env с TIME_TRACKING_DATABASE_URL / DATABASE_URL):

  set PYTHONPATH=time_tracking
  python time_tracking/scripts/seed_mock_data.py

Или из каталога time_tracking:

  set PYTHONPATH=.
  python scripts/seed_mock_data.py

Переменные: TIME_TRACKING_DATABASE_URL в .env (как в docker-compose для сервиса time_tracking).
Повторный запуск добавит ещё одну партию данных (не идемпотентно).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import uuid
from collections import defaultdict
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

# .env из корня репозитория (до импорта database — там читается DATABASE_URL)
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

from sqlalchemy import delete  # noqa: E402

from infrastructure.database import async_session_factory  # noqa: E402
from infrastructure.models import TimeTrackingUserProjectAccessModel  # noqa: E402
from infrastructure.repositories import (  # noqa: E402
    ClientProjectRepository,
    ClientRepository,
    TimeEntryRepository,
    TimeTrackingUserRepository,
)
from infrastructure.repository_shared import _now_utc  # noqa: E402
MOCK_PREFIX = "[mock] "

# Синхронно с time_tracking.presentation.schemas.ProjectCurrency
MOCK_CURRENCIES: tuple[str, ...] = ("USD", "UZS", "EUR", "RUB", "GBP")


def _fixed_fee_amount(currency: str, rng: random.Random) -> Decimal:
    """Сумма «фикса» в масштабе, типичном для валюты (мок-данные)."""
    c = (currency or "USD").upper()
    if c == "UZS":
        return Decimal(rng.randint(80_000_000, 350_000_000))
    if c == "RUB":
        return Decimal(rng.randint(800_000, 8_000_000))
    return Decimal(rng.randint(5_000, 85_000))


def _project_currency(i_client: int, j_proj: int, client_currency: str, rng: random.Random) -> str:
    """Часть проектов в валюте клиента, часть — в другой из списка (см. отчёты/мультивалюта)."""
    if rng.random() < 0.45:
        return client_currency
    return MOCK_CURRENCIES[(i_client * 3 + j_proj) % len(MOCK_CURRENCIES)]


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _iter_weekdays_in_range(d0: date, d1: date) -> Iterator[date]:
    d = d0
    while d <= d1:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def _random_duration_seconds(rng: random.Random) -> int:
    # 0.5 … 8 ч, шаг 30 мин (квант 60 с соблюдён через кратность 30 мин = 1800 с)
    half_hours = rng.randint(1, 16)
    return half_hours * 1800


async def _seed(
    *,
    seed: int | None,
    clients_min: int,
    clients_max: int,
    weeks_back: int,
) -> None:
    rng = random.Random(seed)
    n_clients = rng.randint(clients_min, clients_max)

    async with async_session_factory() as session:
        ur = TimeTrackingUserRepository(session)
        users = [
            u
            for u in await ur.list_users()
            if not u.is_blocked and not u.is_archived
        ]
        if not users:
            print("Нет пользователей в time_tracking_users (не заблокированных). Сначала синхронизируйте список TT.", file=sys.stderr)
            return

        cr = ClientRepository(session)
        cpr = ClientProjectRepository(session)
        ter = TimeEntryRepository(session)

        project_ids: list[str] = []

        for i in range(n_clients):
            client_currency = MOCK_CURRENCIES[i % len(MOCK_CURRENCIES)]
            c = await cr.create(
                name=f"{MOCK_PREFIX}Клиент {i + 1}",
                address=None,
                currency=client_currency,
                invoice_due_mode="net30",
                invoice_due_days_after_issue=30,
                tax_percent=Decimal("0"),
                tax2_percent=None,
                discount_percent=None,
            )
            n_proj = rng.randint(1, 10)
            for j in range(n_proj):
                proj_cur = _project_currency(i, j, client_currency, rng)
                # ~30% проектов — fixed_fee; у клиентов с несколькими проектами первый — фикс чаще
                want_fixed = (n_proj > 1 and j == 0 and (i + j) % 2 == 0) or rng.random() < 0.22
                if want_fixed:
                    p = await cpr.create(
                        client_id=c.id,
                        name=f"Проект {j + 1} — фикс ({c.name.replace(MOCK_PREFIX, '').strip()})",
                        code=f"C{i+1:02d}-P{j+1:02d}",
                        start_date=None,
                        end_date=None,
                        notes="Сгенерировано seed_mock_data (фиксированная ставка)",
                        report_visibility="managers_only",
                        project_type="fixed_fee",
                        currency=proj_cur,
                        fixed_fee_amount=_fixed_fee_amount(proj_cur, rng),
                    )
                else:
                    p = await cpr.create(
                        client_id=c.id,
                        name=f"Проект {j + 1} ({c.name.replace(MOCK_PREFIX, '').strip()})",
                        code=f"C{i+1:02d}-P{j+1:02d}",
                        start_date=None,
                        end_date=None,
                        notes="Сгенерировано seed_mock_data",
                        report_visibility="managers_only",
                        project_type="time_and_materials",
                        currency=proj_cur,
                    )
                project_ids.append(p.id)

        if not project_ids:
            print("Проекты не созданы.", file=sys.stderr)
            return

        # Не вызываем UserProjectAccessRepository.replace_all: там лишний SELECT (get_by_id_global),
        # в части окружений после flush проекты «не видны» — вставляем доступ напрямую, FK к проектам остаётся проверкой.
        await session.flush()
        unique_pids = list(dict.fromkeys(project_ids))
        now_access = _now_utc()
        for u in users:
            await session.execute(
                delete(TimeTrackingUserProjectAccessModel).where(
                    TimeTrackingUserProjectAccessModel.auth_user_id == u.auth_user_id
                )
            )
        for u in users:
            for pid in unique_pids:
                session.add(
                    TimeTrackingUserProjectAccessModel(
                        id=str(uuid.uuid4()),
                        auth_user_id=u.auth_user_id,
                        project_id=pid,
                        granted_by_auth_user_id=None,
                        created_at=now_access,
                    )
                )
        await session.flush()

        today = date.today()
        d_from = today - timedelta(weeks=weeks_back)
        weekdays = list(_iter_weekdays_in_range(d_from, today))
        if not weekdays:
            print("Нет рабочих дней в диапазоне.", file=sys.stderr)
            await session.commit()
            return

        # Записи времени: по каждой календарной неделе суммарно не больше weekly_capacity
        for u in users:
            cap = float(u.weekly_capacity_hours or Decimal("35"))
            by_week: dict[date, float] = defaultdict(float)
            entries_n = rng.randint(25, min(90, len(weekdays) * 2))
            attempts = 0
            while entries_n > 0 and attempts < entries_n * 5:
                attempts += 1
                wd = rng.choice(weekdays)
                wk = _week_start(wd)
                if by_week[wk] >= cap * 0.98:
                    continue
                pid = rng.choice(project_ids)
                sec = _random_duration_seconds(rng)
                h = sec / 3600.0
                if by_week[wk] + h > cap * 0.98:
                    if cap * 0.98 - by_week[wk] < 0.5:
                        continue
                    max_h = cap * 0.98 - by_week[wk]
                    max_units = int(max_h * 2)  # полу hours
                    if max_units < 1:
                        continue
                    half_hours = rng.randint(1, min(16, max_units))
                    sec = half_hours * 1800
                by_week[wk] += sec / 3600.0
                await ter.create(
                    entry_id=str(uuid.uuid4()),
                    auth_user_id=u.auth_user_id,
                    work_date=wd,
                    duration_seconds=sec,
                    is_billable=rng.random() < 0.88,
                    project_id=pid,
                    task_id=None,
                    description="Мок-запись (seed_mock_data.py)",
                )
                entries_n -= 1

        await session.commit()

    print(
        f"Готово: клиентов {n_clients}, проектов {len(project_ids)}, "
        f"пользователей TT с полным доступом: {len(users)} (записи за ~{weeks_back} нед.)."
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=None, help="Seed RNG для воспроизводимости")
    p.add_argument("--clients-min", type=int, default=20, metavar="N")
    p.add_argument("--clients-max", type=int, default=30, metavar="N")
    p.add_argument("--weeks", type=int, default=8, help="Сколько недель назад распределять время")
    args = p.parse_args()
    if args.clients_min < 1 or args.clients_max < args.clients_min:
        p.error("clients-min/max некорректны")
    asyncio.run(
        _seed(
            seed=args.seed,
            clients_min=args.clients_min,
            clients_max=args.clients_max,
            weeks_back=max(1, args.weeks),
        )
    )


if __name__ == "__main__":
    main()
