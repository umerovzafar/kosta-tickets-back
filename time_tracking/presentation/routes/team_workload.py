"""Агрегат «загрузка команды» за период (карточки + таблица сотрудников)."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from application.team_workload_math import capacity_for_period, period_days_inclusive, workload_percent
from infrastructure.database import get_session
from infrastructure.repositories import TimeEntryRepository, TimeTrackingUserRepository
from presentation.schemas import (
    TeamWorkloadMemberOut,
    TeamWorkloadOut,
    TeamWorkloadSummaryOut,
)

router = APIRouter(prefix="/team-workload", tags=["team_workload"])


@router.get("", response_model=TeamWorkloadOut)
async def get_team_workload(
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    include_archived: bool = Query(False, alias="includeArchived"),
    session: AsyncSession = Depends(get_session),
) -> TeamWorkloadOut:
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="Параметр to не может быть раньше from")
    try:
        pdays = period_days_inclusive(date_from, date_to)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    user_repo = TimeTrackingUserRepository(session)
    entry_repo = TimeEntryRepository(session)

    users = await user_repo.list_users()
    rows = [u for u in users if (include_archived or not u.is_archived) and not u.is_blocked]

    sums = await entry_repo.aggregate_by_user(date_from, date_to)

    members: list[TeamWorkloadMemberOut] = []
    total_hours = Decimal("0")
    billable_sum = Decimal("0")
    non_sum = Decimal("0")
    team_cap = Decimal("0")

    for u in sorted(rows, key=lambda x: (x.display_name or x.email or "").lower()):
        cap = capacity_for_period(u.weekly_capacity_hours, date_from, date_to)
        tot, bill, nonb = sums.get(u.auth_user_id, (Decimal("0"), Decimal("0"), Decimal("0")))
        total_hours += tot
        billable_sum += bill
        non_sum += nonb
        team_cap += cap
        members.append(
            TeamWorkloadMemberOut(
                auth_user_id=u.auth_user_id,
                display_name=u.display_name,
                email=u.email,
                capacity_hours=cap,
                total_hours=tot,
                billable_hours=bill,
                non_billable_hours=nonb,
                workload_percent=workload_percent(tot, cap),
            )
        )

    summary = TeamWorkloadSummaryOut(
        total_hours=total_hours,
        team_capacity_hours=team_cap,
        billable_hours=billable_sum,
        non_billable_hours=non_sum,
        team_workload_percent=workload_percent(total_hours, team_cap),
    )

    return TeamWorkloadOut(
        date_from=date_from,
        date_to=date_to,
        period_days=pdays,
        summary=summary,
        members=members,
    )
