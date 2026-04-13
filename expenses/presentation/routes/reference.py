"""Справочники: типы расходов, подразделения, проекты, курсы."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import get_session
from infrastructure.repositories import ExpenseRepository
from presentation.deps import check_view_role, get_current_user
from presentation.schemas import DepartmentRefOut, ExchangeRateOut, ExpenseTypeRefOut, ProjectRefOut

router = APIRouter(tags=["expenses-reference"])


@router.get("/expense-types", response_model=list[ExpenseTypeRefOut])
async def list_expense_types(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    rows = await repo.list_expense_types()
    return [ExpenseTypeRefOut(code=r.code, label=r.label, sort_order=r.sort_order) for r in rows]


@router.get("/departments", response_model=list[DepartmentRefOut])
async def list_departments(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    rows = await repo.list_departments()
    return [DepartmentRefOut(id=r.id, name=r.name) for r in rows]


@router.get("/projects", response_model=list[ProjectRefOut])
async def list_projects(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    rows = await repo.list_projects()
    return [ProjectRefOut(id=r.id, name=r.name) for r in rows]


@router.get("/expenses/project-totals/{project_id}")
async def get_project_expense_totals(
    project_id: str,
    date_from: date | None = Query(None, alias="dateFrom"),
    date_to: date | None = Query(None, alias="dateTo"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Агрегация расходов по project_id (approved/paid/closed) — для дашборда проекта TT."""
    check_view_role(user)
    repo = ExpenseRepository(session)
    return await repo.aggregate_expenses_for_project(project_id, date_from, date_to)


@router.get("/exchange-rates", response_model=ExchangeRateOut)
async def get_exchange_rate(
    date_param: date = Query(..., alias="date"),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_exchange_rate_for_date(date_param)
    if not row:
        raise HTTPException(status_code=404, detail="Курс на указанную дату не найден")
    return ExchangeRateOut(date=row.rate_date, rate=row.rate, pair_label=row.pair_label)
