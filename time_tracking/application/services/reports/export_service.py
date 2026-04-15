"""Export Service — генерация CSV и XLSX из данных отчётов."""

from __future__ import annotations

import csv
from datetime import date
from io import BytesIO, StringIO
from typing import Any

from starlette.responses import Response


def _filename(report_type: str, group_by: str | None, date_from: date, date_to: date, fmt: str) -> str:
    """Имя файла согласно ТЗ: time_projects_2026-04-01_2026-04-15.xlsx"""
    parts = [report_type]
    if group_by:
        parts.append(group_by)
    parts.append(date_from.isoformat())
    parts.append(date_to.isoformat())
    return "_".join(parts) + f".{fmt}"


def _collect_fieldnames(rows: list[dict]) -> list[str]:
    seen: set[str] = set()
    keys: list[str] = []
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                keys.append(k)
    return keys


def export_csv(
    rows: list[dict],
    report_type: str,
    group_by: str | None,
    date_from: date,
    date_to: date,
) -> Response:
    buf = StringIO()
    if rows:
        fieldnames = _collect_fieldnames(rows)
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(rows)
    # UTF-8 BOM for Excel compatibility
    content = ("\ufeff" + buf.getvalue()).encode("utf-8")
    fname = _filename(report_type, group_by, date_from, date_to, "csv")
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def export_xlsx(
    rows: list[dict],
    report_type: str,
    group_by: str | None,
    date_from: date,
    date_to: date,
) -> Response:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError as exc:
        raise RuntimeError("openpyxl is required for XLSX export") from exc

    wb = Workbook()
    ws = wb.active
    ws.title = "Report"

    fieldnames = _collect_fieldnames(rows) if rows else []

    # Header row
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col_idx, name in enumerate(fieldnames, start=1):
        cell = ws.cell(row=1, column=col_idx, value=_humanize_header(name))
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row_idx, row in enumerate(rows, start=2):
        for col_idx, name in enumerate(fieldnames, start=1):
            val = row.get(name, "")
            if val is None:
                val = ""
            ws.cell(row=row_idx, column=col_idx, value=val)

    # Auto-width columns
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 50)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    fname = _filename(report_type, group_by, date_from, date_to, "xlsx")
    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _humanize_header(name: str) -> str:
    """Преобразовать snake_case в заголовок с заглавной буквы."""
    return name.replace("_", " ").title()


def export_report(
    rows: list[dict],
    fmt: str,
    report_type: str,
    group_by: str | None,
    date_from: date,
    date_to: date,
) -> Response:
    """Точка входа: выбрать формат и сгенерировать файл."""
    if fmt == "xlsx":
        return export_xlsx(rows, report_type, group_by, date_from, date_to)
    return export_csv(rows, report_type, group_by, date_from, date_to)
