"""Вычисление данных отчётов: summary (KPI) и table (детализация / агрегат).

Поддерживаемые report_type: time, detailed-time, detailed-expense, contractor, uninvoiced.
Группировки (group): tasks, clients, projects, team.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx
from sqlalchemy import and_, case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from application.hourly_rate_logic import pick_rate_for_date
from infrastructure.config import get_settings
from infrastructure.models import (
    TimeEntryModel,
    TimeManagerClientModel,
    TimeManagerClientProjectModel,
    TimeManagerClientTaskModel,
    TimeTrackingUserModel,
    UserHourlyRateModel,
)

_log = logging.getLogger(__name__)

REPORT_TYPES = frozenset({
    "time", "detailed-time", "detailed-expense", "contractor", "uninvoiced",
})
GROUP_OPTIONS = frozenset({"tasks", "clients", "projects", "team"})

_Q2 = Decimal("0.01")
_Q6 = Decimal("0.000001")
_ZERO = Decimal(0)


def _d(v: Any) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v)) if v else Decimal(0)


def _hours(v: Decimal) -> float:
    return float(v.quantize(_Q6, rounding=ROUND_HALF_UP))


def _money(v: Decimal) -> float:
    return float(v.quantize(_Q2, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Helpers: filters → SQL conditions
# ---------------------------------------------------------------------------


def _base_entry_conditions(
    date_from: date,
    date_to: date,
    user_ids: list[int] | None,
    project_ids: list[str] | None,
    client_ids: list[str] | None,
    include_fixed_fee: bool,
) -> list:
    cond: list = [
        TimeEntryModel.work_date >= date_from,
        TimeEntryModel.work_date <= date_to,
    ]
    if user_ids:
        cond.append(TimeEntryModel.auth_user_id.in_(user_ids))
    if project_ids:
        cond.append(TimeEntryModel.project_id.in_(project_ids))
    if client_ids:
        cond.append(
            TimeEntryModel.project_id.in_(
                select(TimeManagerClientProjectModel.id).where(
                    TimeManagerClientProjectModel.client_id.in_(client_ids)
                )
            )
        )
    if not include_fixed_fee:
        cond.append(
            TimeEntryModel.project_id.notin_(
                select(TimeManagerClientProjectModel.id).where(
                    TimeManagerClientProjectModel.project_type == "fixed_fee"
                )
            )
        )
    return cond


# ---------------------------------------------------------------------------
# Rate resolution for billable amount
# ---------------------------------------------------------------------------


async def _load_user_rates(
    session: AsyncSession, user_ids: list[int] | None
) -> dict[int, list[UserHourlyRateModel]]:
    """Загрузить billable ставки пользователей."""
    q = select(UserHourlyRateModel).where(
        UserHourlyRateModel.rate_kind == "billable"
    )
    if user_ids:
        q = q.where(UserHourlyRateModel.auth_user_id.in_(user_ids))
    rows = (await session.execute(q)).scalars().all()
    out: dict[int, list[UserHourlyRateModel]] = {}
    for r in rows:
        out.setdefault(r.auth_user_id, []).append(r)
    return out


def _billable_amount_for_entry(
    hours: Decimal,
    is_billable: bool,
    work_date: date,
    user_rates: list[UserHourlyRateModel] | None,
) -> tuple[Decimal, str]:
    """Возвращает (amount, currency). Если нет ставки — (0, 'USD')."""
    if not is_billable or not user_rates:
        return Decimal(0), "USD"
    rate = pick_rate_for_date(user_rates, work_date)
    if not rate:
        return Decimal(0), "USD"
    return (hours * _d(rate.amount)).quantize(_Q2, rounding=ROUND_HALF_UP), rate.currency or "USD"


# ---------------------------------------------------------------------------
# Cross-service: expense data
# ---------------------------------------------------------------------------


async def _fetch_expense_report_data(
    date_from: date,
    date_to: date,
    user_ids: list[int] | None = None,
    project_ids: list[str] | None = None,
) -> list[dict]:
    settings = get_settings()
    base = (settings.expenses_service_url or "").rstrip("/")
    if not base:
        return []
    params: dict[str, str] = {
        "dateFrom": date_from.isoformat(),
        "dateTo": date_to.isoformat(),
    }
    if user_ids:
        params["userIds"] = ",".join(str(u) for u in user_ids)
    if project_ids:
        params["projectIds"] = ",".join(project_ids)
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(f"{base}/expenses/report-data", params=params)
        if r.status_code != 200:
            _log.warning("expenses/report-data returned %s", r.status_code)
            return []
        data = r.json()
        return data if isinstance(data, list) else data.get("rows", [])
    except Exception as exc:
        _log.warning("expenses/report-data error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Lookup caches
# ---------------------------------------------------------------------------


async def _load_users_map(session: AsyncSession) -> dict[int, TimeTrackingUserModel]:
    rows = (await session.execute(select(TimeTrackingUserModel))).scalars().all()
    return {u.auth_user_id: u for u in rows}


async def _load_projects_map(session: AsyncSession) -> dict[str, TimeManagerClientProjectModel]:
    rows = (await session.execute(select(TimeManagerClientProjectModel))).scalars().all()
    return {p.id: p for p in rows}


async def _load_clients_map(session: AsyncSession) -> dict[str, TimeManagerClientModel]:
    rows = (await session.execute(select(TimeManagerClientModel))).scalars().all()
    return {c.id: c for c in rows}


async def _load_tasks_map(session: AsyncSession) -> dict[str, TimeManagerClientTaskModel]:
    rows = (await session.execute(select(TimeManagerClientTaskModel))).scalars().all()
    return {t.id: t for t in rows}


# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------


async def build_report_summary(
    session: AsyncSession,
    *,
    report_type: str,
    date_from: date,
    date_to: date,
    user_ids: list[int] | None = None,
    project_ids: list[str] | None = None,
    client_ids: list[str] | None = None,
    include_fixed_fee: bool = True,
) -> dict:
    period = {"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()}

    if report_type == "detailed-expense":
        return await _summary_expense(period, date_from, date_to, user_ids, project_ids)

    cond = _base_entry_conditions(
        date_from, date_to, user_ids, project_ids, client_ids, include_fixed_fee,
    )
    _zero = literal(0)
    bill_hrs = func.coalesce(
        func.sum(case((TimeEntryModel.is_billable.is_(True), TimeEntryModel.hours), else_=_zero)), _zero
    )
    nonbill_hrs = func.coalesce(
        func.sum(case((TimeEntryModel.is_billable.is_(False), TimeEntryModel.hours), else_=_zero)), _zero
    )
    total_hrs = func.coalesce(func.sum(TimeEntryModel.hours), _zero)

    q = select(total_hrs.label("t"), bill_hrs.label("b"), nonbill_hrs.label("nb")).select_from(TimeEntryModel).where(and_(*cond))
    row = (await session.execute(q)).one()
    total, billable, non_billable = _d(row.t), _d(row.b), _d(row.nb)

    rates_map = await _load_user_rates(session, user_ids)
    billable_amount = Decimal(0)
    currency = "USD"

    entries_q = (
        select(
            TimeEntryModel.auth_user_id,
            TimeEntryModel.work_date,
            TimeEntryModel.hours,
            TimeEntryModel.is_billable,
        )
        .where(and_(*cond))
        .where(TimeEntryModel.is_billable.is_(True))
    )
    for e in (await session.execute(entries_q)).all():
        amt, cur = _billable_amount_for_entry(
            _d(e.hours), True, e.work_date, rates_map.get(e.auth_user_id)
        )
        billable_amount += amt
        if cur != "USD":
            currency = cur

    base = {
        "reportType": report_type,
        "period": period,
        "totalHours": _hours(total),
        "billableHours": _hours(billable),
        "nonBillableHours": _hours(non_billable),
        "billableAmount": {"value": _money(billable_amount), "currency": currency},
    }

    if report_type == "time":
        base["unbilledAmount"] = {"value": _money(billable_amount), "currency": currency}
    elif report_type == "detailed-time":
        entry_count_q = select(func.count()).select_from(TimeEntryModel).where(and_(*cond))
        lc = (await session.execute(entry_count_q)).scalar_one()
        base["lineCount"] = int(lc or 0)
    elif report_type == "contractor":
        base["contractorHours"] = _hours(total)
        base["contractorCost"] = {"value": 0, "currency": currency}
    elif report_type == "uninvoiced":
        base["uninvoicedHours"] = _hours(billable)
        base["amountToInvoice"] = {"value": _money(billable_amount), "currency": currency}

    return base


async def _summary_expense(
    period: dict,
    date_from: date,
    date_to: date,
    user_ids: list[int] | None,
    project_ids: list[str] | None,
) -> dict:
    rows = await _fetch_expense_report_data(date_from, date_to, user_ids, project_ids)
    total_uzs = Decimal(0)
    reimbursable = Decimal(0)
    count = 0
    for r in rows:
        amt = _d(r.get("amount_uzs", 0))
        total_uzs += amt
        if r.get("is_reimbursable"):
            reimbursable += amt
        count += 1
    return {
        "reportType": "detailed-expense",
        "period": period,
        "totalExpenseUzs": _money(total_uzs),
        "reimbursableUzs": _money(reimbursable),
        "nonReimbursableUzs": _money(total_uzs - reimbursable),
        "lineCount": count,
    }


# ---------------------------------------------------------------------------
# TABLE
# ---------------------------------------------------------------------------


async def build_report_table(
    session: AsyncSession,
    *,
    report_type: str,
    group: str | None,
    date_from: date,
    date_to: date,
    user_ids: list[int] | None = None,
    project_ids: list[str] | None = None,
    client_ids: list[str] | None = None,
    include_fixed_fee: bool = True,
    sort: str = "date_asc",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    if report_type == "detailed-expense":
        return await _table_expense(
            date_from, date_to, user_ids, project_ids, sort, page, page_size,
        )

    if report_type in ("time", "contractor", "uninvoiced"):
        return await _table_aggregated(
            session,
            report_type=report_type,
            group=group or "projects",
            date_from=date_from,
            date_to=date_to,
            user_ids=user_ids,
            project_ids=project_ids,
            client_ids=client_ids,
            include_fixed_fee=include_fixed_fee,
            sort=sort,
            page=page,
            page_size=page_size,
        )

    # detailed-time
    return await _table_detailed_time(
        session,
        date_from=date_from,
        date_to=date_to,
        user_ids=user_ids,
        project_ids=project_ids,
        client_ids=client_ids,
        include_fixed_fee=include_fixed_fee,
        sort=sort,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# Detailed time table
# ---------------------------------------------------------------------------


async def _table_detailed_time(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    user_ids: list[int] | None,
    project_ids: list[str] | None,
    client_ids: list[str] | None,
    include_fixed_fee: bool,
    sort: str,
    page: int,
    page_size: int,
) -> dict:
    cond = _base_entry_conditions(
        date_from, date_to, user_ids, project_ids, client_ids, include_fixed_fee,
    )
    count_q = select(func.count()).select_from(TimeEntryModel).where(and_(*cond))
    total_count = int((await session.execute(count_q)).scalar_one() or 0)

    q = select(TimeEntryModel).where(and_(*cond))
    if sort == "date_desc":
        q = q.order_by(TimeEntryModel.work_date.desc(), TimeEntryModel.created_at.desc())
    else:
        q = q.order_by(TimeEntryModel.work_date.asc(), TimeEntryModel.created_at.asc())
    q = q.offset((page - 1) * page_size).limit(page_size)

    entries = list((await session.execute(q)).scalars().all())

    users = await _load_users_map(session)
    projects = await _load_projects_map(session)
    tasks = await _load_tasks_map(session)
    rates_map = await _load_user_rates(session, user_ids)

    rows: list[dict] = []
    for e in entries:
        u = users.get(e.auth_user_id)
        p = projects.get(e.project_id) if e.project_id else None
        t = tasks.get(e.task_id) if e.task_id else None
        amt, cur = _billable_amount_for_entry(
            _d(e.hours), e.is_billable, e.work_date, rates_map.get(e.auth_user_id),
        )
        rows.append({
            "rowId": e.id,
            "sourceType": "time_entry",
            "sourceId": e.id,
            "date": e.work_date.isoformat(),
            "userId": e.auth_user_id,
            "userName": (u.display_name or u.email) if u else str(e.auth_user_id),
            "projectId": e.project_id,
            "projectName": p.name if p else None,
            "taskId": e.task_id,
            "taskName": t.name if t else None,
            "description": e.description or "",
            "hours": _hours(_d(e.hours)),
            "isBillable": e.is_billable,
            "billableAmount": _money(amt),
            "currency": cur,
        })

    return {
        "rows": rows,
        "totalCount": total_count,
        "page": page,
        "pageSize": page_size,
        "hasMore": (page * page_size) < total_count,
    }


# ---------------------------------------------------------------------------
# Billable amount aggregation per group key
# ---------------------------------------------------------------------------


async def _compute_group_billable_amounts(
    session: AsyncSession,
    cond: list,
    group: str,
    rates_map: dict[int, list[UserHourlyRateModel]],
    projects: dict[str, TimeManagerClientProjectModel],
) -> dict[Any, tuple[Decimal, str]]:
    """Return {group_key: (total_billable_amount, currency)} by iterating
    over individual billable entries and applying hourly rates."""
    eq = (
        select(
            TimeEntryModel.auth_user_id,
            TimeEntryModel.project_id,
            TimeEntryModel.task_id,
            TimeEntryModel.work_date,
            TimeEntryModel.hours,
        )
        .where(and_(*cond))
        .where(TimeEntryModel.is_billable.is_(True))
    )
    entries = (await session.execute(eq)).all()

    accum: dict[Any, tuple[Decimal, str]] = {}
    for e in entries:
        if group == "team":
            gid = e.auth_user_id
        elif group == "projects":
            gid = e.project_id
        elif group == "clients":
            p = projects.get(e.project_id) if e.project_id else None
            gid = p.client_id if p else None
        else:  # tasks
            gid = e.task_id

        amt, cur = _billable_amount_for_entry(
            _d(e.hours), True, e.work_date, rates_map.get(e.auth_user_id),
        )
        prev_amt, prev_cur = accum.get(gid, (_ZERO, "USD"))
        accum[gid] = (prev_amt + amt, cur if cur != "USD" else prev_cur)

    return accum


# ---------------------------------------------------------------------------
# Aggregated table (time / contractor / uninvoiced)
# ---------------------------------------------------------------------------


async def _table_aggregated(
    session: AsyncSession,
    *,
    report_type: str,
    group: str,
    date_from: date,
    date_to: date,
    user_ids: list[int] | None,
    project_ids: list[str] | None,
    client_ids: list[str] | None,
    include_fixed_fee: bool,
    sort: str,
    page: int,
    page_size: int,
) -> dict:
    cond = _base_entry_conditions(
        date_from, date_to, user_ids, project_ids, client_ids, include_fixed_fee,
    )

    if report_type == "uninvoiced":
        cond.append(TimeEntryModel.is_billable.is_(True))

    _zero = literal(0)
    bill_hrs = func.coalesce(
        func.sum(case((TimeEntryModel.is_billable.is_(True), TimeEntryModel.hours), else_=_zero)), _zero
    ).label("billable_hours")
    total_hrs = func.coalesce(func.sum(TimeEntryModel.hours), _zero).label("total_hours")

    if group == "team":
        group_col = TimeEntryModel.auth_user_id
        q = select(group_col.label("gid"), total_hrs, bill_hrs).where(and_(*cond)).group_by(group_col)
    elif group == "projects":
        group_col = TimeEntryModel.project_id
        q = select(group_col.label("gid"), total_hrs, bill_hrs).where(and_(*cond)).group_by(group_col)
    elif group == "clients":
        q = (
            select(
                TimeManagerClientProjectModel.client_id.label("gid"),
                total_hrs,
                bill_hrs,
            )
            .select_from(TimeEntryModel)
            .outerjoin(
                TimeManagerClientProjectModel,
                TimeManagerClientProjectModel.id == TimeEntryModel.project_id,
            )
            .where(and_(*cond))
            .group_by(TimeManagerClientProjectModel.client_id)
        )
    else:  # tasks
        q = (
            select(
                TimeEntryModel.task_id.label("gid"),
                total_hrs,
                bill_hrs,
            )
            .where(and_(*cond))
            .group_by(TimeEntryModel.task_id)
        )

    if sort == "hours_asc":
        q = q.order_by(total_hrs.asc())
    else:
        q = q.order_by(total_hrs.desc())

    all_rows = (await session.execute(q)).all()
    total_count = len(all_rows)
    page_rows = all_rows[(page - 1) * page_size: page * page_size]

    users = await _load_users_map(session)
    projects = await _load_projects_map(session)
    clients = await _load_clients_map(session)
    tasks = await _load_tasks_map(session)
    rates_map = await _load_user_rates(session, user_ids)

    billable_amounts = await _compute_group_billable_amounts(
        session, cond, group, rates_map, projects,
    )

    rows: list[dict] = []
    for r in page_rows:
        gid = r.gid
        total_h = _d(r.total_hours)
        bill_h = _d(r.billable_hours)
        amt_info = billable_amounts.get(gid, (_ZERO, "USD"))
        row: dict[str, Any] = {
            "hours": _hours(total_h),
            "billableHours": _hours(bill_h),
            "nonBillableHours": _hours(total_h - bill_h),
            "billableAmount": _money(amt_info[0]),
            "currency": amt_info[1],
            "invoicedAmount": 0,
        }
        if group == "team":
            u = users.get(gid) if gid else None
            row["userId"] = gid
            row["name"] = (u.display_name or u.email) if u else str(gid or "N/A")
        elif group == "projects":
            p = projects.get(gid) if gid else None
            row["projectId"] = gid
            row["name"] = p.name if p else "Без проекта"
            row["code"] = p.code if p else None
            if p and p.client_id:
                c = clients.get(p.client_id)
                row["clientId"] = p.client_id
                row["clientName"] = c.name if c else None
        elif group == "clients":
            c = clients.get(gid) if gid else None
            row["clientId"] = gid
            row["name"] = c.name if c else "Без клиента"
        else:  # tasks
            t = tasks.get(gid) if gid else None
            row["taskId"] = gid
            row["name"] = t.name if t else "Без задачи"
        rows.append(row)

    return {
        "rows": rows,
        "totalCount": total_count,
        "page": page,
        "pageSize": page_size,
        "hasMore": (page * page_size) < total_count,
    }


# ---------------------------------------------------------------------------
# Detailed expense table
# ---------------------------------------------------------------------------


async def _table_expense(
    date_from: date,
    date_to: date,
    user_ids: list[int] | None,
    project_ids: list[str] | None,
    sort: str,
    page: int,
    page_size: int,
) -> dict:
    all_rows = await _fetch_expense_report_data(date_from, date_to, user_ids, project_ids)

    reverse = sort.endswith("_desc")
    all_rows.sort(key=lambda r: r.get("expense_date", ""), reverse=reverse)

    total_count = len(all_rows)
    start = (page - 1) * page_size
    page_rows = all_rows[start: start + page_size]

    rows: list[dict] = []
    for r in page_rows:
        rows.append({
            "rowId": r.get("id", ""),
            "sourceType": "expense",
            "sourceId": r.get("id", ""),
            "date": r.get("expense_date", ""),
            "projectId": r.get("project_id"),
            "expenseCategoryId": r.get("expense_category_id"),
            "expenseType": r.get("expense_type", ""),
            "description": r.get("description", ""),
            "amountUzs": _money(_d(r.get("amount_uzs", 0))),
            "exchangeRate": float(r.get("exchange_rate", 0)),
            "equivalentAmount": _money(_d(r.get("equivalent_amount", 0))),
            "status": r.get("status", ""),
            "authorUserId": r.get("created_by_user_id"),
            "isReimbursable": r.get("is_reimbursable", False),
        })

    return {
        "rows": rows,
        "totalCount": total_count,
        "page": page,
        "pageSize": page_size,
        "hasMore": (page * page_size) < total_count,
    }


# ---------------------------------------------------------------------------
# Flatten table rows for snapshot / export
# ---------------------------------------------------------------------------


async def build_table_rows_flat(
    session: AsyncSession, **kwargs
) -> list[dict]:
    """Получить все строки таблицы (без пагинации) для создания снимка."""
    kwargs["page"] = 1
    kwargs["page_size"] = 100_000
    result = await build_report_table(session, **kwargs)
    return result.get("rows", [])
