"""Project Budget Report Service — отчёт по бюджетам проектов."""

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
    _load_user_rates,
    _load_users_map,
)
from infrastructure.models import TimeEntryModel, TimeManagerClientProjectModel
from application.services.reports._base import _d, _hours, _money, _ZERO, build_response


async def get_budget_report(
    session: AsyncSession,
    *,
    date_from: date,
    date_to: date,
    client_ids: list[str] | None = None,
    project_ids: list[str] | None = None,
    user_ids: list[int] | None = None,
    include_fixed_fee: bool = True,
    page: int = 1,
    per_page: int = 100,
) -> dict:
    projects_map = await _load_projects_map(session)
    clients_map = await _load_clients_map(session)
    users_map = await _load_users_map(session)

    # Filter projects
    target_projects = list(projects_map.values())
    if project_ids:
        pids_set = set(project_ids)
        target_projects = [p for p in target_projects if p.id in pids_set]
    if client_ids:
        cids_set = set(client_ids)
        target_projects = [p for p in target_projects if p.client_id in cids_set]
    if not include_fixed_fee:
        target_projects = [p for p in target_projects if p.project_type != "fixed_fee"]

    target_pids = [p.id for p in target_projects]
    if not target_pids:
        return build_response(
            results=[],
            total_entries=0,
            page=page,
            per_page=per_page,
            report_type="project-budget",
            group_by=None,
            date_from=date_from,
            date_to=date_to,
        )

    # Load time entries to calculate budget_spent
    cond = _base_entry_conditions(
        date_from, date_to, user_ids, target_pids, client_ids, True,
    )
    # Бюджет проекта считается по округлённым часам (согласовано со счетами и отчётами).
    entries_q = select(TimeEntryModel).where(and_(*cond))
    entries = list((await session.execute(entries_q)).scalars().all())

    all_user_ids = list({e.auth_user_id for e in entries})
    rates_map = await _load_user_rates(session, all_user_ids or None)

    # Aggregate hours/amount per project + per-user tracking
    hours_by_project: dict[str, Decimal] = {}
    amount_by_project: dict[str, Decimal] = {}
    # pid -> { uid -> {hours, amount} }
    user_buckets_by_project: dict[str, dict[int, dict]] = {}

    for e in entries:
        pid = e.project_id
        if pid is None:
            continue
        h = _d(e.hours)
        hours_by_project[pid] = hours_by_project.get(pid, _ZERO) + h

        uid = e.auth_user_id
        if pid not in user_buckets_by_project:
            user_buckets_by_project[pid] = {}
        ubkt = user_buckets_by_project[pid].setdefault(uid, {"hours": _ZERO, "amount": _ZERO})
        ubkt["hours"] += h

        if e.is_billable:
            p_ent = projects_map.get(pid)
            pc = (getattr(p_ent, "currency", None) or "USD") if p_ent else "USD"
            amt, _ = _billable_amount_for_entry(
                h, e.is_billable, e.work_date, rates_map.get(uid), project_currency=pc,
            )
            amount_by_project[pid] = amount_by_project.get(pid, _ZERO) + amt
            ubkt["amount"] += amt

    all_rows: list[dict] = []
    for p in target_projects:
        c = clients_map.get(p.client_id) if p.client_id else None

        budget_by, budget_val = _get_budget_info(p)
        spent = _get_budget_spent(p, hours_by_project, amount_by_project)
        remaining = max(_ZERO, budget_val - spent) if budget_val > _ZERO else _ZERO

        user_buckets = user_buckets_by_project.get(p.id, {})
        users_list = _build_users_list(user_buckets, users_map, budget_by)
        project_currency = (getattr(p, "currency", None) or "USD")

        all_rows.append({
            "client_id": p.client_id,
            "client_name": c.name if c else None,
            "project_id": p.id,
            "project_name": p.name,
            "currency": project_currency,
            "budget_is_monthly": p.budget_resets_every_month,
            "budget_by": budget_by,
            "is_active": not p.is_archived,
            "budget": _budget_display(budget_val, budget_by),
            "budget_spent": _budget_display(spent, budget_by),
            "budget_remaining": _budget_display(remaining, budget_by),
            "users": users_list,
        })

    all_rows.sort(key=lambda r: r.get("project_name") or "", reverse=False)

    total_entries_count = len(all_rows)
    start = (page - 1) * per_page
    results = all_rows[start: start + per_page]

    return build_response(
        results=results,
        total_entries=total_entries_count,
        page=page,
        per_page=per_page,
        report_type="project-budget",
        group_by=None,
        date_from=date_from,
        date_to=date_to,
    )


async def get_budget_report_all_rows(
    session: AsyncSession, **kwargs: Any
) -> list[dict]:
    kwargs["page"] = 1
    kwargs["per_page"] = 100_000
    result = await get_budget_report(session, **kwargs)
    return result.get("results", [])


def _get_budget_info(p: Any) -> tuple[str, Decimal]:
    """Определить тип бюджета и его значение."""
    budget_type = (p.budget_type or "").lower()
    if "hour" in budget_type and p.budget_hours:
        return "hours", _d(p.budget_hours)
    if p.budget_amount:
        return "money", _d(p.budget_amount)
    if p.budget_hours:
        return "hours", _d(p.budget_hours)
    return "money", _ZERO


def _get_budget_spent(
    p: Any,
    hours_by_project: dict[str, Decimal],
    amount_by_project: dict[str, Decimal],
) -> Decimal:
    budget_type = (p.budget_type or "").lower()
    if "hour" in budget_type:
        return hours_by_project.get(p.id, _ZERO)
    return amount_by_project.get(p.id, _ZERO)


def _budget_display(val: Decimal, budget_by: str) -> float:
    if budget_by == "hours":
        return _hours(val)
    return _money(val)


def _build_users_list(
    user_buckets: dict,
    users_map: dict,
    budget_by: str,
) -> list[dict[str, Any]]:
    """Список пользователей, логировавших время по проекту."""
    result = []
    for uid, ubkt in user_buckets.items():
        u = users_map.get(uid)
        result.append({
            "user_id": uid,
            "user_name": (u.display_name or u.email) if u else str(uid or ""),
            "avatar_url": u.picture if u else None,
            "hours_logged": _hours(ubkt["hours"]),
            "amount_logged": _money(ubkt["amount"]),
        })
    result.sort(key=lambda r: r["hours_logged"], reverse=True)
    return result
