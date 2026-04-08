from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker, selectinload
from starlette.concurrency import run_in_threadpool

from application.excel_schedule_import import import_schedule_from_workbook
from infrastructure.config import get_settings
from infrastructure.database import get_session
from infrastructure.db_sync import sync_engine_url
from infrastructure.models import AbsenceDay, ScheduleEmployee

router = APIRouter(prefix="/schedule", tags=["schedule"])

MAX_IMPORT_FILE_BYTES = 20 * 1024 * 1024

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


class ImportResultOut(BaseModel):
    year: int
    employees_imported: int
    absence_days_imported: int


def _sync_import_bytes(db_url: str, content: bytes, year: int, sheet: str | None) -> tuple[int, int]:
    engine = create_engine(sync_engine_url(db_url), echo=False)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with SessionLocal() as session:
        return import_schedule_from_workbook(
            session,
            year=year,
            sheet_name=sheet,
            source=content,
        )


@router.post("/import", response_model=ImportResultOut)
async def import_excel_upload(
    year: int = Form(..., ge=2000, le=2100),
    file: UploadFile = File(...),
    sheet: str | None = Form(None),
):
    """
    Загрузка .xlsx: парсинг и замена в БД данных только за указанный `year`.
    Даты в колонках файла должны быть того же календарного года, что и `year`.
    """
    settings = get_settings()
    db_url = (settings.database_url or "").strip()
    if not db_url:
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")

    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Ожидается файл Excel (.xlsx или .xlsm)")

    content = await file.read()
    if len(content) > MAX_IMPORT_FILE_BYTES:
        raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 20 МБ)")

    sheet_name = sheet.strip() if sheet and sheet.strip() else None

    try:
        emp, days = await run_in_threadpool(_sync_import_bytes, db_url, content, year, sheet_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Не удалось прочитать или разобрать файл: {e}",
        ) from e

    return ImportResultOut(year=year, employees_imported=emp, absence_days_imported=days)


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
