"""Агрегаты дашборда проекта из time entries (в т.ч. non-billable по флагу is_billable)."""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import (
    ClientProjectRepository,
    ClientRepository,
    TimeEntryRepository,
    TimeTrackingUserRepository,
)


def _hours_json(d: Decimal) -> float:
    return float(d.quantize(Decimal("0.01")))


async def build_client_project_dashboard(
    session: AsyncSession,
    *,
    client_id: str,
    project_id: str,
    date_from: date | None,
    date_to: date | None,
) -> dict | None:
    cpr = ClientProjectRepository(session)
    if not await cpr.get_by_id(client_id, project_id):
        return None
    if date_from is not None and date_to is not None and date_to < date_from:
        raise ValueError("Параметр date_to не может быть раньше date_from")

    cr = ClientRepository(session)
    client_row = await cr.get_by_id(client_id)
    currency: str | None = None
    if client_row and client_row.currency:
        c = str(client_row.currency).strip()
        currency = c if c else None

    entry_repo = TimeEntryRepository(session)
    tot, bill, nonb = await entry_repo.aggregate_totals_for_project(project_id, date_from, date_to)
    weeks = await entry_repo.aggregate_hours_by_week_for_project(project_id, date_from, date_to)
    by_user = await entry_repo.aggregate_by_user_for_project(date_from, date_to, project_id)

    user_repo = TimeTrackingUserRepository(session)
    by_auth = {u.auth_user_id: u for u in await user_repo.list_users()}

    def _member_sort_key(item: tuple[int, tuple[Decimal, Decimal, Decimal]]) -> str:
        uid, _ = item
        u = by_auth.get(uid)
        return (u.display_name or u.email or str(uid)).lower() if u else str(uid).lower()

    team: list[dict] = []
    for uid, (ut, ub, un) in sorted(by_user.items(), key=_member_sort_key):
        if ut <= 0:
            continue
        u = by_auth.get(uid)
        label = (u.display_name or u.email or str(uid)) if u else str(uid)
        team.append(
            {
                "user_id": str(uid),
                "name": label,
                "hours": _hours_json(ut),
                "billable_hours": _hours_json(ub),
                "non_billable_hours": _hours_json(un),
                "billable_amount": 0,
                "internal_cost_amount": 0,
            }
        )

    hours_by_week = [
        {
            "week_start": wk.isoformat(),
            "hours": _hours_json(t),
            "billable_hours": _hours_json(b),
            "non_billable_hours": _hours_json(n),
        }
        for wk, t, b, n in weeks
    ]

    return {
        "currency": currency,
        "totals": {
            "total_hours": _hours_json(tot),
            "billable_hours": _hours_json(bill),
            "non_billable_hours": _hours_json(nonb),
            "billable_amount": 0,
            "internal_cost_amount": 0,
            "internal_costs_complete": True,
            "unbilled_amount": 0,
        },
        "progress_by_week": [],
        "hours_by_week": hours_by_week,
        "tasks": [],
        "team": team,
        "invoices": [],
    }
