"""Проекты клиента time manager."""

import csv
import json
from datetime import date
from io import StringIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from infrastructure.database import get_session
from infrastructure.repositories import ClientProjectRepository, ClientRepository
from presentation.schemas import (
    TimeManagerClientProjectCodeHintOut,
    TimeManagerClientProjectCreateBody,
    TimeManagerClientProjectOut,
    TimeManagerClientProjectPatchBody,
)

router = APIRouter(prefix="/clients", tags=["client_projects"])


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


def _validate_date_range(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise HTTPException(
            status_code=400,
            detail="end_date must be on or after start_date",
        )


async def _require_client(session: AsyncSession, client_id: str) -> None:
    repo = ClientRepository(session)
    if not await repo.get_by_id(client_id):
        raise HTTPException(status_code=404, detail="Client not found")


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
    await _require_client(session, client_id)
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


@router.get("/{client_id}/projects", response_model=list[TimeManagerClientProjectOut])
async def list_client_projects(
    client_id: str,
    include_archived: bool = Query(False, alias="includeArchived"),
    session: AsyncSession = Depends(get_session),
):
    await _require_client(session, client_id)
    repo = ClientProjectRepository(session)
    rows = await repo.list_for_client(client_id, include_archived=include_archived)
    out: list[TimeManagerClientProjectOut] = []
    for r in rows:
        usage = await repo.time_entries_count(r.id)
        out.append(_project_out(r, usage))
    return out


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


@router.post("/{client_id}/projects", response_model=TimeManagerClientProjectOut)
async def create_client_project(
    client_id: str,
    body: TimeManagerClientProjectCreateBody,
    session: AsyncSession = Depends(get_session),
):
    await _require_client(session, client_id)
    _validate_date_range(body.start_date, body.end_date)
    repo = ClientProjectRepository(session)
    if await repo.has_code_conflict(client_id, body.code):
        raise HTTPException(
            status_code=409,
            detail="Another project with this code already exists for this client",
        )
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
            billable_rate_type=body.billable_rate_type,
            budget_type=body.budget_type,
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
    await _require_client(session, client_id)
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
    await _require_client(session, client_id)
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
