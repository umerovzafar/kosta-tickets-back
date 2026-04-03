"""
Публичный GET по ссылке из письма: утверждение / отклонение без Bearer (токен в query).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.config import get_settings
from infrastructure.database import get_session
from infrastructure.email_action_token import verify_email_action_token
from infrastructure.repositories import ExpenseRepository

router = APIRouter(prefix="/expenses", tags=["expenses"])

# В audit / history: действие по ссылке из письма (нет user id модератора)
_EMAIL_ACTION_USER_ID = 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _page(title: str, message: str, ok: bool) -> str:
    color = "#16a34a" if ok else "#dc2626"
    return f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title></head>
<body style="margin:0;font-family:Segoe UI,Arial,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;">
<div style="max-width:420px;text-align:center;">
<p style="color:{color};font-size:48px;margin:0 0 16px 0;">{'✓' if ok else '!'}</p>
<h1 style="font-size:20px;margin:0 0 12px 0;font-weight:600;">{title}</h1>
<p style="color:#94a3b8;font-size:15px;line-height:1.5;margin:0;">{message}</p>
<p style="color:#64748b;font-size:12px;margin:24px 0 0 0;">Kosta Legal · расходы</p>
</div></body></html>"""


@router.get("/{expense_id}/email-action", response_class=HTMLResponse)
async def expense_email_action(
    expense_id: str,
    token: str = Query(..., description="Подписанный токен из письма"),
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    secret = (settings.expense_email_action_secret or "").strip()
    if not secret:
        return HTMLResponse(
            _page("Ссылка недоступна", "На сервере не задан EXPENSE_EMAIL_ACTION_SECRET.", False),
            status_code=503,
        )
    try:
        action = verify_email_action_token(secret, token=token, expense_id=expense_id)
    except ValueError as e:
        return HTMLResponse(
            _page("Ссылка недействительна", str(e), False),
            status_code=400,
        )

    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        return HTMLResponse(_page("Заявка не найдена", f"Нет заявки {expense_id}.", False), status_code=404)

    if row.status == "approved" and action == "approve":
        return HTMLResponse(
            _page("Уже утверждено", f"Заявка {expense_id} уже была утверждена.", True),
            status_code=200,
        )
    if row.status == "rejected" and action == "reject":
        return HTMLResponse(
            _page("Уже отклонено", f"Заявка {expense_id} уже была отклонена.", True),
            status_code=200,
        )
    if row.status != "pending_approval":
        return HTMLResponse(
            _page(
                "Действие недоступно",
                f"Статус заявки: «{row.status}». Согласование по ссылке возможно только в статусе «на согласовании».",
                False,
            ),
            status_code=409,
        )

    uid = _EMAIL_ACTION_USER_ID
    prev = row.status

    if action == "approve":
        row.status = "approved"
        row.approved_at = _utc_now()
        row.updated_by_user_id = uid
        row.updated_at = _utc_now()
        await repo.add_status_history(
            expense_request_id=row.id,
            from_status=prev,
            to_status="approved",
            changed_by_user_id=uid,
            comment=None,
        )
        await repo.add_audit(
            expense_request_id=row.id,
            action="approved_via_email_link",
            field_name="status",
            old_value=prev,
            new_value="approved",
            performed_by_user_id=uid,
        )
        await session.commit()
        return HTMLResponse(
            _page("Заявка утверждена", f"Расход {expense_id} отмечен как утверждённый.", True),
            status_code=200,
        )

    reason = "Отклонено по ссылке из письма"
    row.status = "rejected"
    row.rejected_at = _utc_now()
    row.updated_by_user_id = uid
    row.updated_at = _utc_now()
    await repo.add_status_history(
        expense_request_id=row.id,
        from_status=prev,
        to_status="rejected",
        changed_by_user_id=uid,
        comment=reason,
    )
    await repo.add_audit(
        expense_request_id=row.id,
        action="rejected_via_email_link",
        field_name="status",
        old_value=prev,
        new_value=f"rejected: {reason}",
        performed_by_user_id=uid,
    )
    await session.commit()
    return HTMLResponse(
        _page("Заявка отклонена", f"Расход {expense_id} отклонён.", True),
        status_code=200,
    )
