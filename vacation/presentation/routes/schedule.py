from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from infrastructure.database import get_session
from infrastructure.models import AbsenceDay, ScheduleEmployee

router = APIRouter(prefix="/schedule", tags=["schedule"])

KIND_LABELS: dict[int, str] = {
    1: "annual_vacation",
    2: "sick_leave",
    3: "day_off",
    4: "business_trip",
    5: "remote_work",
}


class EmployeeOut(BaseModel):
    id: int
    year: int
    excel_row_no: int | None
    full_name: str
    planned_period_note: str | None = None


class AbsenceDayOut(BaseModel):
    absence_on: date
    kind_code: int
    kind: str = Field(description="Стабильный ключ вида отсутствия")


class AbsenceDayWithEmployeeOut(AbsenceDayOut):
    employee_id: int
    full_name: str


class EmployeeWithAbsencesOut(EmployeeOut):
    absence_days: list[AbsenceDayOut]


@router.get("/kind-codes", response_model=dict[str, str])
async def kind_codes() -> dict[str, str]:
    """Расшифровка kind_code из легенды графика (ежегодный отпуск, болезнь, …)."""
    return {str(k): v for k, v in KIND_LABELS.items()}


@router.get("/employees", response_model=list[EmployeeOut])
async def list_employees(
    year: int = Query(..., ge=2000, le=2100),
    session: AsyncSession = Depends(get_session),
):
    r = await session.execute(
        select(ScheduleEmployee).where(ScheduleEmployee.year == year).order_by(ScheduleEmployee.excel_row_no.nulls_last(), ScheduleEmployee.id)
    )
    rows = r.scalars().all()
    return [
        EmployeeOut(
            id=e.id,
            year=e.year,
            excel_row_no=e.excel_row_no,
            full_name=e.full_name,
            planned_period_note=e.planned_period_note,
        )
        for e in rows
    ]


@router.get("/employees/{employee_id}", response_model=EmployeeWithAbsencesOut)
async def get_employee(
    employee_id: int,
    year: int | None = Query(None, ge=2000, le=2100),
    session: AsyncSession = Depends(get_session),
):
    q = (
        select(ScheduleEmployee)
        .options(selectinload(ScheduleEmployee.absence_days))
        .where(ScheduleEmployee.id == employee_id)
    )
    r = await session.execute(q)
    e = r.scalar_one_or_none()
    if e is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    if year is not None and e.year != year:
        raise HTTPException(status_code=404, detail="Employee not found for this year")
    days = sorted(e.absence_days, key=lambda d: d.absence_on)
    return EmployeeWithAbsencesOut(
        id=e.id,
        year=e.year,
        excel_row_no=e.excel_row_no,
        full_name=e.full_name,
        planned_period_note=e.planned_period_note,
        absence_days=[
            AbsenceDayOut(
                absence_on=d.absence_on,
                kind_code=d.kind_code,
                kind=KIND_LABELS.get(d.kind_code, "unknown"),
            )
            for d in days
        ],
    )


@router.get("/absence-days", response_model=list[AbsenceDayWithEmployeeOut])
async def list_absence_days(
    year: int = Query(..., ge=2000, le=2100),
    employee_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    session: AsyncSession = Depends(get_session),
):
    q = select(AbsenceDay, ScheduleEmployee).join(ScheduleEmployee).where(ScheduleEmployee.year == year)
    if employee_id is not None:
        q = q.where(AbsenceDay.employee_id == employee_id)
    if date_from is not None:
        q = q.where(AbsenceDay.absence_on >= date_from)
    if date_to is not None:
        q = q.where(AbsenceDay.absence_on <= date_to)
    q = q.order_by(AbsenceDay.absence_on, AbsenceDay.employee_id)
    r = await session.execute(q)
    out: list[AbsenceDayWithEmployeeOut] = []
    for d, emp in r.all():
        out.append(
            AbsenceDayWithEmployeeOut(
                employee_id=emp.id,
                full_name=emp.full_name,
                absence_on=d.absence_on,
                kind_code=d.kind_code,
                kind=KIND_LABELS.get(d.kind_code, "unknown"),
            )
        )
    return out
