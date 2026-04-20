"""Детальный подетальный экспорт по времени — одна строка = одна запись времени.

Колонки:
    Date | Recorded At | Client | Project | Project Code | Task | Notes | Hours | Billable? |
    Invoiced? | Approved? | First Name | Last Name | Employee Id | Roles | Employee? |
    Billable Rate | Billable Amount | Cost Rate | Cost Amount | Currency |
    External Reference URL | Invoice ID
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from application.report_builder import (
    _base_entry_conditions,
    billable_amount_from_entry,
    _billable_rate_for_entry,
    _cost_amount_for_entry,
    _invoice_info_for_time_entries,
    _load_clients_map,
    _load_projects_map,
    _load_tasks_map,
    _load_user_cost_rates,
    _load_user_rates,
    _load_users_map,
    _split_employee_name,
)
from application.services.reports._base import _d, _hours, _money, build_response
from infrastructure.models import TimeEntryModel


async def get_detailed_time_rows(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    client_ids: list[str] | None = None,
    project_ids: list[str] | None = None,
    user_ids: list[int] | None = None,
    task_ids: list[str] | None = None,
    is_billable: bool | None = None,
    include_fixed_fee: bool = True,
) -> list[dict[str, Any]]:
    """Вернуть плоские строки детального отчёта по времени (для экспорта и JSON-ответа).

    Порядок строк всегда хронологический: work_date по возрастанию, затем created_at, затем id.
    """
    cond = _base_entry_conditions(
        date_from, date_to, user_ids, project_ids, client_ids, include_fixed_fee,
    )
    if is_billable is not None:
        cond.append(TimeEntryModel.is_billable.is_(is_billable))
    if task_ids:
        cond.append(TimeEntryModel.task_id.in_(task_ids))

    q = (
        select(TimeEntryModel)
        .where(and_(*cond))
        .order_by(
            TimeEntryModel.work_date.asc(),
            TimeEntryModel.created_at.asc(),
            TimeEntryModel.id.asc(),
        )
    )

    entries = list((await session.execute(q)).scalars().all())

    users_map = await _load_users_map(session)
    projects_map = await _load_projects_map(session)
    clients_map = await _load_clients_map(session)
    tasks_map = await _load_tasks_map(session)

    uids = sorted({e.auth_user_id for e in entries})
    rates_map = await _load_user_rates(session, uids or None)
    cost_rates_map = await _load_user_cost_rates(session, uids or None)
    inv_map = await _invoice_info_for_time_entries(session, [e.id for e in entries])

    rows: list[dict[str, Any]] = []
    for e in entries:
        u = users_map.get(e.auth_user_id)
        p = projects_map.get(e.project_id) if e.project_id else None
        c = clients_map.get(p.client_id) if p else None
        t = tasks_map.get(e.task_id) if e.task_id else None

        hrs = _d(e.hours)
        bill_amt, bill_cur = billable_amount_from_entry(
            e, hrs, e.work_date, rates_map.get(e.auth_user_id),
        )
        bill_rate, bill_rate_cur = _billable_rate_for_entry(
            e.work_date, rates_map.get(e.auth_user_id),
        )
        cost_amt, cost_rate, cost_cur = _cost_amount_for_entry(
            hrs, e.work_date, cost_rates_map.get(e.auth_user_id),
        )
        inv_t = inv_map.get(e.id)

        # Приоритет валюты: проект → ставка биллинга → ставка себестоимости → USD
        project_currency = (getattr(p, "currency", None) or "USD") if p else "USD"
        if project_currency != "USD":
            cur_out = project_currency
        elif e.is_billable and bill_cur != "USD":
            cur_out = bill_cur
        else:
            cur_out = cost_cur or "USD"

        fn, ln = _split_employee_name(
            u.display_name if u else None,
            u.email if u else None,
        )

        rows.append({
            "Date": e.work_date.isoformat(),
            "Recorded At": e.created_at.isoformat(),
            "Client": c.name if c else "",
            "Project": p.name if p else "",
            "Project Code": (p.code or "") if p else "",
            "Task": (e.description or "").strip(),
            "Notes": t.name if t else "",
            "Hours": _hours(hrs),
            "Billable?": "Yes" if e.is_billable else "No",
            "Invoiced?": "Yes" if inv_t else "No",
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
            "Invoice ID": inv_t[1] if inv_t else "",
        })

    return rows


async def get_detailed_time_report(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    client_ids: list[str] | None = None,
    project_ids: list[str] | None = None,
    user_ids: list[int] | None = None,
    task_ids: list[str] | None = None,
    is_billable: bool | None = None,
    include_fixed_fee: bool = True,
    page: int = 1,
    per_page: int = 100,
) -> dict:
    """Вернуть детальный отчёт с пагинацией в стандартном формате {results, pagination, meta}."""
    all_rows = await get_detailed_time_rows(
        session,
        date_from=date_from,
        date_to=date_to,
        client_ids=client_ids,
        project_ids=project_ids,
        user_ids=user_ids,
        task_ids=task_ids,
        is_billable=is_billable,
        include_fixed_fee=include_fixed_fee,
    )
    total = len(all_rows)
    start = (page - 1) * per_page
    results = all_rows[start: start + per_page]
    return build_response(
        results=results,
        total_entries=total,
        page=page,
        per_page=per_page,
        report_type="detailed-time",
        group_by=None,
        date_from=date_from,
        date_to=date_to,
    )
