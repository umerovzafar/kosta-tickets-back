"""Time Report Service — отчёты по времени (группировка clients / projects).

Каждая запись в `users[].entries` и строки плоского экспорта содержат полный набор полей
(даты, клиент, проект, код проекта, задача, деньги, cost, счёт, сдача недели, внешняя ссылка).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from application.report_builder import (
    _base_entry_conditions,
    _billable_amount_for_entry,
    _billable_rate_for_entry,
    _cost_amount_for_entry,
    _d,
    _load_user_cost_rates,
    _load_clients_map,
    _load_projects_map,
    _load_tasks_map,
    _load_user_rates,
    _load_users_map,
    invoice_details_for_time_entries,
    load_week_submitted_user_dates,
)
from infrastructure.models import TimeEntryModel
from application.services.reports._base import _hours, _money, _ZERO, build_response

TIME_GROUP_OPTIONS = frozenset({"clients", "projects"})

# Срез вложенного списка записей на группу/пользователя (анти-перегруз JSON).
MAX_ENTRY_LOG_ROWS = 100_000

# Порядок колонок CSV/XLSX (см. export_service).
TIME_REPORT_FLAT_COLUMNS: tuple[str, ...] = (
    "work_date",
    "recorded_at",
    "client_id",
    "client_name",
    "project_id",
    "project_name",
    "project_code",
    "task_id",
    "task_name",
    "note",
    "hours",
    "is_billable",
    "task_billable_by_default",
    "is_invoiced",
    "is_paid",
    "is_week_submitted",
    "employee_name",
    "employee_position",
    "auth_user_id",
    "billable_rate",
    "amount_to_pay",
    "cost_rate",
    "cost_amount",
    "currency",
    "external_reference_url",
    "invoice_id",
    "invoice_number",
    "time_entry_id",
    "report_group_by",
    "report_group_id",
)


def _time_entry_line_snake(
    e: TimeEntryModel,
    *,
    projects_map: dict[str, Any],
    clients_map: dict[str, Any],
    tasks_map: dict[str, Any],
    users_map: dict[int, Any],
    rates_map: dict[int, list],
    cost_rates_map: dict[int, list],
    invoice_by_entry: dict[str, dict[str, Any]],
    week_submitted: set[tuple[int, date]],
) -> dict[str, Any]:
    """Одна строка отчёта: все обязательные меры (None где неприменимо)."""
    p = projects_map.get(e.project_id) if e.project_id else None
    c = clients_map.get(p.client_id) if p and p.client_id else None
    t = tasks_map.get(e.task_id) if e.task_id else None
    u = users_map.get(e.auth_user_id)
    project_currency = (getattr(p, "currency", None) or "USD") if p else "USD"
    h = _d(e.hours)
    uid = e.auth_user_id
    brates = rates_map.get(uid) or []
    crates = cost_rates_map.get(uid) or []
    amt, _cur = _billable_amount_for_entry(
        h, e.is_billable, e.work_date, brates, project_currency=project_currency
    )
    br, _brc = _billable_rate_for_entry(
        e.work_date, brates, project_currency=project_currency
    )
    cost_amt, cost_r, _cnc = _cost_amount_for_entry(
        h, e.work_date, crates, project_currency=project_currency
    )
    inv = invoice_by_entry.get(e.id) or {}
    is_invoiced = e.id in invoice_by_entry
    is_paid = bool(inv.get("is_paid")) if is_invoiced else False
    wk_ok = (uid, e.work_date) in week_submitted
    desc = (e.description or "").strip()
    ext = (e.external_reference_url or "").strip() or None

    return {
        "time_entry_id": e.id,
        "work_date": e.work_date.isoformat(),
        "recorded_at": e.created_at.isoformat(),
        "client_id": c.id if c else None,
        "client_name": c.name if c else None,
        "project_id": e.project_id,
        "project_name": p.name if p else None,
        "project_code": p.code if p else None,
        "task_id": e.task_id,
        "task_name": t.name if t else None,
        "note": desc or None,
        "hours": _hours(h),
        "is_billable": e.is_billable,
        "task_billable_by_default": bool(t.billable_by_default) if t else None,
        "is_invoiced": is_invoiced,
        "is_paid": is_paid,
        "is_week_submitted": wk_ok,
        "employee_name": (u.display_name or u.email) if u else str(uid),
        "employee_position": (u.role or "") if u else None,
        "auth_user_id": uid,
        "billable_rate": _money(br) if br is not None else None,
        "amount_to_pay": _money(amt),
        "cost_rate": _money(cost_r) if cost_r is not None else None,
        "cost_amount": _money(cost_amt),
        "currency": project_currency,
        "external_reference_url": ext,
        "invoice_id": inv.get("invoice_id"),
        "invoice_number": inv.get("invoice_number"),
    }


def _line_snake_to_api_json(line: dict[str, Any]) -> dict[str, Any]:
    """camelCase + поля для UI; сохраняем часть старых имён (projectId, description, …)."""
    out: dict[str, Any] = {
        "timeEntryId": line["time_entry_id"],
        "workDate": line["work_date"],
        "recordedAt": line["recorded_at"],
        "clientId": line["client_id"],
        "clientName": line["client_name"],
        "projectId": line["project_id"],
        "projectName": line["project_name"],
        "projectCode": line["project_code"],
        "taskId": line["task_id"],
        "taskName": line["task_name"],
        "note": line["note"],
        "hours": line["hours"],
        "isBillable": line["is_billable"],
        "taskBillableByDefault": line["task_billable_by_default"],
        "isInvoiced": line["is_invoiced"],
        "isPaid": line["is_paid"],
        "isWeekSubmitted": line["is_week_submitted"],
        "employeeName": line["employee_name"],
        "employeePosition": line["employee_position"] or None,
        "authUserId": line["auth_user_id"],
        "billableRate": line["billable_rate"],
        "amountToPay": line["amount_to_pay"],
        "costRate": line["cost_rate"],
        "costAmount": line["cost_amount"],
        "currency": line["currency"],
        "externalReferenceUrl": line["external_reference_url"],
        "invoiceId": line["invoice_id"],
        "invoiceNumber": line["invoice_number"],
    }
    # обратная совместимость с прежними вложенными `entries`
    eid = line["time_entry_id"]
    out["id"] = eid
    out["time_entry_id"] = eid
    out["work_date"] = line["work_date"]
    out["recorded_at"] = line["recorded_at"]
    out["is_billable"] = line["is_billable"]
    out["client_id"] = line["client_id"]
    out["client_name"] = line["client_name"]
    out["project_id"] = line["project_id"]
    out["project_name"] = line["project_name"]
    out["task_id"] = line["task_id"]
    out["task_name"] = line["task_name"]
    out["description"] = line["note"]
    return out


async def get_time_report(
    session: AsyncSession,
    *,
    group_by: str,
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
    cond = _base_entry_conditions(
        date_from, date_to, user_ids, project_ids, client_ids, include_fixed_fee,
    )
    if is_billable is not None:
        cond.append(TimeEntryModel.is_billable.is_(is_billable))
    if task_ids:
        cond.append(TimeEntryModel.task_id.in_(task_ids))

    entries_q = select(TimeEntryModel).where(and_(*cond))
    entries = list((await session.execute(entries_q)).scalars().all())

    users_map = await _load_users_map(session)
    projects_map = await _load_projects_map(session)
    clients_map = await _load_clients_map(session)
    tasks_map = await _load_tasks_map(session)
    uids = {e.auth_user_id for e in entries}
    inv_map = await invoice_details_for_time_entries(session, [e.id for e in entries])
    week_set = await load_week_submitted_user_dates(session, uids, date_from, date_to)
    rates_map = await _load_user_rates(session, list(uids)) if uids else {}
    cost_rates_map = await _load_user_cost_rates(session, list(uids)) if uids else {}

    line_ctx = {
        "projects_map": projects_map,
        "clients_map": clients_map,
        "tasks_map": tasks_map,
        "users_map": users_map,
        "rates_map": rates_map,
        "cost_rates_map": cost_rates_map,
        "invoice_by_entry": inv_map,
        "week_submitted": week_set,
    }

    buckets: dict[Any, dict] = {}
    for e in entries:
        gid = _get_group_id(e, group_by, projects_map)
        p = projects_map.get(e.project_id) if e.project_id else None
        project_currency = (getattr(p, "currency", None) or "USD") if p else "USD"
        sline = _time_entry_line_snake(e, **line_ctx)
        eline = _line_snake_to_api_json(sline)

        bkt = buckets.setdefault(
            gid,
            {
                "total": _ZERO,
                "billable": _ZERO,
                "amount": _ZERO,
                "currency": project_currency,
                "last_recorded_at": None,
                "user_buckets": {},
            },
        )
        if bkt["last_recorded_at"] is None or e.created_at > bkt["last_recorded_at"]:
            bkt["last_recorded_at"] = e.created_at
        h = _d(e.hours)
        bkt["total"] += h
        uid = e.auth_user_id
        ubkt = bkt["user_buckets"].setdefault(
            uid,
            {
                "total": _ZERO,
                "billable": _ZERO,
                "amount": _ZERO,
                "currency": project_currency,
                "last_recorded_at": None,
                "entry_events": [],
            },
        )
        if ubkt["last_recorded_at"] is None or e.created_at > ubkt["last_recorded_at"]:
            ubkt["last_recorded_at"] = e.created_at
        ubkt["entry_events"].append(eline)
        ubkt["total"] += h
        if e.is_billable:
            bkt["billable"] += h
            br = rates_map.get(uid)
            amt, effective_cur = _billable_amount_for_entry(
                h, True, e.work_date, br, project_currency=project_currency
            )
            bkt["amount"] += amt
            bkt["currency"] = effective_cur or project_currency
            ubkt["billable"] += h
            ubkt["amount"] += amt
            ubkt["currency"] = effective_cur or project_currency

    all_rows: list[dict] = []
    for gid, bkt in buckets.items():
        row = _build_row(gid, bkt, group_by, users_map, projects_map, clients_map)
        all_rows.append(row)

    all_rows.sort(key=lambda r: r.get("total_hours", 0), reverse=True)
    total_entries_count = len(all_rows)
    start = (page - 1) * per_page
    results = all_rows[start : start + per_page]

    return build_response(
        results=results,
        total_entries=total_entries_count,
        page=page,
        per_page=per_page,
        report_type="time",
        group_by=group_by,
        date_from=date_from,
        date_to=date_to,
    )


async def get_time_report_all_rows(
    session: AsyncSession, **kwargs: Any
) -> list[dict]:
    """Получить все **агрегированные** строки без пагинации (устар. для API)."""
    kwargs["page"] = 1
    kwargs["per_page"] = 100_000
    result = await get_time_report(session, **kwargs)
    return result.get("results", [])


async def get_time_report_flat_entries(
    session: AsyncSession,
    *,
    group_by: str,
    date_from: date,
    date_to: date,
    client_ids: list[str] | None = None,
    project_ids: list[str] | None = None,
    user_ids: list[int] | None = None,
    task_ids: list[str] | None = None,
    is_billable: bool | None = None,
    include_fixed_fee: bool = True,
) -> list[dict[str, Any]]:
    """Плоский список: одна строка на факт списания времени (для CSV/XLSX), все колонки."""
    cond = _base_entry_conditions(
        date_from, date_to, user_ids, project_ids, client_ids, include_fixed_fee,
    )
    if is_billable is not None:
        cond.append(TimeEntryModel.is_billable.is_(is_billable))
    if task_ids:
        cond.append(TimeEntryModel.task_id.in_(task_ids))
    entries_q = select(TimeEntryModel).where(and_(*cond))
    entries = list((await session.execute(entries_q)).scalars().all())

    users_map = await _load_users_map(session)
    projects_map = await _load_projects_map(session)
    clients_map = await _load_clients_map(session)
    tasks_map = await _load_tasks_map(session)
    uids = {e.auth_user_id for e in entries}
    inv_map = await invoice_details_for_time_entries(session, [e.id for e in entries])
    week_set = await load_week_submitted_user_dates(session, uids, date_from, date_to)
    rates_map = await _load_user_rates(session, list(uids)) if uids else {}
    cost_rates_map = await _load_user_cost_rates(session, list(uids)) if uids else {}
    line_ctx: dict[str, Any] = {
        "projects_map": projects_map,
        "clients_map": clients_map,
        "tasks_map": tasks_map,
        "users_map": users_map,
        "rates_map": rates_map,
        "cost_rates_map": cost_rates_map,
        "invoice_by_entry": inv_map,
        "week_submitted": week_set,
    }

    flat: list[dict[str, Any]] = []
    for e in entries:
        sline = _time_entry_line_snake(e, **line_ctx)
        g = _get_group_id(e, group_by, projects_map)
        if isinstance(g, tuple) and len(g) == 2:
            a, b = g
            sline["report_group_id"] = f"{a}|{b}"
        else:
            sline["report_group_id"] = str(g) if g is not None else None
        sline["report_group_by"] = group_by
        flat.append(sline)

    flat.sort(
        key=lambda r: (
            r.get("work_date") or "",
            r.get("auth_user_id") or 0,
            r.get("recorded_at") or "",
            r.get("time_entry_id") or "",
        )
    )
    return [_row_for_export(r) for r in flat]


def _row_for_export(r: dict[str, Any]) -> dict[str, Any]:
    """Фиксированный порядок и набор полей (одинаковые ключи в каждой строке)."""
    return {k: r.get(k) for k in TIME_REPORT_FLAT_COLUMNS}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_group_id(e: Any, group_by: str, projects_map: dict) -> Any:
    p = projects_map.get(e.project_id) if e.project_id else None
    pc = (getattr(p, "currency", None) or "USD") if p else "USD"
    if group_by == "projects":
        return e.project_id
    if group_by == "clients":
        cid = p.client_id if p else None
        return (cid, pc) if cid is not None else (None, pc)
    raise ValueError(f"Unsupported time report group_by: {group_by!r}")


def _entry_log_payload(ubkt: dict, *, max_n: int = MAX_ENTRY_LOG_ROWS) -> dict[str, Any]:
    events = sorted(ubkt.get("entry_events") or [], key=lambda x: x.get("recordedAt", ""), reverse=True)
    total_n = len(events)
    truncated = total_n > max_n
    last_dt = ubkt.get("last_recorded_at")
    return {
        "last_recorded_at": last_dt.isoformat() if last_dt else None,
        "entries": events[:max_n],
        "entries_total": total_n,
        "entries_truncated": truncated,
    }


def _build_users_list(user_buckets: dict, users_map: dict) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for uid, ubkt in user_buckets.items():
        u = users_map.get(uid)
        log = _entry_log_payload(ubkt)
        result.append(
            {
                "user_id": uid,
                "user_name": (u.display_name or u.email) if u else str(uid or ""),
                "avatar_url": u.picture if u else None,
                "total_hours": _hours(ubkt["total"]),
                "billable_hours": _hours(ubkt["billable"]),
                "billable_amount": _money(ubkt["amount"]),
                "currency": ubkt["currency"],
                **log,
            }
        )
    result.sort(key=lambda r: r["total_hours"], reverse=True)
    return result


def _build_row(
    gid: Any,
    bkt: dict,
    group_by: str,
    users_map: dict,
    projects_map: dict,
    clients_map: dict,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "total_hours": _hours(bkt["total"]),
        "billable_hours": _hours(bkt["billable"]),
        "currency": bkt["currency"],
        "billable_amount": _money(bkt["amount"]),
    }

    last_bucket = bkt.get("last_recorded_at")
    row["last_recorded_at"] = last_bucket.isoformat() if last_bucket else None

    if group_by == "clients":
        cid: Any
        if isinstance(gid, tuple) and len(gid) == 2:
            cid, _pcur = gid
        else:
            cid = gid
        c = clients_map.get(cid) if cid else None
        row["client_id"] = cid
        row["client_name"] = c.name if c else None
        row["users"] = _build_users_list(bkt["user_buckets"], users_map)
    elif group_by == "projects":
        p = projects_map.get(gid) if gid else None
        c = clients_map.get(p.client_id) if (p and p.client_id) else None
        row["client_id"] = p.client_id if p else None
        row["client_name"] = c.name if c else None
        row["project_id"] = gid
        row["project_name"] = p.name if p else None
        row["users"] = _build_users_list(bkt["user_buckets"], users_map)
    else:
        raise ValueError(f"Unsupported time report group_by: {group_by!r}")

    return row
