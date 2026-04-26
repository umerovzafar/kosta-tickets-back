"""Проекты клиента time manager."""

import csv
import json
from datetime import date
from io import StringIO
from typing import Literal

from application.budget_mode import normalize_budget_type_for_persist
from application.project_dashboard import build_client_project_dashboard
from application.project_team_workload import compute_project_team_workload
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from infrastructure.database import get_session
from infrastructure.repositories import ClientProjectRepository
from presentation.routes.client_access import ensure_client_not_archived, get_client_or_404
from presentation.schemas import (
    TeamWorkloadOut,
    TimeManagerClientProjectCodeHintOut,
    TimeManagerClientProjectCreateBody,
    TimeManagerClientProjectOut,
    TimeManagerClientProjectPatchBody,
)

router = APIRouter(prefix="/clients", tags=["client_projects"])

# --- Глобальный список проектов (все клиенты) для формы расходов ---

_global_projects_router = APIRouter(tags=["projects_global"])


@_global_projects_router.get("/projects-for-expenses")
async def list_all_projects_for_expenses(
    include_archived: bool = Query(False, alias="includeArchived"),
    limit: int | None = Query(None, ge=1, le=500, description="Если задано — пагинированный ответ"),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """Плоский список проектов всех клиентов для справочника расходов (id + name + clientName)."""
    repo = ClientProjectRepository(session)
    from infrastructure.repositories import ClientRepository

    cr = ClientRepository(session)
    if limit is None:
        clients = {c.id: c for c in await cr.list_all(include_archived=True)}
        rows = await repo.list_all_global(include_archived=include_archived)
    else:
        rows, total = await repo.list_all_global_paginated(
            include_archived=include_archived, limit=limit, offset=offset
        )
        cids = {r.client_id for r in rows}
        clients = await cr.get_by_ids(cids)
    items = [
        {
            "id": r.id,
            "name": r.name,
            "code": r.code,
            "clientId": r.client_id,
            "clientName": clients[r.client_id].name if r.client_id in clients else None,
            "isArchived": r.is_archived,
        }
        for r in rows
    ]
    if limit is None:
        return items
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@_global_projects_router.get("/projects/{project_id}/expense-categories")
async def list_expense_categories_for_project(
    project_id: str,
    include_archived: bool = Query(False, alias="includeArchived"),
    session: AsyncSession = Depends(get_session),
):
    """Категории расходов клиента, к которому относится проект (для формы расхода)."""
    repo = ClientProjectRepository(session)
    row = await repo.get_by_id_global(project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    from infrastructure.repositories import ClientExpenseCategoryRepository

    ec_repo = ClientExpenseCategoryRepository(session)
    cats = await ec_repo.list_for_client(row.client_id, include_archived=include_archived)
    return [
        {
            "id": c.id,
            "name": c.name,
            "hasUnitPrice": c.has_unit_price,
            "isArchived": c.is_archived,
        }
        for c in cats
    ]


def _parse_dashboard_date(param: str | None) -> date | None:
    if param is None or not str(param).strip():
        return None
    s = str(param).strip()[:10]
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Некорректная дата: {param!r}") from e


def _suggest_next_code(last: str | None) -> str | None:
    if not last or not str(last).strip():
        return None
    s = str(last).strip()
    i = s.rfind("-")
    if i <= 0:
        return None
    prefix, suffix = s[:i], s[i + 1 :]
    if not suffix.isdigit():
        return None
    n = int(suffix)
    width = len(suffix)
    return f"{prefix}-{str(n + 1).zfill(width)}"


def _project_out(row, usage: int) -> TimeManagerClientProjectOut:
    return TimeManagerClientProjectOut(
        id=row.id,
        client_id=row.client_id,
        name=row.name,
        code=row.code,
        start_date=row.start_date,
        end_date=row.end_date,
        notes=row.notes,
        report_visibility=row.report_visibility,
        project_type=row.project_type,
        currency=getattr(row, "currency", "USD") or "USD",
        billable_rate_type=row.billable_rate_type,
        budget_type=row.budget_type,
        budget_amount=row.budget_amount,
        budget_hours=row.budget_hours,
        budget_resets_every_month=row.budget_resets_every_month,
        budget_includes_expenses=row.budget_includes_expenses,
        send_budget_alerts=row.send_budget_alerts,
        budget_alert_threshold_percent=row.budget_alert_threshold_percent,
        fixed_fee_amount=row.fixed_fee_amount,
        is_archived=row.is_archived,
        created_at=row.created_at,
        updated_at=row.updated_at,
        usage_count=usage,
        deletable=usage == 0,
    )


async def _client_projects_to_out(
    repo: ClientProjectRepository,
    rows: list,
) -> list[TimeManagerClientProjectOut]:
    pids = [r.id for r in rows]
    usage_map = await repo.time_entries_counts_by_project_ids(pids)
    return [_project_out(r, usage_map.get(r.id, 0)) for r in rows]


def _validate_date_range(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise HTTPException(
            status_code=400,
            detail="end_date must be on or after start_date",
        )


async def _require_client(session: AsyncSession, client_id: str) -> None:
    await get_client_or_404(session, client_id)


async def _require_client_mutable(session: AsyncSession, client_id: str) -> None:
    row = await get_client_or_404(session, client_id)
    ensure_client_not_archived(row)


@router.get("/{client_id}/projects/code-hint", response_model=TimeManagerClientProjectCodeHintOut)
async def get_client_project_code_hint(
    client_id: str,
    session: AsyncSession = Depends(get_session),
):
    await _require_client(session, client_id)
    repo = ClientProjectRepository(session)
    row = await repo.get_last_project_with_code(client_id)
    last = row.code.strip() if row and row.code else None
    return TimeManagerClientProjectCodeHintOut(
        last_code=last,
        suggested_next=_suggest_next_code(last),
    )


def _export_filename_stub(code: str | None, project_id: str) -> str:
    if code and str(code).strip():
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(code).strip()[:48])
        return safe or project_id
    return project_id


@router.post(
    "/{client_id}/projects/{project_id}/duplicate",
    response_model=TimeManagerClientProjectOut,
)
async def duplicate_client_project(
    client_id: str,
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    await _require_client_mutable(session, client_id)
    repo = ClientProjectRepository(session)
    try:
        row = await repo.duplicate_from(client_id, project_id)
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not duplicate project (code conflict)",
        ) from None
    await session.refresh(row)
    usage = await repo.time_entries_count(row.id)
    return _project_out(row, usage)


@router.get("/{client_id}/projects/{project_id}/export")
async def export_client_project(
    client_id: str,
    project_id: str,
    export_format: Literal["json", "csv"] = Query("json", alias="format"),
    session: AsyncSession = Depends(get_session),
):
    await _require_client(session, client_id)
    repo = ClientProjectRepository(session)
    row = await repo.get_by_id(client_id, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    usage = await repo.time_entries_count(row.id)
    data = _project_out(row, usage).model_dump(mode="json")
    stub = _export_filename_stub(row.code, row.id)
    if export_format == "json":
        body = json.dumps(data, ensure_ascii=False, indent=2)
        return Response(
            content=body.encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{stub}.json"',
            },
        )
    buf = StringIO()
    w = csv.writer(buf)
    flat = {k: ("" if v is None else v) for k, v in data.items()}
    w.writerow(list(flat.keys()))
    w.writerow([str(flat[k]) for k in flat.keys()])
    csv_text = "\ufeff" + buf.getvalue()
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{stub}.csv"',
        },
    )


@router.get("/{client_id}/projects")
async def list_client_projects(
    client_id: str,
    include_archived: bool = Query(False, alias="includeArchived"),
    limit: int | None = Query(None, ge=1, le=500, description="Если задано — пагинированный ответ"),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    await _require_client(session, client_id)
    repo = ClientProjectRepository(session)
    if limit is None:
        rows = await repo.list_for_client(client_id, include_archived=include_archived)
    else:
        rows, total = await repo.list_for_client_paginated(
            client_id, include_archived=include_archived, limit=limit, offset=offset
        )
    out = await _client_projects_to_out(repo, rows)
    if limit is None:
        return out
    return {"items": out, "total": total, "limit": limit, "offset": offset}


@router.get(
    "/{client_id}/projects/{project_id}",
    response_model=TimeManagerClientProjectOut,
)
async def get_client_project(
    client_id: str,
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    await _require_client(session, client_id)
    repo = ClientProjectRepository(session)
    row = await repo.get_by_id(client_id, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    usage = await repo.time_entries_count(row.id)
    return _project_out(row, usage)


@router.get("/{client_id}/projects/{project_id}/dashboard")
async def get_client_project_dashboard(
    client_id: str,
    project_id: str,
    session: AsyncSession = Depends(get_session),
    date_from: str | None = Query(None, description="YYYY-MM-DD"),
    date_to: str | None = Query(None, description="YYYY-MM-DD"),
):
    """Агрегаты для UI деталей проекта: часы из time entries (billable / non-billable по is_billable)."""
    await _require_client(session, client_id)
    df = _parse_dashboard_date(date_from)
    dt = _parse_dashboard_date(date_to)
    try:
        payload = await build_client_project_dashboard(
            session,
            client_id=client_id,
            project_id=project_id,
            date_from=df,
            date_to=dt,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not payload:
        raise HTTPException(status_code=404, detail="Project not found")
    return payload


@router.get("/{client_id}/projects/{project_id}/team-workload", response_model=TeamWorkloadOut)
async def get_project_team_workload(
    client_id: str,
    project_id: str,
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    include_archived: bool = Query(False, alias="includeArchived"),
    session: AsyncSession = Depends(get_session),
):
    """Загрузка команды по проекту (карточки + таблица): часы только по этому project_id."""
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="Параметр to не может быть раньше from")
    await _require_client(session, client_id)
    try:
        out = await compute_project_team_workload(
            session,
            client_id=client_id,
            project_id=project_id,
            date_from=date_from,
            date_to=date_to,
            include_archived=include_archived,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if out is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return out


@router.post("/{client_id}/projects", response_model=TimeManagerClientProjectOut)
async def create_client_project(
    client_id: str,
    body: TimeManagerClientProjectCreateBody,
    session: AsyncSession = Depends(get_session),
):
    await _require_client_mutable(session, client_id)
    _validate_date_range(body.start_date, body.end_date)
    repo = ClientProjectRepository(session)
    if await repo.has_code_conflict(client_id, body.code):
        raise HTTPException(
            status_code=409,
            detail="Another project with this code already exists for this client",
        )
    _bt_persist = normalize_budget_type_for_persist(body.budget_hours, body.budget_amount)
    _budget_type_create = _bt_persist if _bt_persist is not None else body.budget_type
    try:
        row = await repo.create(
            client_id=client_id,
            name=body.name,
            code=body.code,
            start_date=body.start_date,
            end_date=body.end_date,
            notes=body.notes,
            report_visibility=body.report_visibility.value,
            project_type=body.project_type.value,
            currency=body.currency.value if body.currency else "USD",
            billable_rate_type=body.billable_rate_type,
            budget_type=_budget_type_create,
            budget_amount=body.budget_amount,
            budget_hours=body.budget_hours,
            budget_resets_every_month=body.budget_resets_every_month,
            budget_includes_expenses=body.budget_includes_expenses,
            send_budget_alerts=body.send_budget_alerts,
            budget_alert_threshold_percent=body.budget_alert_threshold_percent,
            fixed_fee_amount=body.fixed_fee_amount,
            is_archived=body.is_archived,
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Another project with this code already exists for this client",
        ) from None
    await session.refresh(row)
    usage = await repo.time_entries_count(row.id)
    return _project_out(row, usage)


@router.patch(
    "/{client_id}/projects/{project_id}",
    response_model=TimeManagerClientProjectOut,
)
async def patch_client_project(
    client_id: str,
    project_id: str,
    body: TimeManagerClientProjectPatchBody,
    session: AsyncSession = Depends(get_session),
):
    await _require_client_mutable(session, client_id)
    repo = ClientProjectRepository(session)
    patch = body.model_dump(exclude_unset=True, mode="json", by_alias=False)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")

    row = await repo.get_by_id(client_id, project_id)
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    if "code" in patch and patch["code"] is not None:
        if await repo.has_code_conflict(client_id, str(patch["code"]), exclude_project_id=project_id):
            raise HTTPException(
                status_code=409,
                detail="Another project with this code already exists for this client",
            )

    merged_start = row.start_date
    merged_end = row.end_date
    if "start_date" in patch:
        merged_start = patch["start_date"]
    if "end_date" in patch:
        merged_end = patch["end_date"]
    _validate_date_range(merged_start, merged_end)

    if "report_visibility" in patch and patch["report_visibility"] is not None:
        rv = patch["report_visibility"]
        patch["report_visibility"] = rv.value if hasattr(rv, "value") else str(rv)
    if "project_type" in patch and patch["project_type"] is not None:
        pt = patch["project_type"]
        patch["project_type"] = pt.value if hasattr(pt, "value") else str(pt)
    if "is_archived" in patch and patch["is_archived"] is not None:
        patch["is_archived"] = bool(patch["is_archived"])

    if any(k in patch for k in ("budget_hours", "budget_amount", "budget_type")):
        m_h = patch["budget_hours"] if "budget_hours" in patch else row.budget_hours
        m_a = patch["budget_amount"] if "budget_amount" in patch else row.budget_amount
        nt = normalize_budget_type_for_persist(m_h, m_a)
        patch["budget_type"] = nt

    try:
        updated = await repo.update(client_id, project_id, patch)
        if not updated:
            raise HTTPException(status_code=404, detail="Project not found")
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Another project with this code already exists for this client",
        ) from None

    await session.refresh(updated)
    usage = await repo.time_entries_count(updated.id)
    return _project_out(updated, usage)


@router.delete("/{client_id}/projects/{project_id}", status_code=204)
async def delete_client_project(
    client_id: str,
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    await _require_client_mutable(session, client_id)
    repo = ClientProjectRepository(session)
    usage = await repo.time_entries_count(project_id)
    if usage > 0:
        raise HTTPException(
            status_code=409,
            detail="Project has time entries and cannot be deleted",
        )
    ok = await repo.delete(client_id, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    await session.commit()
    return Response(status_code=204)
