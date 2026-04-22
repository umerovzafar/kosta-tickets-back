"""Time Report Service — агрегированные отчёты по времени.

Группировки: clients, projects, tasks, team.

Для группировок clients / projects / tasks каждая строка содержит поле `users` —
список пользователей, вносивших время в этот бакет, с детализацией их часов;
у строки и у каждого пользователя — `last_recorded_at` (ISO), плюс у пользователя
`entries` (до 50 последних записей: дата, время, часы, проект/клиент/задача/комментарий),
`entries_total`, `entries_truncated`;
для tasks в строке также `client_id` / `client_name` (клиент справочника задачи).
Для группировки team каждая строка сама является пользователем.

Суммы billable (число + валюта) всегда в **валюте проекта** записи времени. Для clients /
tasks / team бакет — это не только id сущности, а **(id, project_currency)**, чтобы
не складывать разные валюты в одной строке; одна и та же задача/клиент/сотрудник
может появиться **несколько раз** (по разным валютам). group_by=projects — по-прежнему
один проект = одна валюта, ключ только project_id.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from application.report_builder import (
    _base_entry_conditions,
    _billable_amount_for_entry,
    _load_clients_map,
    _load_projects_map,
    _load_tasks_map,
    _load_user_rates,
    _load_users_map,
)
from infrastructure.models import TimeEntryModel
from application.services.reports._base import _d, _hours, _money, _ZERO, build_response

TIME_GROUP_OPTIONS = frozenset({"clients", "projects", "tasks", "team"})


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
    rates_map = await _load_user_rates(session, user_ids)

    # Структура бакета: общие итоги + разбивка по пользователям
    buckets: dict[Any, dict] = {}
    for e in entries:
        gid = _get_group_id(e, group_by, projects_map)
        # Определяем валюту проекта как приоритетную
        p = projects_map.get(e.project_id) if e.project_id else None
        project_currency = (getattr(p, "currency", None) or "USD") if p else "USD"

        bkt = buckets.setdefault(gid, {
            "total": _ZERO,
            "billable": _ZERO,
            "amount": _ZERO,
            "currency": project_currency,
            "last_recorded_at": None,
            "user_buckets": {},      # uid -> {total, billable, amount, currency, …}
        })
        if bkt["last_recorded_at"] is None or e.created_at > bkt["last_recorded_at"]:
            bkt["last_recorded_at"] = e.created_at
        h = _d(e.hours)
        bkt["total"] += h

        uid = e.auth_user_id
        ubkt = bkt["user_buckets"].setdefault(uid, {
            "total": _ZERO,
            "billable": _ZERO,
            "amount": _ZERO,
            "currency": project_currency,
            "last_recorded_at": None,
            "entry_events": [],
        })
        if ubkt["last_recorded_at"] is None or e.created_at > ubkt["last_recorded_at"]:
            ubkt["last_recorded_at"] = e.created_at
        ubkt["entry_events"].append(
            _entry_event_dict(
                e,
                projects_map=projects_map,
                clients_map=clients_map,
                tasks_map=tasks_map,
            )
        )
        ubkt["total"] += h

        if e.is_billable:
            bkt["billable"] += h
            amt, cur = _billable_amount_for_entry(
                h, e.is_billable, e.work_date, rates_map.get(uid), project_currency=project_currency,
            )
            effective_cur = project_currency
            bkt["amount"] += amt
            bkt["currency"] = effective_cur

            ubkt["billable"] += h
            ubkt["amount"] += amt
            ubkt["currency"] = effective_cur

    all_rows: list[dict] = []
    for gid, bkt in buckets.items():
        row = _build_row(gid, bkt, group_by, users_map, projects_map, clients_map, tasks_map)
        all_rows.append(row)

    all_rows.sort(key=lambda r: r.get("total_hours", 0), reverse=True)

    total_entries_count = len(all_rows)
    start = (page - 1) * per_page
    results = all_rows[start: start + per_page]

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
    """Получить все строки без пагинации (для экспорта)."""
    kwargs["page"] = 1
    kwargs["per_page"] = 100_000
    result = await get_time_report(session, **kwargs)
    return result.get("results", [])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_group_id(e: Any, group_by: str, projects_map: dict) -> Any:
    p = projects_map.get(e.project_id) if e.project_id else None
    pc = (getattr(p, "currency", None) or "USD") if p else "USD"
    if group_by == "team":
        return (e.auth_user_id, pc)
    if group_by == "projects":
        return e.project_id
    if group_by == "clients":
        cid = p.client_id if p else None
        return (cid, pc) if cid is not None else (None, pc)
    # tasks — одна сущность (task) может встречаться в проектах с разной валютой
    return (e.task_id, pc)


MAX_ENTRY_LOG_ROWS = 50


def _entry_event_dict(
    e: TimeEntryModel,
    *,
    projects_map: dict,
    clients_map: dict,
    tasks_map: dict,
) -> dict[str, Any]:
    """Одна запись времени для вложенного списка `entries` (команда и разрезы с `users`)."""
    p = projects_map.get(e.project_id) if e.project_id else None
    cid = p.client_id if p else None
    c = clients_map.get(cid) if cid else None
    t = tasks_map.get(e.task_id) if e.task_id else None
    desc = (e.description or "").strip()
    base = {
        "id": e.id,
        "time_entry_id": e.id,
        "work_date": e.work_date.isoformat(),
        "recorded_at": e.created_at.isoformat(),
        "hours": _hours(_d(e.hours)),
        "is_billable": e.is_billable,
        "project_id": e.project_id,
        "project_name": p.name if p else None,
        "client_id": cid,
        "client_name": c.name if c else None,
        "task_id": e.task_id,
        "task_name": t.name if t else None,
        "description": desc or None,
        "projectId": e.project_id,
        "projectName": p.name if p else None,
        "clientId": cid,
        "clientName": c.name if c else None,
        "taskId": e.task_id,
        "taskName": t.name if t else None,
    }
    return base


def _entry_log_payload(ubkt: dict, *, max_n: int = MAX_ENTRY_LOG_ROWS) -> dict[str, Any]:
    """Журнал записей времени для одного пользователя в бакете (срез + флаги)."""
    events = sorted(ubkt.get("entry_events") or [], key=lambda x: x["recorded_at"], reverse=True)
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
    """Построить список пользователей с их часами для вложенного поля `users`."""
    result = []
    for uid, ubkt in user_buckets.items():
        u = users_map.get(uid)
        log = _entry_log_payload(ubkt)
        result.append({
            "user_id": uid,
            "user_name": (u.display_name or u.email) if u else str(uid or ""),
            "avatar_url": u.picture if u else None,
            "total_hours": _hours(ubkt["total"]),
            "billable_hours": _hours(ubkt["billable"]),
            "billable_amount": _money(ubkt["amount"]),
            "currency": ubkt["currency"],
            **log,
        })
    result.sort(key=lambda r: r["total_hours"], reverse=True)
    return result


def _build_row(
    gid: Any,
    bkt: dict,
    group_by: str,
    users_map: dict,
    projects_map: dict,
    clients_map: dict,
    tasks_map: dict,
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

    elif group_by == "tasks":
        tid: Any
        if isinstance(gid, tuple) and len(gid) == 2:
            tid, _pcur = gid
        else:
            tid = gid
        t = tasks_map.get(tid) if tid else None
        row["task_id"] = tid
        row["task_name"] = t.name if t else None
        row["client_id"] = t.client_id if t else None
        c = clients_map.get(t.client_id) if (t and t.client_id) else None
        row["client_name"] = c.name if c else None
        row["users"] = _build_users_list(bkt["user_buckets"], users_map)

    else:  # team — строка сама является пользователем
        tuid: Any
        if isinstance(gid, tuple) and len(gid) == 2:
            tuid, _pcur = gid
        else:
            tuid = gid
        u = users_map.get(tuid) if tuid is not None else None
        row["user_id"] = tuid
        row["user_name"] = (u.display_name or u.email) if u else str(tuid or "")
        row["is_contractor"] = False
        row["weekly_capacity"] = float(u.weekly_capacity_hours) if u else 0.0
        row["avatar_url"] = u.picture if u else None
        ub = bkt["user_buckets"].get(tuid) if tuid is not None else None
        if ub:
            row.update(_entry_log_payload(ub))
        else:
            row["entries"] = []
            row["entries_total"] = 0
            row["entries_truncated"] = False

    return row
