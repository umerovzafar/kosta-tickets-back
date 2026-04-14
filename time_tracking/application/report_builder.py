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
from sqlalchemy import and_, exists, func, select
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
from infrastructure.models_invoices import InvoiceLineItemModel, InvoiceModel

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
    *,
    exclude_invoiced_time: bool = False,
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
    if exclude_invoiced_time:
        inv_exists = exists(
            select(1)
            .select_from(InvoiceLineItemModel)
            .join(InvoiceModel, InvoiceModel.id == InvoiceLineItemModel.invoice_id)
            .where(
                InvoiceLineItemModel.time_entry_id == TimeEntryModel.id,
                InvoiceModel.status != "canceled",
            )
        )
        cond.append(~inv_exists)
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


async def _load_user_cost_rates(
    session: AsyncSession, user_ids: list[int] | None
) -> dict[int, list[UserHourlyRateModel]]:
    """Ставки себестоимости (cost) по пользователям."""
    q = select(UserHourlyRateModel).where(UserHourlyRateModel.rate_kind == "cost")
    if user_ids:
        q = q.where(UserHourlyRateModel.auth_user_id.in_(user_ids))
    rows = (await session.execute(q)).scalars().all()
    out: dict[int, list[UserHourlyRateModel]] = {}
    for r in rows:
        out.setdefault(r.auth_user_id, []).append(r)
    return out


def _split_employee_name(display_name: str | None, email: str | None) -> tuple[str, str]:
    """Имя и фамилия для отчёта: из display_name (первый токен — имя, остаток — фамилия)."""
    raw = (display_name or "").strip()
    if not raw:
        raw = (email or "").strip()
        if "@" in raw:
            raw = raw.split("@", 1)[0].replace(".", " ").replace("_", " ").strip()
    if not raw:
        return "", ""
    parts = raw.split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1].strip()


def _billable_rate_for_entry(
    work_date: date,
    user_rates: list[UserHourlyRateModel] | None,
) -> tuple[Decimal | None, str]:
    """Ставка за час (billable), действующая на дату; без ставки — (None, USD)."""
    if not user_rates:
        return None, "USD"
    rate = pick_rate_for_date(user_rates, work_date)
    if not rate:
        return None, "USD"
    return _d(rate.amount), (rate.currency or "USD").strip()[:10] or "USD"


def _cost_amount_for_entry(
    hours: Decimal,
    work_date: date,
    user_cost_rates: list[UserHourlyRateModel] | None,
) -> tuple[Decimal, Decimal | None, str]:
    """(cost_amount, cost_rate_per_hour, currency)."""
    if not user_cost_rates:
        return Decimal(0), None, "USD"
    rate = pick_rate_for_date(user_cost_rates, work_date)
    if not rate:
        return Decimal(0), None, "USD"
    r_amt = _d(rate.amount)
    amt = (hours * r_amt).quantize(_Q2, rounding=ROUND_HALF_UP)
    return amt, r_amt, (rate.currency or "USD").strip()[:10] or "USD"


async def _invoice_info_for_time_entries(
    session: AsyncSession, entry_ids: list[str],
) -> dict[str, tuple[str, str]]:
    """time_entry_id -> (invoice_uuid, invoice_number) для неотменённых счетов."""
    if not entry_ids:
        return {}
    q = (
        select(
            InvoiceLineItemModel.time_entry_id,
            InvoiceModel.id,
            InvoiceModel.invoice_number,
        )
        .select_from(InvoiceLineItemModel)
        .join(InvoiceModel, InvoiceModel.id == InvoiceLineItemModel.invoice_id)
        .where(
            InvoiceLineItemModel.time_entry_id.in_(entry_ids),
            InvoiceLineItemModel.time_entry_id.is_not(None),
            InvoiceModel.status != "canceled",
        )
    )
    rows = (await session.execute(q)).all()
    out: dict[str, tuple[str, str]] = {}
    for tid, iid, num in rows:
        if not tid:
            continue
        k = str(tid)
        if k not in out:
            out[k] = (str(iid), str(num))
    return out


# Колонки детального отчёта по времени (клиентский экспорт / сверка с Harvest-подобными полями).
DETAILED_TIME_REPORT_COLUMNS: tuple[str, ...] = (
    "Date",
    "Client",
    "Project",
    "Project Code",
    "Task",
    "Notes",
    "Hours",
    "Billable?",
    "Invoiced?",
    "Approved?",
    "First Name",
    "Last Name",
    "Employee Id",
    "Roles",
    "Employee?",
    "Billable Rate",
    "Billable Amount",
    "Cost Rate",
    "Cost Amount",
    "Currency",
    "External Reference URL",
    "Invoice ID",
)


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
        date_from,
        date_to,
        user_ids,
        project_ids,
        client_ids,
        include_fixed_fee,
        exclude_invoiced_time=(report_type == "uninvoiced"),
    )

    entries_q = select(
        TimeEntryModel.auth_user_id,
        TimeEntryModel.work_date,
        TimeEntryModel.hours,
        TimeEntryModel.is_billable,
    ).where(and_(*cond))
    entries = (await session.execute(entries_q)).all()

    rates_map = await _load_user_rates(session, user_ids)

    total = _ZERO
    billable = _ZERO
    non_billable = _ZERO
    billable_amount = _ZERO
    currency = "USD"
    line_count = 0

    for e in entries:
        h = _d(e.hours)
        total += h
        line_count += 1
        if e.is_billable:
            billable += h
            amt, cur = _billable_amount_for_entry(
                h, True, e.work_date, rates_map.get(e.auth_user_id),
            )
            billable_amount += amt
            if cur != "USD":
                currency = cur
        else:
            non_billable += h

    base: dict[str, Any] = {
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
        base["lineCount"] = line_count
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
    """
    Детальные строки времени для отчёта (в т.ч. по выбранному клиенту через clientIds / projectIds).

    Логика колонок (модель как в Harvest-подобных выгрузках):
    - Client / Project / Project Code / Task — из справочников проекта и клиента.
    - Billable? / Billable Rate / Billable Amount / Currency — по флагу billable и ставкам rate_kind=billable.
    - Cost Rate / Cost Amount — по ставкам rate_kind=cost (на все часы строки).
    - Invoiced? / Invoice ID — связь со строкой счёта (счёт не в статусе canceled).
    - Approved? — отдельного согласования времени в ТТ нет; в колонке выводится «N/A» (зарезервировано под будущий статус).
    - Roles — роль пользователя в модуле time_tracking (user/manager/…), не корпоративные роли auth.
    - Employee? — «Yes», если пользователь не в архиве в справочнике TT.
    - External Reference URL — пока не хранится; пусто.
    - First Name / Last Name — разбор display_name (первое слово / остаток), иначе локальная часть email.
    """
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
    clients = await _load_clients_map(session)
    tasks = await _load_tasks_map(session)
    page_uids = sorted({e.auth_user_id for e in entries})
    rates_map = await _load_user_rates(session, page_uids or None)
    cost_rates_map = await _load_user_cost_rates(session, page_uids or None)
    inv_map = await _invoice_info_for_time_entries(session, [e.id for e in entries])

    rows: list[dict] = []
    for e in entries:
        u = users.get(e.auth_user_id)
        p = projects.get(e.project_id) if e.project_id else None
        c = clients.get(p.client_id) if p else None
        t = tasks.get(e.task_id) if e.task_id else None
        hrs = _d(e.hours)
        bill_amt, bill_cur = _billable_amount_for_entry(
            hrs, e.is_billable, e.work_date, rates_map.get(e.auth_user_id),
        )
        bill_rate, bill_rate_cur = _billable_rate_for_entry(
            e.work_date, rates_map.get(e.auth_user_id),
        )
        cost_amt, cost_rate, cost_cur = _cost_amount_for_entry(
            hrs, e.work_date, cost_rates_map.get(e.auth_user_id),
        )
        inv_t = inv_map.get(e.id)
        invoiced = inv_t is not None
        inv_display = inv_t[1] if inv_t else ""

        fn, ln = _split_employee_name(
            u.display_name if u else None,
            u.email if u else None,
        )
        cur_out = bill_cur if e.is_billable else (cost_cur or bill_cur or "USD")

        row: dict[str, Any] = {
            "Date": e.work_date.isoformat(),
            "Client": c.name if c else "",
            "Project": p.name if p else "",
            "Project Code": (p.code or "") if p else "",
            "Task": t.name if t else "",
            "Notes": (e.description or "").strip(),
            "Hours": _hours(hrs),
            "Billable?": "Yes" if e.is_billable else "No",
            "Invoiced?": "Yes" if invoiced else "No",
            "Approved?": "N/A",
            "First Name": fn,
            "Last Name": ln,
            "Employee Id": str(e.auth_user_id),
            "Roles": (u.role or "").strip() if u else "",
            "Employee?": "Yes" if (u and not u.is_archived) else "No",
            "Billable Rate": _money(bill_rate) if bill_rate is not None else "",
            "Billable Amount": _money(bill_amt) if e.is_billable else 0.0,
            "Cost Rate": _money(cost_rate) if cost_rate is not None else "",
            "Cost Amount": _money(cost_amt),
            "Currency": cur_out,
            "External Reference URL": "",
            "Invoice ID": inv_display,
            # Технические поля для снимков и старых интеграций
            "rowId": e.id,
            "sourceType": "time_entry",
            "sourceId": e.id,
            # Дубли в camelCase для API, ожидающего прежние имена
            "date": e.work_date.isoformat(),
            "userId": e.auth_user_id,
            "userName": (u.display_name or u.email) if u else str(e.auth_user_id),
            "projectId": e.project_id,
            "projectName": p.name if p else None,
            "taskId": e.task_id,
            "taskName": t.name if t else None,
            "description": e.description or "",
            "isBillable": e.is_billable,
            "billableAmount": _money(bill_amt),
            "currency": cur_out,
            "clientName": c.name if c else None,
            "invoiced": invoiced,
            "invoiceNumber": inv_display or None,
            "invoiceUuid": inv_t[0] if inv_t else None,
        }
        rows.append(row)

    return {
        "rows": rows,
        "totalCount": total_count,
        "page": page,
        "pageSize": page_size,
        "hasMore": (page * page_size) < total_count,
    }


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
        date_from,
        date_to,
        user_ids,
        project_ids,
        client_ids,
        include_fixed_fee,
        exclude_invoiced_time=(report_type == "uninvoiced"),
    )

    if report_type == "uninvoiced":
        cond.append(TimeEntryModel.is_billable.is_(True))

    entries_q = select(
        TimeEntryModel.auth_user_id,
        TimeEntryModel.project_id,
        TimeEntryModel.task_id,
        TimeEntryModel.work_date,
        TimeEntryModel.hours,
        TimeEntryModel.is_billable,
    ).where(and_(*cond))
    entries = (await session.execute(entries_q)).all()

    users_map = await _load_users_map(session)
    projects_map = await _load_projects_map(session)
    clients_map = await _load_clients_map(session)
    tasks_map = await _load_tasks_map(session)
    rates_map = await _load_user_rates(session, user_ids)

    buckets: dict[Any, dict] = {}
    for e in entries:
        if group == "team":
            gid = e.auth_user_id
        elif group == "projects":
            gid = e.project_id
        elif group == "clients":
            p = projects_map.get(e.project_id) if e.project_id else None
            gid = p.client_id if p else None
        else:
            gid = e.task_id

        bkt = buckets.get(gid)
        if bkt is None:
            bkt = {"total": _ZERO, "billable": _ZERO, "amount": _ZERO, "currency": "USD"}
            buckets[gid] = bkt

        h = _d(e.hours)
        bkt["total"] += h
        if e.is_billable:
            bkt["billable"] += h
            amt, cur = _billable_amount_for_entry(
                h, True, e.work_date, rates_map.get(e.auth_user_id),
            )
            bkt["amount"] += amt
            if cur != "USD":
                bkt["currency"] = cur

    sorted_keys = sorted(
        buckets.keys(),
        key=lambda k: float(buckets[k]["total"]),
        reverse=(sort != "hours_asc"),
    )

    total_count = len(sorted_keys)
    page_keys = sorted_keys[(page - 1) * page_size: page * page_size]

    rows: list[dict] = []
    for gid in page_keys:
        bkt = buckets[gid]
        total_h = bkt["total"]
        bill_h = bkt["billable"]
        row: dict[str, Any] = {
            "hours": _hours(total_h),
            "billableHours": _hours(bill_h),
            "nonBillableHours": _hours(total_h - bill_h),
            "billableAmount": _money(bkt["amount"]),
            "currency": bkt["currency"],
            "invoicedAmount": 0,
        }
        if group == "team":
            u = users_map.get(gid) if gid else None
            row["userId"] = gid
            row["name"] = (u.display_name or u.email) if u else str(gid or "N/A")
        elif group == "projects":
            p = projects_map.get(gid) if gid else None
            row["projectId"] = gid
            row["name"] = p.name if p else "Без проекта"
            row["code"] = p.code if p else None
            if p and p.client_id:
                c = clients_map.get(p.client_id)
                row["clientId"] = p.client_id
                row["clientName"] = c.name if c else None
        elif group == "clients":
            c = clients_map.get(gid) if gid else None
            row["clientId"] = gid
            row["name"] = c.name if c else "Без клиента"
        else:
            t = tasks_map.get(gid) if gid else None
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
