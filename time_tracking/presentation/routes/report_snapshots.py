"""Снимки отчётов (report snapshots) — список и чтение.

Ранее таблицы и репозиторий были в БД, HTTP-маршрутов не было → фронт получал 404.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import get_session
from infrastructure.models_reports import ReportSnapshotRowModel
from infrastructure.repository_reports import ReportSnapshotRepository
from presentation.deps import require_bearer_user

router = APIRouter(prefix="/reports", tags=["reports"])


def _json_obj(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        o = json.loads(raw)
        return o if isinstance(o, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


@router.get("/snapshots")
async def list_report_snapshots(
    session: AsyncSession = Depends(get_session),
    viewer: dict = Depends(require_bearer_user),
) -> list[dict[str, Any]]:
    """Снимки, созданные текущим пользователем (кратко, с числом строк)."""
    uid = int(viewer["id"])
    repo = ReportSnapshotRepository(session)
    rows = await repo.list_for_user(uid)
    out: list[dict[str, Any]] = []
    for m in rows:
        n = await repo.row_count(m.id)
        out.append(
            {
                "id": m.id,
                "name": m.name,
                "reportType": m.report_type,
                "groupBy": m.group_by,
                "version": m.version,
                "createdAt": m.created_at.isoformat(),
                "updatedAt": m.updated_at.isoformat() if m.updated_at else None,
                "rowCount": n,
            }
        )
    return out


@router.get("/snapshots/{snapshot_id}")
async def get_report_snapshot(
    snapshot_id: str,
    session: AsyncSession = Depends(get_session),
    viewer: dict = Depends(require_bearer_user),
) -> dict[str, Any]:
    """Один снимок со строками; только владелец (создатель)."""
    uid = int(viewer["id"])
    repo = ReportSnapshotRepository(session)
    snap = await repo.get_by_id(snapshot_id, load_rows=True)
    if not snap or snap.created_by_user_id != uid:
        raise HTTPException(status_code=404, detail="Not Found")
    row_models: list[ReportSnapshotRowModel] = list(snap.rows or [])
    row_models.sort(key=lambda r: (r.sort_order, r.id))
    rows_out: list[dict[str, Any]] = []
    for r in row_models:
        rows_out.append(
            {
                "id": r.id,
                "sortOrder": r.sort_order,
                "sourceType": r.source_type,
                "sourceId": r.source_id,
                "data": _json_obj(r.frozen_data_json),
                "overrides": _json_obj(r.overrides_json) if r.overrides_json else None,
                "editedByUserId": r.edited_by_user_id,
                "editedAt": r.edited_at.isoformat() if r.edited_at else None,
            }
        )
    return {
        "id": snap.id,
        "name": snap.name,
        "reportType": snap.report_type,
        "groupBy": snap.group_by,
        "version": snap.version,
        "filters": _json_obj(snap.filters_json),
        "createdAt": snap.created_at.isoformat(),
        "updatedAt": snap.updated_at.isoformat() if snap.updated_at else None,
        "rows": rows_out,
    }
