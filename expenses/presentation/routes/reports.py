from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import get_session
from infrastructure.repositories import ExpenseRepository
from presentation.deps import check_view_role, created_by_filter_for_user, get_current_user
from presentation.schemas import (
    ByDateReportOut,
    CalendarDayOut,
    CalendarReportOut,
    DynamicsPoint,
    SummaryReportOut,
)
from presentation.routes.requests import _to_out

router = APIRouter(prefix="/reports", tags=["reports"])


def _period_bounds(period: str, anchor: date, date_from: date | None, date_to: date | None) -> tuple[date, date]:
    if period == "day":
        return anchor, anchor
    if period == "week":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if period == "month":
        _, last = monthrange(anchor.year, anchor.month)
        return date(anchor.year, anchor.month, 1), date(anchor.year, anchor.month, last)
    if period == "custom":
        if not date_from or not date_to:
            raise HTTPException(status_code=400, detail="Для периода custom укажите date_from и date_to")
        if date_from > date_to:
            raise HTTPException(status_code=400, detail="date_from не может быть позже date_to")
        return date_from, date_to
    raise HTTPException(status_code=400, detail="period: day|week|month|custom")


@router.get("/summary", response_model=SummaryReportOut)
async def report_summary(
    period: str = Query("day", pattern="^(day|week|month|custom)$"),
    anchor: date | None = Query(None, description="Базовая дата (по умолчанию сегодня)"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    budget_category: str | None = Query(None),
    currency: str = Query("UZS"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    anchor_d = anchor or date.today()
    d0, d1 = _period_bounds(period, anchor_d, date_from, date_to)
    uid = created_by_filter_for_user(user)
    repo = ExpenseRepository(session)
    total, ops, appr = await repo.summary_stats(
        created_by_user_id=uid,
        date_from=d0,
        date_to=d1,
        budget_category=budget_category,
    )
    return SummaryReportOut(
        date_from=d0,
        date_to=d1,
        currency=currency,
        total_amount=total,
        operations_count=ops,
        approved_count=appr,
    )


@router.get("/dynamics", response_model=list[DynamicsPoint])
async def report_dynamics(
    period: str = Query("month", pattern="^(day|week|month|custom)$"),
    anchor: date | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    budget_category: str | None = Query(None),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    anchor_d = anchor or date.today()
    d0, d1 = _period_bounds(period, anchor_d, date_from, date_to)
    uid = created_by_filter_for_user(user)
    repo = ExpenseRepository(session)
    rows = await repo.dynamics_by_day(
        created_by_user_id=uid,
        date_from=d0,
        date_to=d1,
        budget_category=budget_category,
        status_filter="approved",
    )
    return [DynamicsPoint(date=d, total_amount=amt, count=cnt) for d, amt, cnt in rows]


@router.get("/calendar", response_model=CalendarReportOut)
async def report_calendar(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    uid = created_by_filter_for_user(user)
    repo = ExpenseRepository(session)
    raw = await repo.calendar_days(created_by_user_id=uid, year=year, month=month)
    by_day = {d: (amt, cnt) for d, amt, cnt in raw}
    _, last = monthrange(year, month)
    days: list[CalendarDayOut] = []
    for day in range(1, last + 1):
        d = date(year, month, day)
        amt, cnt = by_day.get(d, (0, 0))
        has = cnt > 0
        days.append(
            CalendarDayOut(
                date=d,
                total_amount=amt,
                count=cnt,
                has_expenses=has,
            )
        )
    return CalendarReportOut(year=year, month=month, days=days)


@router.get("/by-date", response_model=ByDateReportOut)
async def report_by_date(
    day: date = Query(..., alias="date"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    uid = created_by_filter_for_user(user)
    repo = ExpenseRepository(session)
    rows = await repo.list_by_expense_date(created_by_user_id=uid, day=day)
    approved_total = sum((r.amount for r in rows if r.status == "approved"), Decimal("0"))
    approved_count = sum(1 for r in rows if r.status == "approved")
    total_all = sum((r.amount for r in rows), Decimal("0"))
    return ByDateReportOut(
        date=day,
        total_amount=total_all,
        approved_total=approved_total,
        approved_count=approved_count,
        items=[_to_out(r) for r in rows],
    )
