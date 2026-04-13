"""Эндпоинты модуля отчётов time_tracking."""

from __future__ import annotations

import csv
import json
import logging
import traceback
from datetime import date
from io import StringIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

_log = logging.getLogger(__name__)

from application.report_builder import (
    REPORT_TYPES,
    GROUP_OPTIONS,
    build_report_summary,
    build_report_table,
    build_table_rows_flat,
)
from infrastructure.database import get_session
from infrastructure.repository_reports import (
    ReportSavedViewRepository,
    ReportSnapshotRepository,
)
from infrastructure.repository_users import TimeTrackingUserRepository
from presentation.schemas_reports import (
    ReportMetaOut,
    ReportSummaryOut,
    ReportTableOut,
    ReportUserForFilterOut,
    SavedViewCreateBody,
    SavedViewOut,
    SavedViewPatchBody,
    SnapshotCreateBody,
    SnapshotOut,
    SnapshotRowOut,
    SnapshotRowPatchBody,
)

router = APIRouter(prefix="/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(v: str | None, name: str) -> date:
    if not v:
        raise HTTPException(status_code=400, detail=f"{name} is required")
    try:
        return date.fromisoformat(str(v).strip()[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date for {name}: {v}")


def _parse_ids_int(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    out: list[int] = []
    for part in raw.split(","):
        s = part.strip()
        if s:
            try:
                out.append(int(s))
            except ValueError:
                pass
    return out or None


def _parse_ids_str(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    out = [s.strip() for s in raw.split(",") if s.strip()]
    return out or None


def _validate_report_type(rt: str) -> str:
    if rt not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown reportType: {rt}")
    return rt


def _validate_group(g: str | None) -> str | None:
    if g and g not in GROUP_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown group: {g}")
    return g


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


@router.get("/meta", response_model=ReportMetaOut)
async def get_reports_meta():
    return ReportMetaOut(
        reportTypes=sorted(REPORT_TYPES),
        groupOptions=sorted(GROUP_OPTIONS),
    )


# ---------------------------------------------------------------------------
# Users for filter
# ---------------------------------------------------------------------------


@router.get("/users-for-filter", response_model=list[ReportUserForFilterOut])
async def get_users_for_filter(session: AsyncSession = Depends(get_session)):
    repo = TimeTrackingUserRepository(session)
    users = await repo.list_users()
    return [
        ReportUserForFilterOut(
            id=u.auth_user_id,
            displayName=u.display_name,
            email=u.email,
        )
        for u in users
        if not u.is_archived
    ]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


@router.get("/summary")
async def get_report_summary(
    reportType: str = Query(..., alias="reportType"),
    dateFrom: str = Query(..., alias="dateFrom"),
    dateTo: str = Query(..., alias="dateTo"),
    userIds: Optional[str] = Query(None, alias="userIds"),
    projectIds: Optional[str] = Query(None, alias="projectIds"),
    clientIds: Optional[str] = Query(None, alias="clientIds"),
    includeFixedFeeProjects: bool = Query(True, alias="includeFixedFeeProjects"),
    session: AsyncSession = Depends(get_session),
):
    rt = _validate_report_type(reportType)
    df = _parse_date(dateFrom, "dateFrom")
    dt = _parse_date(dateTo, "dateTo")
    try:
        return await build_report_summary(
            session,
            report_type=rt,
            date_from=df,
            date_to=dt,
            user_ids=_parse_ids_int(userIds),
            project_ids=_parse_ids_str(projectIds),
            client_ids=_parse_ids_str(clientIds),
            include_fixed_fee=includeFixedFeeProjects,
        )
    except HTTPException:
        raise
    except Exception as exc:
        tb = traceback.format_exc()
        _log.error("reports/summary error: %s\n%s", exc, tb)
        raise HTTPException(status_code=500, detail=f"Report summary error: {exc}")


# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------


@router.get("/table")
async def get_report_table(
    reportType: str = Query(..., alias="reportType"),
    dateFrom: str = Query(..., alias="dateFrom"),
    dateTo: str = Query(..., alias="dateTo"),
    group: Optional[str] = Query(None),
    userIds: Optional[str] = Query(None, alias="userIds"),
    projectIds: Optional[str] = Query(None, alias="projectIds"),
    clientIds: Optional[str] = Query(None, alias="clientIds"),
    includeFixedFeeProjects: bool = Query(True, alias="includeFixedFeeProjects"),
    sort: str = Query("date_asc"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=500, alias="pageSize"),
    session: AsyncSession = Depends(get_session),
):
    rt = _validate_report_type(reportType)
    _validate_group(group)
    df = _parse_date(dateFrom, "dateFrom")
    dt = _parse_date(dateTo, "dateTo")
    try:
        return await build_report_table(
            session,
            report_type=rt,
            group=group,
            date_from=df,
            date_to=dt,
            user_ids=_parse_ids_int(userIds),
            project_ids=_parse_ids_str(projectIds),
            client_ids=_parse_ids_str(clientIds),
            include_fixed_fee=includeFixedFeeProjects,
            sort=sort,
            page=page,
            page_size=pageSize,
        )
    except HTTPException:
        raise
    except Exception as exc:
        tb = traceback.format_exc()
        _log.error("reports/table error: %s\n%s", exc, tb)
        raise HTTPException(status_code=500, detail=f"Report table error: {exc}")


# ---------------------------------------------------------------------------
# Table export (CSV)
# ---------------------------------------------------------------------------


@router.get("/table/export")
async def export_report_table(
    reportType: str = Query(..., alias="reportType"),
    dateFrom: str = Query(..., alias="dateFrom"),
    dateTo: str = Query(..., alias="dateTo"),
    group: Optional[str] = Query(None),
    userIds: Optional[str] = Query(None, alias="userIds"),
    projectIds: Optional[str] = Query(None, alias="projectIds"),
    clientIds: Optional[str] = Query(None, alias="clientIds"),
    includeFixedFeeProjects: bool = Query(True, alias="includeFixedFeeProjects"),
    sort: str = Query("date_asc"),
    format: str = Query("csv", alias="format"),
    session: AsyncSession = Depends(get_session),
):
    rt = _validate_report_type(reportType)
    _validate_group(group)
    df = _parse_date(dateFrom, "dateFrom")
    dt = _parse_date(dateTo, "dateTo")
    rows = await build_table_rows_flat(
        session,
        report_type=rt,
        group=group,
        date_from=df,
        date_to=dt,
        user_ids=_parse_ids_int(userIds),
        project_ids=_parse_ids_str(projectIds),
        client_ids=_parse_ids_str(clientIds),
        include_fixed_fee=includeFixedFeeProjects,
        sort=sort,
    )
    if format == "json":
        body = json.dumps(rows, ensure_ascii=False, indent=2, default=str)
        return Response(
            content=body.encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="report_{rt}.json"'},
        )
    # CSV
    buf = StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    csv_text = "\ufeff" + buf.getvalue()
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="report_{rt}.csv"'},
    )


# ---------------------------------------------------------------------------
# Saved views
# ---------------------------------------------------------------------------


@router.get("/saved-views", response_model=list[SavedViewOut])
async def list_saved_views(
    ownerUserId: int = Query(..., alias="ownerUserId"),
    session: AsyncSession = Depends(get_session),
):
    repo = ReportSavedViewRepository(session)
    rows = await repo.list_for_user(ownerUserId)
    return [
        SavedViewOut(
            id=r.id,
            name=r.name,
            ownerUserId=r.owner_user_id,
            filters=r.filters_json,
            createdAt=r.created_at,
            updatedAt=r.updated_at,
        )
        for r in rows
    ]


@router.post("/saved-views", response_model=SavedViewOut)
async def create_saved_view(
    body: SavedViewCreateBody,
    session: AsyncSession = Depends(get_session),
    ownerUserId: int = Query(..., alias="ownerUserId"),
):
    repo = ReportSavedViewRepository(session)
    row = await repo.create(
        name=body.name,
        owner_user_id=ownerUserId,
        filters=body.filters.model_dump(mode="json", exclude_none=True),
    )
    await session.commit()
    await session.refresh(row)
    return SavedViewOut(
        id=row.id,
        name=row.name,
        ownerUserId=row.owner_user_id,
        filters=row.filters_json,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


@router.get("/saved-views/{view_id}", response_model=SavedViewOut)
async def get_saved_view(
    view_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = ReportSavedViewRepository(session)
    row = await repo.get_by_id(view_id)
    if not row:
        raise HTTPException(status_code=404, detail="Saved view not found")
    return SavedViewOut(
        id=row.id,
        name=row.name,
        ownerUserId=row.owner_user_id,
        filters=row.filters_json,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


@router.patch("/saved-views/{view_id}", response_model=SavedViewOut)
async def patch_saved_view(
    view_id: str,
    body: SavedViewPatchBody,
    session: AsyncSession = Depends(get_session),
):
    repo = ReportSavedViewRepository(session)
    patch: dict = {}
    if body.name is not None:
        patch["name"] = body.name
    if body.filters is not None:
        patch["filters"] = body.filters.model_dump(mode="json", exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    row = await repo.update(view_id, patch)
    if not row:
        raise HTTPException(status_code=404, detail="Saved view not found")
    await session.commit()
    await session.refresh(row)
    return SavedViewOut(
        id=row.id,
        name=row.name,
        ownerUserId=row.owner_user_id,
        filters=row.filters_json,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


@router.delete("/saved-views/{view_id}", status_code=204)
async def delete_saved_view(
    view_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = ReportSavedViewRepository(session)
    ok = await repo.delete(view_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Saved view not found")
    await session.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


@router.get("/snapshots")
async def list_snapshots(
    createdByUserId: int = Query(..., alias="createdByUserId"),
    session: AsyncSession = Depends(get_session),
):
    repo = ReportSnapshotRepository(session)
    snaps = await repo.list_for_user(createdByUserId)
    out = []
    for s in snaps:
        rc = await repo.row_count(s.id)
        out.append(
            SnapshotOut(
                id=s.id,
                name=s.name,
                reportType=s.report_type,
                groupBy=s.group_by,
                filters=s.filters_json,
                version=s.version,
                createdByUserId=s.created_by_user_id,
                createdAt=s.created_at,
                updatedAt=s.updated_at,
                rowCount=rc,
            )
        )
    return out


@router.post("/snapshots")
async def create_snapshot(
    body: SnapshotCreateBody,
    createdByUserId: int = Query(..., alias="createdByUserId"),
    session: AsyncSession = Depends(get_session),
):
    rt = _validate_report_type(body.reportType)
    filters_dict = body.filters.model_dump(mode="json", exclude_none=True)
    df = _parse_date(filters_dict.get("dateFrom"), "dateFrom")
    dt = _parse_date(filters_dict.get("dateTo"), "dateTo")

    flat_rows = await build_table_rows_flat(
        session,
        report_type=rt,
        group=body.group,
        date_from=df,
        date_to=dt,
        user_ids=filters_dict.get("userIds"),
        project_ids=filters_dict.get("projectIds"),
        client_ids=filters_dict.get("clientIds"),
        include_fixed_fee=filters_dict.get("includeFixedFeeProjects", True),
        sort=filters_dict.get("sort", "date_asc"),
    )

    rows_data = [
        {
            "source_type": r.get("sourceType", "row"),
            "source_id": r.get("sourceId") or r.get("rowId", ""),
            "data": r,
        }
        for r in flat_rows
    ]

    repo = ReportSnapshotRepository(session)
    snap = await repo.create(
        name=body.name,
        report_type=rt,
        group_by=body.group,
        filters=filters_dict,
        created_by_user_id=createdByUserId,
        rows_data=rows_data,
    )
    await session.commit()
    rc = await repo.row_count(snap.id)
    return SnapshotOut(
        id=snap.id,
        name=snap.name,
        reportType=snap.report_type,
        groupBy=snap.group_by,
        filters=snap.filters_json,
        version=snap.version,
        createdByUserId=snap.created_by_user_id,
        createdAt=snap.created_at,
        updatedAt=snap.updated_at,
        rowCount=rc,
    )


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot(
    snapshot_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = ReportSnapshotRepository(session)
    snap = await repo.get_by_id(snapshot_id, load_rows=True)
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    rows_out = [
        SnapshotRowOut(
            id=r.id,
            sortOrder=r.sort_order,
            sourceType=r.source_type,
            sourceId=r.source_id,
            data=r.frozen_data_json,
            overrides=r.overrides_json,
            editedByUserId=r.edited_by_user_id,
            editedAt=r.edited_at,
        )
        for r in (snap.rows or [])
    ]
    return SnapshotOut(
        id=snap.id,
        name=snap.name,
        reportType=snap.report_type,
        groupBy=snap.group_by,
        filters=snap.filters_json,
        version=snap.version,
        createdByUserId=snap.created_by_user_id,
        createdAt=snap.created_at,
        updatedAt=snap.updated_at,
        rowCount=len(rows_out),
        rows=rows_out,
    )


@router.patch("/snapshots/{snapshot_id}/rows/{row_id}")
async def patch_snapshot_row(
    snapshot_id: str,
    row_id: str,
    body: SnapshotRowPatchBody,
    editedByUserId: int = Query(..., alias="editedByUserId"),
    session: AsyncSession = Depends(get_session),
):
    repo = ReportSnapshotRepository(session)
    snap = await repo.get_by_id(snapshot_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    row = await repo.patch_row(snapshot_id, row_id, body.overrides, editedByUserId)
    if not row:
        raise HTTPException(status_code=404, detail="Snapshot row not found")
    await session.commit()
    await session.refresh(row)
    return SnapshotRowOut(
        id=row.id,
        sortOrder=row.sort_order,
        sourceType=row.source_type,
        sourceId=row.source_id,
        data=row.frozen_data_json,
        overrides=row.overrides_json,
        editedByUserId=row.edited_by_user_id,
        editedAt=row.edited_at,
    )


@router.post("/snapshots/{snapshot_id}/rebuild-from-source")
async def rebuild_snapshot(
    snapshot_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = ReportSnapshotRepository(session)
    snap = await repo.get_by_id(snapshot_id)
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    filters = json.loads(snap.filters_json) if isinstance(snap.filters_json, str) else snap.filters_json
    df = _parse_date(filters.get("dateFrom"), "dateFrom")
    dt = _parse_date(filters.get("dateTo"), "dateTo")

    flat_rows = await build_table_rows_flat(
        session,
        report_type=snap.report_type,
        group=snap.group_by,
        date_from=df,
        date_to=dt,
        user_ids=filters.get("userIds"),
        project_ids=filters.get("projectIds"),
        client_ids=filters.get("clientIds"),
        include_fixed_fee=filters.get("includeFixedFeeProjects", True),
        sort=filters.get("sort", "date_asc"),
    )

    rows_data = [
        {
            "source_type": r.get("sourceType", "row"),
            "source_id": r.get("sourceId") or r.get("rowId", ""),
            "data": r,
        }
        for r in flat_rows
    ]

    snap = await repo.rebuild_rows(snapshot_id, rows_data)
    await session.commit()
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    rc = await repo.row_count(snap.id)
    return SnapshotOut(
        id=snap.id,
        name=snap.name,
        reportType=snap.report_type,
        groupBy=snap.group_by,
        filters=snap.filters_json,
        version=snap.version,
        createdByUserId=snap.created_by_user_id,
        createdAt=snap.created_at,
        updatedAt=snap.updated_at,
        rowCount=rc,
    )


@router.delete("/snapshots/{snapshot_id}", status_code=204)
async def delete_snapshot(
    snapshot_id: str,
    session: AsyncSession = Depends(get_session),
):
    repo = ReportSnapshotRepository(session)
    ok = await repo.delete(snapshot_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    await session.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Snapshot export
# ---------------------------------------------------------------------------


@router.get("/snapshots/{snapshot_id}/export")
async def export_snapshot(
    snapshot_id: str,
    format: str = Query("csv", alias="format"),
    session: AsyncSession = Depends(get_session),
):
    repo = ReportSnapshotRepository(session)
    snap = await repo.get_by_id(snapshot_id, load_rows=True)
    if not snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    rows: list[dict] = []
    for r in (snap.rows or []):
        data = json.loads(r.frozen_data_json) if isinstance(r.frozen_data_json, str) else {}
        if r.overrides_json:
            ov = json.loads(r.overrides_json) if isinstance(r.overrides_json, str) else {}
            data.update(ov)
        rows.append(data)

    fname = f"snapshot_{snapshot_id[:8]}"
    if format == "json":
        body = json.dumps(rows, ensure_ascii=False, indent=2, default=str)
        return Response(
            content=body.encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}.json"'},
        )
    buf = StringIO()
    if rows:
        all_keys: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for k in row:
                if k not in seen:
                    all_keys.append(k)
                    seen.add(k)
        w = csv.DictWriter(buf, fieldnames=all_keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    csv_text = "\ufeff" + buf.getvalue()
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}.csv"'},
    )
