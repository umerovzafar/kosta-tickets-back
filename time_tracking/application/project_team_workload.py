"""Загрузка команды за период, отфильтрованная по одному проекту (часы только с project_id)."""

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from application.team_workload_math import capacity_for_period, period_days_inclusive, workload_percent
from infrastructure.repositories import (
    ClientProjectRepository,
    TimeEntryRepository,
    TimeTrackingUserRepository,
    UserProjectAccessRepository,
)
from presentation.schemas import TeamWorkloadMemberOut, TeamWorkloadOut, TeamWorkloadSummaryOut


async def compute_project_team_workload(
    session: AsyncSession,
    *,
    client_id: str,
    project_id: str,
    date_from: date,
    date_to: date,
    include_archived: bool,
) -> TeamWorkloadOut | None:
    """
    Участники строки таблицы:
    - все с записью в time_tracking_user_project_access на этот project_id;
    - плюс все, у кого за период есть time entry с этим project_id (даже без строки доступа).

    Ёмкость и % загрузки — как у глобального /team-workload (weekly_capacity × дни/7).
    """
    proj_repo = ClientProjectRepository(session)
    row = await proj_repo.get_by_id(client_id, project_id)
    if not row:
        return None

    pdays = period_days_inclusive(date_from, date_to)
    user_repo = TimeTrackingUserRepository(session)
    entry_repo = TimeEntryRepository(session)
    access_repo = UserProjectAccessRepository(session)

    from_access = await access_repo.list_auth_user_ids_for_project(project_id)
    from_entries = await entry_repo.list_auth_users_with_entries_on_project(
        date_from, date_to, project_id
    )
    member_ids = sorted(set(from_access) | set(from_entries))

    users = await user_repo.list_users()
    by_id = {u.auth_user_id: u for u in users}

    sums = await entry_repo.aggregate_by_user_for_project(date_from, date_to, project_id)

    members: list[TeamWorkloadMemberOut] = []
    total_hours = Decimal("0")
    billable_sum = Decimal("0")
    non_sum = Decimal("0")
    team_cap = Decimal("0")
    team_weekly = Decimal("0")

    for uid in member_ids:
        u = by_id.get(uid)
        if u is None:
            continue
        if u.is_blocked:
            continue
        if not include_archived and u.is_archived:
            continue
        cap = capacity_for_period(u.weekly_capacity_hours, date_from, date_to)
        tot, bill, nonb = sums.get(u.auth_user_id, (Decimal("0"), Decimal("0"), Decimal("0")))
        total_hours += tot
        billable_sum += bill
        non_sum += nonb
        team_cap += cap
        team_weekly += u.weekly_capacity_hours
        members.append(
            TeamWorkloadMemberOut(
                auth_user_id=u.auth_user_id,
                display_name=u.display_name,
                email=u.email,
                picture=u.picture,
                capacity_hours=cap,
                total_hours=tot,
                billable_hours=bill,
                non_billable_hours=nonb,
                workload_percent=workload_percent(tot, cap),
            )
        )

    members.sort(key=lambda m: (m.display_name or m.email or "").lower())

    summary = TeamWorkloadSummaryOut(
        total_hours=total_hours,
        team_capacity_hours=team_cap,
        team_weekly_capacity_hours=team_weekly,
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
        project_id=project_id,
        client_id=client_id,
        project_name=row.name,
    )
