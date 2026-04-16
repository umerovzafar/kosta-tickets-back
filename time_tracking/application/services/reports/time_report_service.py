"""Time Report Service — агрегированные отчёты по времени.

Группировки: clients, projects, tasks, team.

Для группировок clients / projects / tasks каждая строка содержит поле `users` —
список пользователей, вносивших время в этот бакет, с детализацией их часов;
для tasks в строке также `client_id` / `client_name` (клиент справочника задачи).
Для группировки team каждая строка сама является пользователем.
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
            "user_buckets": {},      # uid -> {total, billable, amount, currency}
        })
        h = _d(e.hours)
        bkt["total"] += h
        # Обновляем валюту из проекта если она ещё не задана
        if bkt["currency"] == "USD" and project_currency != "USD":
            bkt["currency"] = project_currency

        uid = e.auth_user_id
        ubkt = bkt["user_buckets"].setdefault(uid, {
            "total": _ZERO, "billable": _ZERO, "amount": _ZERO, "currency": project_currency,
        })
        ubkt["total"] += h

        if e.is_billable:
            bkt["billable"] += h
            amt, cur = _billable_amount_for_entry(
                h, True, e.work_date, rates_map.get(uid),
            )
            # Используем валюту проекта, если ставка не переопределяет
            effective_cur = project_currency if project_currency != "USD" else cur
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
    if group_by == "team":
        return e.auth_user_id
    elif group_by == "projects":
        return e.project_id
    elif group_by == "clients":
        p = projects_map.get(e.project_id) if e.project_id else None
        return p.client_id if p else None
    else:  # tasks
        return e.task_id


def _build_users_list(user_buckets: dict, users_map: dict) -> list[dict[str, Any]]:
    """Построить список пользователей с их часами для вложенного поля `users`."""
    result = []
    for uid, ubkt in user_buckets.items():
        u = users_map.get(uid)
        result.append({
            "user_id": uid,
            "user_name": (u.display_name or u.email) if u else str(uid or ""),
            "avatar_url": u.picture if u else None,
            "total_hours": _hours(ubkt["total"]),
            "billable_hours": _hours(ubkt["billable"]),
            "billable_amount": _money(ubkt["amount"]),
            "currency": ubkt["currency"],
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

    if group_by == "clients":
        c = clients_map.get(gid) if gid else None
        row["client_id"] = gid
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
        t = tasks_map.get(gid) if gid else None
        row["task_id"] = gid
        row["task_name"] = t.name if t else None
        row["client_id"] = t.client_id if t else None
        c = clients_map.get(t.client_id) if (t and t.client_id) else None
        row["client_name"] = c.name if c else None
        row["users"] = _build_users_list(bkt["user_buckets"], users_map)

    else:  # team — строка сама является пользователем
        u = users_map.get(gid) if gid else None
        row["user_id"] = gid
        row["user_name"] = (u.display_name or u.email) if u else str(gid or "")
        row["is_contractor"] = False
        row["weekly_capacity"] = float(u.weekly_capacity_hours) if u else 0.0
        row["avatar_url"] = u.picture if u else None

    return row
