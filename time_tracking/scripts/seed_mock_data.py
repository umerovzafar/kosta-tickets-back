"""Мок-данные: клиенты, проекты, доступ TT-пользователей, записи времени, почасовые ставки, расходы.

Запуск (из корня репозитория tickets-back, с .env с TIME_TRACKING_DATABASE_URL / DATABASE_URL):

  set PYTHONPATH=time_tracking
  python time_tracking/scripts/seed_mock_data.py

Или из корня приложения (например ``cd /app``): ``python scripts/seed_mock_data.py``

Переменные: TIME_TRACKING_DATABASE_URL (или DATABASE_URL) — БД time tracking; опционально
EXPENSES_DATABASE_URL — БД модуля расходов. Мок-заявки: нативная сумма в валюте проекта →
``amount_uzs`` и ``equivalent_amount`` согласованы с ``expenses.application.expense_service.calc_equivalent``
(``equivalent_amount = amount_uzs / exchange_rate``). Курс UZS за 1 USD: из таблицы
``exchange_rates`` в БД expenses на дату расхода (если есть), иначе ``--uzs-per-usd`` (по умолчанию 12850).
Кросс-курсы EUR/GBP/RUB→USD — как в старом сиде (см. константы ниже).

Почасовые ставки billable/cost: по одной паре на каждую валюту из MOCK_CURRENCIES — только если у
пользователя ещё нет ставки этого типа в этой валюте (повторный запуск не падает и не дублирует).

Повторный запуск добавляет ещё клиентов/проекты/время/расходы; мок-клиенты с префиксом ``[mock] ``.
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
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
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

_EXP_ROOT = _ROOT / "expenses"
if _EXP_ROOT.is_dir() and str(_EXP_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXP_ROOT))
try:
    from application.expense_service import calc_equivalent as _calc_equivalent
except ImportError:  # образ только time_tracking / нет каталога expenses
    def _calc_equivalent(amount_uzs: Decimal, exchange_rate: Decimal) -> Decimal:
        if exchange_rate <= 0:
            raise ValueError("exchange_rate must be positive")
        return (amount_uzs / exchange_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

from sqlalchemy import delete, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

from infrastructure.database import async_session_factory  # noqa: E402
from infrastructure.models import TimeTrackingUserProjectAccessModel  # noqa: E402
from infrastructure.repositories import (  # noqa: E402
    ClientProjectRepository,
    ClientRepository,
    TimeEntryRepository,
    TimeTrackingUserRepository,
)
from infrastructure.repository_rates import HourlyRateRepository  # noqa: E402
from infrastructure.repository_shared import _now_utc  # noqa: E402
MOCK_PREFIX = "[mock] "

# Синхронно с time_tracking.presentation.schemas.ProjectCurrency
MOCK_CURRENCIES: tuple[str, ...] = ("USD", "UZS", "EUR", "RUB", "GBP")

# Как в expenses: exchange_rate = UZS за 1 USD; equivalent_amount = amount_uzs / exchange_rate (USD)
_UZS_PER_USD = Decimal("12850")
_EUR_USD = Decimal("1.08")
_GBP_USD = Decimal("1.27")
# приблизительно: 1 USD = 100 RUB
_RUB_PER_USD = Decimal("100")


def _make_async_pg_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _expense_stored_amounts(
    currency: str, rng: random.Random, *, uzs_per_usd: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """amount_uzs, exchange_rate (UZS за 1 USD), equivalentAmount (USD) = calc_equivalent(amount_uzs, rate)."""
    c = (currency or "USD").upper()
    r = uzs_per_usd
    u: Decimal
    if c == "UZS":
        u = Decimal(rng.randint(150_000, 12_000_000))
    elif c == "USD":
        usd = Decimal(rng.randint(30, 6_000))
        u = (usd * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif c == "EUR":
        eur = Decimal(rng.randint(25, 5_000))
        eq_usd = (eur * _EUR_USD).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        u = (eq_usd * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif c == "GBP":
        gbp = Decimal(rng.randint(20, 4_000))
        eq_usd = (gbp * _GBP_USD).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        u = (eq_usd * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif c == "RUB":
        rub = Decimal(rng.randint(5_000, 500_000))
        eq_usd = (rub / _RUB_PER_USD).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        u = (eq_usd * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        usd = Decimal(rng.randint(30, 6_000))
        u = (usd * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    eq = _calc_equivalent(u, r)
    return u, r, eq


def _norm_rate_currency(c: str | None) -> str:
    return (c or "USD").strip().upper()[:10] or "USD"


def _random_billable_hourly(currency: str, rng: random.Random) -> Decimal:
    """Почасовая ставка (billable) в масштабе, похожем на реальные значения по валюте."""
    c = (currency or "USD").upper()
    if c == "UZS":
        return Decimal(rng.randint(400_000, 9_000_000))
    if c == "RUB":
        return Decimal(rng.randint(3_000, 65_000))
    if c == "EUR":
        return Decimal(rng.randint(70, 420))
    if c == "GBP":
        return Decimal(rng.randint(65, 380))
    return Decimal(rng.randint(75, 480))


async def _seed_hourly_rates_if_missing(session, users: list, rng: random.Random) -> int:
    """По billable + cost в каждой валюте из MOCK_CURRENCIES, если ещё нет ставки в этой валюте."""
    hrr = HourlyRateRepository(session)
    n = 0
    for u in users:
        aid = u.auth_user_id
        existing_b = await hrr.list_by_user_and_kind(aid, "billable")
        have_b = {_norm_rate_currency(r.currency) for r in existing_b}
        for cur in MOCK_CURRENCIES:
            if cur in have_b:
                continue
            amt = _random_billable_hourly(cur, rng)
            await hrr.create(
                auth_user_id=aid,
                rate_kind="billable",
                amount=amt,
                currency=cur,
                valid_from=None,
                valid_to=None,
            )
            n += 1
        existing_c = await hrr.list_by_user_and_kind(aid, "cost")
        have_c = {_norm_rate_currency(r.currency) for r in existing_c}
        bill_rows = await hrr.list_by_user_and_kind(aid, "billable")
        by_cur = {_norm_rate_currency(r.currency): r for r in bill_rows}
        for cur in MOCK_CURRENCIES:
            if cur in have_c:
                continue
            base = by_cur.get(cur)
            if base is not None:
                amt = (base.amount * Decimal(rng.randint(45, 78) / 100)).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
            else:
                amt = (_random_billable_hourly(cur, rng) * Decimal("0.60")).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
            if amt <= 0:
                amt = Decimal("0.0001")
            await hrr.create(
                auth_user_id=aid,
                rate_kind="cost",
                amount=amt,
                currency=cur,
                valid_from=None,
                valid_to=None,
            )
            n += 1
    return n


async def _uzs_per_usd_for_date(session, on_date: date, fallback: Decimal) -> Decimal:
    r = await session.execute(
        text(
            "SELECT rate FROM exchange_rates WHERE rate_date <= :d "
            "ORDER BY rate_date DESC LIMIT 1"
        ),
        {"d": on_date},
    )
    row = r.first()
    if row is not None and row[0] is not None:
        return Decimal(str(row[0]))
    return fallback


async def _alloc_kl_id_expenses(session) -> str:
    await session.execute(
        text(
            "INSERT INTO expense_kl_sequence (singleton, last_seq) VALUES (1, 0) "
            "ON CONFLICT (singleton) DO NOTHING"
        )
    )
    res = await session.execute(
        text("UPDATE expense_kl_sequence SET last_seq = last_seq + 1 WHERE singleton = 1 RETURNING last_seq")
    )
    n = int(res.scalar_one())
    return f"KL{n:06d}"


async def _seed_expenses_mocks(
    expenses_database_url: str,
    project_currency: list[tuple[str, str]],
    auth_user_ids: list[int],
    rng: random.Random,
    d_from: date,
    d_to: date,
    *,
    default_uzs_per_usd: Decimal,
    use_exchange_table: bool,
) -> int:
    if not project_currency or not auth_user_ids:
        return 0
    week_days = list(_iter_weekdays_in_range(d_from, d_to))
    if not week_days:
        return 0
    engine = create_async_engine(_make_async_pg_url(expenses_database_url), echo=False, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    n_ins = 0
    now = datetime.now(timezone.utc)
    try:
        async with factory() as session:
            for pid, cur in project_currency:
                k = rng.randint(1, 3)
                for _ in range(k):
                    ed = rng.choice(week_days)
                    r_uzs = default_uzs_per_usd
                    if use_exchange_table:
                        r_uzs = await _uzs_per_usd_for_date(session, ed, default_uzs_per_usd)
                    amount_u, rate, eq = _expense_stored_amounts(cur, rng, uzs_per_usd=r_uzs)
                    eid = await _alloc_kl_id_expenses(session)
                    uid = rng.choice(auth_user_ids)
                    desc = f"[mock] seed_mock_data, проект {cur}"
                    await session.execute(
                        text(
                            """
                            INSERT INTO expense_requests (
                                id, description, expense_date, payment_deadline,
                                amount_uzs, exchange_rate, equivalent_amount,
                                expense_type, expense_subtype, is_reimbursable, payment_method,
                                department_id, project_id, expense_category_id,
                                vendor, business_purpose, comment, status, current_approver_id,
                                created_by_user_id, updated_by_user_id,
                                created_at, updated_at, submitted_at, approved_at,
                                rejected_at, paid_at, paid_by_user_id, closed_at, withdrawn_at
                            ) VALUES (
                                :id, :description, :expense_date, NULL,
                                :amount_uzs, :exchange_rate, :equivalent_amount,
                                :expense_type, NULL, :is_reimbursable, 'card',
                                NULL, :project_id, NULL,
                                :vendor, NULL, 'seed_mock_data.py', :status, NULL,
                                :created_by, :updated_by,
                                :created_at, :updated_at, :submitted_at, :approved_at,
                                NULL, NULL, NULL, NULL, NULL
                            )
                            """
                        ),
                        {
                            "id": eid,
                            "description": desc,
                            "expense_date": ed,
                            "amount_uzs": float(amount_u),
                            "exchange_rate": float(rate),
                            "equivalent_amount": float(eq),
                            "expense_type": "client_expense",
                            "is_reimbursable": False,
                            "project_id": pid,
                            "vendor": "Mock vendor (seed)",
                            "status": "approved",
                            "created_by": uid,
                            "updated_by": uid,
                            "created_at": now,
                            "updated_at": now,
                            "submitted_at": now,
                            "approved_at": now,
                        },
                    )
                    n_ins += 1
            await session.commit()
    finally:
        await engine.dispose()
    return n_ins


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
    skip_expenses: bool = False,
    default_uzs_per_usd: Decimal = _UZS_PER_USD,
    use_exchange_table: bool = True,
) -> None:
    rng = random.Random(seed)
    n_clients = rng.randint(clients_min, clients_max)
    n_exp_mocks = 0
    n_rate_rows = 0
    users: list = []
    project_ids: list[str] = []
    projects_meta: list[tuple[str, str]] = []
    today = date.today()
    d_from = today

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

        project_ids = []
        projects_meta = []

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
                    projects_meta.append((p.id, proj_cur))
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
                    projects_meta.append((p.id, proj_cur))
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

        n_rate_rows = await _seed_hourly_rates_if_missing(session, users, rng)

        today = date.today()
        d_from = today - timedelta(weeks=weeks_back)
        weekdays = list(_iter_weekdays_in_range(d_from, today))
        if not weekdays:
            print("Нет рабочих дней в диапазоне — пропуск записей времени.", file=sys.stderr)

        # Записи времени: по каждой календарной неделе суммарно не больше weekly_capacity
        if weekdays:
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

    ex_url = (os.environ.get("EXPENSES_DATABASE_URL") or "").strip()
    if not skip_expenses and ex_url and projects_meta and users:
        try:
            n_exp_mocks = await _seed_expenses_mocks(
                ex_url,
                projects_meta,
                [u.auth_user_id for u in users],
                rng,
                d_from,
                today,
                default_uzs_per_usd=default_uzs_per_usd,
                use_exchange_table=use_exchange_table,
            )
        except Exception as e:
            print(f"Мок-расходы (expenses) не записаны: {e}", file=sys.stderr)
    elif not skip_expenses and projects_meta and users and not ex_url:
        print(
            "Мок-расходы пропущены: задайте EXPENSES_DATABASE_URL в .env.",
            file=sys.stderr,
        )

    msg = (
        f"Готово: клиентов {n_clients}, проектов {len(project_ids)}, "
        f"пользователей TT с полным доступом: {len(users)} (время за ~{weeks_back} нед."
    )
    if n_rate_rows:
        msg += f", новых почасовых ставок: {n_rate_rows}"
    if n_exp_mocks:
        msg += f", мок-расходов в БД expenses: {n_exp_mocks}"
    msg += ")."
    print(msg)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=None, help="Seed RNG для воспроизводимости")
    p.add_argument("--clients-min", type=int, default=20, metavar="N")
    p.add_argument("--clients-max", type=int, default=30, metavar="N")
    p.add_argument("--weeks", type=int, default=8, help="Сколько недель назад распределять время")
    p.add_argument(
        "--skip-expenses",
        action="store_true",
        help="Не писать мок-заявки в БД expenses (даже если задана EXPENSES_DATABASE_URL)",
    )
    p.add_argument(
        "--uzs-per-usd",
        type=str,
        default="12850",
        help="Курс UZS за 1 USD, если в exchange_rates (expenses) нет строки на дату расхода",
    )
    p.add_argument(
        "--no-exchange-table",
        action="store_true",
        help="Не читать exchange_rates: для всех мок-расходов только --uzs-per-usd",
    )
    args = p.parse_args()
    if args.clients_min < 1 or args.clients_max < args.clients_min:
        p.error("clients-min/max некорректны")
    uzs = Decimal(str(args.uzs_per_usd).strip().replace(",", "."))
    if uzs <= 0:
        p.error("uzs-per-usd must be positive")
    asyncio.run(
        _seed(
            seed=args.seed,
            clients_min=args.clients_min,
            clients_max=args.clients_max,
            weeks_back=max(1, args.weeks),
            skip_expenses=bool(args.skip_expenses),
            default_uzs_per_usd=uzs,
            use_exchange_table=not bool(args.no_exchange_table),
        )
    )


if __name__ == "__main__":
    main()
