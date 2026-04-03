"""Заявки на расход по ТЗ: /expenses."""

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from application.expense_service import (
    assert_attachment_upload_allowed,
    calc_equivalent,
    reimbursable_requires_receipt_before_close,
    validate_submit_fields,
)
from infrastructure.config import get_settings
from infrastructure.database import get_session
from infrastructure.expense_submit_mail import notify_expense_submitted
from infrastructure.auth_users import fetch_users_by_ids
from infrastructure.file_storage import save_attachment
from infrastructure.models import ExpenseRequestModel
from infrastructure.repositories import ExpenseRepository, _MISSING, next_kl_id
from presentation.deps import (
    check_moderate_role,
    check_view_role,
    created_by_filter_for_user,
    ensure_not_moderating_own_expense,
    get_current_user,
    is_admin_editor,
)
from presentation.schemas import (
    AttachmentOut,
    AuditLogOut,
    ExpenseAuthorSnippet,
    ExpenseCreateBody,
    ExpenseListResponse,
    ExpenseRequestDetailOut,
    ExpenseRequestListItemOut,
    ExpenseUpdateBody,
    RejectBody,
    ReviseBody,
    StatusHistoryOut,
)

router = APIRouter(prefix="/expenses", tags=["expenses"])

_log = logging.getLogger(__name__)

_ALLOWED_ATTACHMENT_KINDS = frozenset({"payment_document", "payment_receipt"})


async def _submit_expense_notify_task(
    expense_id: str,
    description: str | None,
    amount_uzs: Decimal | None,
    expense_date: date | datetime | None,
    expense_type: str | None,
    is_reimbursable: bool,
    author_email: str | None,
    author_name: str | None,
) -> None:
    try:
        settings = get_settings()
        await notify_expense_submitted(
            settings,
            expense_id=expense_id,
            description=description,
            amount_uzs=amount_uzs,
            expense_date=expense_date,
            expense_type=expense_type,
            is_reimbursable=is_reimbursable,
            author_email=author_email,
            author_name=author_name,
        )
    except Exception:
        _log.exception("expense submit notification mail failed expense_id=%s", expense_id)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _str_val(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return str(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _can_author_edit(row: ExpenseRequestModel, user_id: int) -> bool:
    return row.created_by_user_id == user_id and row.status in ("draft", "revision_required")


def _ensure_access(row: ExpenseRequestModel, user: dict) -> None:
    uid_filter = created_by_filter_for_user(user)
    if uid_filter is not None and row.created_by_user_id != uid_filter:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")


def _ensure_can_edit(row: ExpenseRequestModel, user: dict) -> None:
    uid = int(user["id"])
    if is_admin_editor(user):
        return
    if not _can_author_edit(row, uid):
        raise HTTPException(
            status_code=400,
            detail="Редактирование доступно только в статусах draft и revision_required",
        )


def _typed_attachment_flags(row: ExpenseRequestModel) -> tuple[bool, bool]:
    docs = row.attachments or []
    pd = any((a.attachment_kind or "").strip() == "payment_document" for a in docs)
    pr = any((a.attachment_kind or "").strip() == "payment_receipt" for a in docs)
    return pd, pr


def _list_item(row: ExpenseRequestModel, author: dict | None = None) -> ExpenseRequestListItemOut:
    n = len(row.attachments or [])
    pd_upl, pr_upl = _typed_attachment_flags(row)
    a = author or {}
    created_by = ExpenseAuthorSnippet(
        id=row.created_by_user_id,
        display_name=a.get("display_name"),
        email=a.get("email"),
        picture=a.get("picture"),
        position=a.get("position"),
    )
    return ExpenseRequestListItemOut(
        id=row.id,
        description=row.description,
        expense_date=row.expense_date,
        payment_deadline=row.payment_deadline,
        amount_uzs=row.amount_uzs,
        exchange_rate=row.exchange_rate,
        equivalent_amount=row.equivalent_amount,
        expense_type=row.expense_type,
        expense_subtype=row.expense_subtype,
        is_reimbursable=row.is_reimbursable,
        payment_method=row.payment_method,
        department_id=row.department_id,
        project_id=row.project_id,
        vendor=row.vendor,
        business_purpose=row.business_purpose,
        comment=row.comment,
        status=row.status,
        current_approver_id=row.current_approver_id,
        created_by_user_id=row.created_by_user_id,
        created_by=created_by,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        submitted_at=row.submitted_at,
        approved_at=row.approved_at,
        rejected_at=row.rejected_at,
        paid_at=row.paid_at,
        closed_at=row.closed_at,
        withdrawn_at=row.withdrawn_at,
        attachments_count=n,
        payment_document_uploaded=pd_upl,
        payment_receipt_uploaded=pr_upl,
    )


def _detail(row: ExpenseRequestModel, author: dict | None = None) -> ExpenseRequestDetailOut:
    li = _list_item(row, author)
    sh = sorted(row.status_history or [], key=lambda x: x.changed_at)
    al = sorted(row.audit_logs or [], key=lambda x: x.performed_at)
    atts = row.attachments or []
    return ExpenseRequestDetailOut(
        **li.model_dump(),
        attachments=[
            AttachmentOut(
                id=a.id,
                expense_request_id=a.expense_request_id,
                file_name=a.file_name,
                storage_key=a.storage_key,
                mime_type=a.mime_type,
                size_bytes=a.size_bytes,
                attachment_kind=a.attachment_kind,
                uploaded_by_user_id=a.uploaded_by_user_id,
                uploaded_at=a.uploaded_at,
            )
            for a in atts
        ],
        status_history=[
            StatusHistoryOut(
                id=h.id,
                expense_request_id=h.expense_request_id,
                from_status=h.from_status,
                to_status=h.to_status,
                changed_by_user_id=h.changed_by_user_id,
                comment=h.comment,
                changed_at=h.changed_at,
            )
            for h in sh
        ],
        audit_logs=[
            AuditLogOut(
                id=log.id,
                expense_request_id=log.expense_request_id,
                action=log.action,
                field_name=log.field_name,
                old_value=log.old_value,
                new_value=log.new_value,
                performed_by_user_id=log.performed_by_user_id,
                performed_at=log.performed_at,
            )
            for log in al
        ],
    )


async def _detail_response(row: ExpenseRequestModel, authorization: Optional[str]) -> ExpenseRequestDetailOut:
    settings = get_settings()
    m = await fetch_users_by_ids(settings.auth_service_url, authorization, {row.created_by_user_id})
    return _detail(row, m.get(row.created_by_user_id))


async def _list_with_authors(
    rows: list[ExpenseRequestModel],
    total: int,
    skip: int,
    limit: int,
    authorization: Optional[str],
) -> ExpenseListResponse:
    settings = get_settings()
    ids = {r.created_by_user_id for r in rows}
    m = await fetch_users_by_ids(settings.auth_service_url, authorization, ids)
    return ExpenseListResponse(
        items=[_list_item(r, m.get(r.created_by_user_id)) for r in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


async def _audit_diff(
    repo: ExpenseRepository,
    row: ExpenseRequestModel,
    before: dict[str, Any],
    after: dict[str, Any],
    user_id: int,
) -> None:
    for key in after:
        if key not in before:
            continue
        o, n = before[key], after[key]
        if _str_val(o) != _str_val(n):
            await repo.add_audit(
                expense_request_id=row.id,
                action="field_updated",
                field_name=key,
                old_value=_str_val(o),
                new_value=_str_val(n),
                performed_by_user_id=user_id,
            )


@router.get("", response_model=ExpenseListResponse)
async def list_expenses(
    status: Optional[str] = Query(None),
    scope: Optional[Literal["registry"]] = Query(
        None,
        description="registry — только approved, paid, closed (ТЗ §10)",
    ),
    expense_type: Optional[str] = Query(None, alias="expenseType"),
    is_reimbursable: Optional[bool] = Query(None, alias="isReimbursable"),
    date_from: Optional[date] = Query(None, alias="dateFrom"),
    date_to: Optional[date] = Query(None, alias="dateTo"),
    department_id: Optional[str] = Query(None, alias="departmentId"),
    project_id: Optional[str] = Query(None, alias="projectId"),
    employee_user_id: Optional[int] = Query(None, alias="employeeUserId"),
    q: Optional[str] = Query(None, description="Поиск по id, описанию, контрагенту"),
    sort_by: str = Query("createdAt", alias="sortBy", pattern="^(createdAt|expenseDate|updatedAt|amountUzs|status)$"),
    sort_order: str = Query("desc", alias="sortOrder", pattern="^(asc|desc)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    uid_filter = created_by_filter_for_user(user)
    if uid_filter is not None:
        eff_creator = uid_filter
    else:
        eff_creator = employee_user_id
    repo = ExpenseRepository(session)
    rows, total = await repo.list_requests(
        created_by_user_id=eff_creator,
        status=status,
        scope=scope,
        expense_type=expense_type,
        is_reimbursable=is_reimbursable,
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        project_id=project_id,
        search=q,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=skip,
        limit=limit,
    )
    return await _list_with_authors(rows, total, skip, limit, authorization)


@router.post("", response_model=ExpenseRequestDetailOut)
async def create_expense(
    body: ExpenseCreateBody,
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    settings = get_settings()
    amount_uzs = body.amount_uzs
    exchange_rate = body.exchange_rate
    eq = calc_equivalent(amount_uzs, exchange_rate)
    exp_d = body.expense_date
    rid = await next_kl_id(session)
    uid = int(user["id"])
    repo = ExpenseRepository(session)
    row = await repo.create(
        id_=rid,
        description=body.description or "",
        expense_date=exp_d,
        payment_deadline=body.payment_deadline,
        amount_uzs=amount_uzs,
        exchange_rate=exchange_rate,
        equivalent_amount=eq,
        expense_type=body.expense_type,
        expense_subtype=body.expense_subtype,
        is_reimbursable=body.is_reimbursable,
        payment_method=body.payment_method,
        department_id=body.department_id,
        project_id=body.project_id,
        vendor=body.vendor,
        business_purpose=body.business_purpose,
        comment=body.comment,
        status="draft",
        created_by_user_id=uid,
        updated_by_user_id=uid,
    )
    await repo.add_audit(
        expense_request_id=row.id,
        action="created",
        field_name=None,
        old_value=None,
        new_value=None,
        performed_by_user_id=uid,
    )
    await session.commit()
    row = await repo.get_by_id(row.id, load_children=True)
    return await _detail_response(row, authorization)


@router.get("/{expense_id}", response_model=ExpenseRequestDetailOut)
async def get_expense(
    expense_id: str,
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    _ensure_access(row, user)
    return await _detail_response(row, authorization)


@router.put("/{expense_id}", response_model=ExpenseRequestDetailOut)
async def update_expense(
    expense_id: str,
    body: ExpenseUpdateBody,
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    _ensure_access(row, user)
    _ensure_can_edit(row, user)

    before = {
        "description": row.description,
        "expense_date": row.expense_date,
        "payment_deadline": row.payment_deadline,
        "amount_uzs": row.amount_uzs,
        "exchange_rate": row.exchange_rate,
        "equivalent_amount": row.equivalent_amount,
        "expense_type": row.expense_type,
        "expense_subtype": row.expense_subtype,
        "is_reimbursable": row.is_reimbursable,
        "payment_method": row.payment_method,
        "department_id": row.department_id,
        "project_id": row.project_id,
        "vendor": row.vendor,
        "business_purpose": row.business_purpose,
        "comment": row.comment,
        "current_approver_id": row.current_approver_id,
    }
    data = body.model_dump(exclude_unset=True)
    amount_uzs = data.get("amount_uzs", row.amount_uzs)
    exchange_rate = data.get("exchange_rate", row.exchange_rate)
    if isinstance(amount_uzs, Decimal) and amount_uzs <= 0:
        raise HTTPException(status_code=400, detail="amountUzs must be greater than 0")
    if isinstance(exchange_rate, Decimal) and exchange_rate <= 0:
        raise HTTPException(status_code=400, detail="exchangeRate must be greater than 0")
    if not isinstance(amount_uzs, Decimal):
        amount_uzs = row.amount_uzs
    if not isinstance(exchange_rate, Decimal):
        exchange_rate = row.exchange_rate
    eq = calc_equivalent(amount_uzs, exchange_rate)

    exp_d = row.expense_date
    if "expense_date" in data:
        exp_d = data["expense_date"]
    pd_new = row.payment_deadline
    if "payment_deadline" in data:
        pd_new = data["payment_deadline"]
    if pd_new is not None and exp_d is not None and pd_new < exp_d:
        raise HTTPException(
            status_code=400,
            detail="Конечный срок оплаты не может быть раньше даты расхода",
        )

    payment_deadline_arg: date | object = _MISSING
    if "payment_deadline" in data:
        payment_deadline_arg = data["payment_deadline"]

    await repo.update_fields(
        row,
        description=data.get("description"),
        expense_date=data.get("expense_date"),
        payment_deadline=payment_deadline_arg,
        amount_uzs=data.get("amount_uzs"),
        exchange_rate=data.get("exchange_rate"),
        equivalent_amount=eq,
        expense_type=data.get("expense_type"),
        expense_subtype=data.get("expense_subtype"),
        is_reimbursable=data.get("is_reimbursable"),
        payment_method=data.get("payment_method"),
        department_id=data.get("department_id"),
        project_id=data.get("project_id"),
        vendor=data.get("vendor"),
        business_purpose=data.get("business_purpose"),
        comment=data.get("comment"),
        current_approver_id=data.get("current_approver_id"),
        updated_by_user_id=int(user["id"]),
    )
    await session.flush()
    after = {
        "description": row.description,
        "expense_date": row.expense_date,
        "payment_deadline": row.payment_deadline,
        "amount_uzs": row.amount_uzs,
        "exchange_rate": row.exchange_rate,
        "equivalent_amount": row.equivalent_amount,
        "expense_type": row.expense_type,
        "expense_subtype": row.expense_subtype,
        "is_reimbursable": row.is_reimbursable,
        "payment_method": row.payment_method,
        "department_id": row.department_id,
        "project_id": row.project_id,
        "vendor": row.vendor,
        "business_purpose": row.business_purpose,
        "comment": row.comment,
        "current_approver_id": row.current_approver_id,
    }
    await _audit_diff(repo, row, before, after, int(user["id"]))
    await session.commit()
    row = await repo.get_by_id(expense_id, load_children=True)
    return await _detail_response(row, authorization)


@router.post("/{expense_id}/submit", response_model=ExpenseRequestDetailOut)
async def submit_expense(
    expense_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    settings = get_settings()
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if row.created_by_user_id != int(user["id"]):
        raise HTTPException(status_code=403, detail="Отправить может только автор")
    if row.status not in ("draft", "revision_required"):
        raise HTTPException(status_code=400, detail="Отправка только из draft или revision_required")
    n_att = await repo.count_attachments(row.id)
    pd_count, pr_count, _un = await repo.attachment_kind_metrics(row.id)
    limit = settings.expense_amount_limit_uzs
    try:
        validate_submit_fields(
            description=row.description,
            expense_date=row.expense_date,
            payment_deadline=row.payment_deadline,
            amount_uzs=row.amount_uzs,
            exchange_rate=row.exchange_rate,
            expense_type=row.expense_type,
            is_reimbursable=row.is_reimbursable,
            comment=row.comment,
            attachment_count=n_att,
            expense_amount_limit_uzs=limit,
            payment_document_count=pd_count,
            payment_receipt_count=pr_count,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    prev = row.status
    row.status = "pending_approval"
    row.submitted_at = row.submitted_at or _utc_now()
    row.updated_by_user_id = int(user["id"])
    row.updated_at = _utc_now()
    await repo.add_status_history(
        expense_request_id=row.id,
        from_status=prev,
        to_status="pending_approval",
        changed_by_user_id=int(user["id"]),
        comment=None,
    )
    await repo.add_audit(
        expense_request_id=row.id,
        action="submitted",
        field_name="status",
        old_value=prev,
        new_value="pending_approval",
        performed_by_user_id=int(user["id"]),
    )
    await session.commit()
    row = await repo.get_by_id(expense_id, load_children=True)
    background_tasks.add_task(
        _submit_expense_notify_task,
        row.id,
        row.description,
        row.amount_uzs,
        row.expense_date,
        row.expense_type,
        row.is_reimbursable,
        user.get("email"),
        user.get("display_name"),
    )
    return await _detail_response(row, authorization)


@router.post("/{expense_id}/approve", response_model=ExpenseRequestDetailOut)
async def approve_expense(
    expense_id: str,
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_moderate_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    _ensure_access(row, user)
    if row.status == "approved":
        return await _detail_response(row, authorization)
    if row.status != "pending_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Одобрение недоступно для статуса «{row.status}»",
        )
    ensure_not_moderating_own_expense(user, row.created_by_user_id)
    prev = row.status
    row.status = "approved"
    row.approved_at = _utc_now()
    row.updated_by_user_id = int(user["id"])
    row.updated_at = _utc_now()
    await repo.add_status_history(
        expense_request_id=row.id,
        from_status=prev,
        to_status="approved",
        changed_by_user_id=int(user["id"]),
        comment=None,
    )
    await repo.add_audit(
        expense_request_id=row.id,
        action="approved",
        field_name="status",
        old_value=prev,
        new_value="approved",
        performed_by_user_id=int(user["id"]),
    )
    await session.commit()
    row = await repo.get_by_id(expense_id, load_children=True)
    return await _detail_response(row, authorization)


@router.post("/{expense_id}/reject", response_model=ExpenseRequestDetailOut)
async def reject_expense(
    expense_id: str,
    body: RejectBody,
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_moderate_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    _ensure_access(row, user)
    if row.status == "rejected":
        return await _detail_response(row, authorization)
    if row.status != "pending_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Отклонение недоступно для статуса «{row.status}»",
        )
    ensure_not_moderating_own_expense(user, row.created_by_user_id)
    prev = row.status
    row.status = "rejected"
    row.rejected_at = _utc_now()
    row.updated_by_user_id = int(user["id"])
    row.updated_at = _utc_now()
    reason = body.reason.strip()
    await repo.add_status_history(
        expense_request_id=row.id,
        from_status=prev,
        to_status="rejected",
        changed_by_user_id=int(user["id"]),
        comment=reason,
    )
    await repo.add_audit(
        expense_request_id=row.id,
        action="rejected",
        field_name="status",
        old_value=prev,
        new_value=f"rejected: {reason}",
        performed_by_user_id=int(user["id"]),
    )
    await session.commit()
    row = await repo.get_by_id(expense_id, load_children=True)
    return await _detail_response(row, authorization)


@router.post("/{expense_id}/revise", response_model=ExpenseRequestDetailOut)
async def revise_expense(
    expense_id: str,
    body: ReviseBody,
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_moderate_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    _ensure_access(row, user)
    if row.status != "pending_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Возврат на доработку недоступен для статуса «{row.status}»",
        )
    ensure_not_moderating_own_expense(user, row.created_by_user_id)
    prev = row.status
    row.status = "revision_required"
    row.updated_by_user_id = int(user["id"])
    row.updated_at = _utc_now()
    c = body.comment.strip()
    await repo.add_status_history(
        expense_request_id=row.id,
        from_status=prev,
        to_status="revision_required",
        changed_by_user_id=int(user["id"]),
        comment=c,
    )
    await repo.add_audit(
        expense_request_id=row.id,
        action="revision_required",
        field_name="status",
        old_value=prev,
        new_value="revision_required",
        performed_by_user_id=int(user["id"]),
    )
    await session.commit()
    row = await repo.get_by_id(expense_id, load_children=True)
    return await _detail_response(row, authorization)


@router.post("/{expense_id}/pay", response_model=ExpenseRequestDetailOut)
async def pay_expense(
    expense_id: str,
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_moderate_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    _ensure_access(row, user)
    if row.status != "approved":
        raise HTTPException(status_code=400, detail="Выплата только для approved")
    if not row.is_reimbursable:
        raise HTTPException(status_code=400, detail="Выплата только для возмещаемых расходов")
    ensure_not_moderating_own_expense(user, row.created_by_user_id)
    prev = row.status
    row.status = "paid"
    row.paid_at = _utc_now()
    row.updated_by_user_id = int(user["id"])
    row.updated_at = _utc_now()
    await repo.add_status_history(
        expense_request_id=row.id,
        from_status=prev,
        to_status="paid",
        changed_by_user_id=int(user["id"]),
        comment=None,
    )
    await repo.add_audit(
        expense_request_id=row.id,
        action="paid",
        field_name="status",
        old_value=prev,
        new_value="paid",
        performed_by_user_id=int(user["id"]),
    )
    await session.commit()
    row = await repo.get_by_id(expense_id, load_children=True)
    return await _detail_response(row, authorization)


@router.post("/{expense_id}/close", response_model=ExpenseRequestDetailOut)
async def close_expense(
    expense_id: str,
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_moderate_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    _ensure_access(row, user)
    ensure_not_moderating_own_expense(user, row.created_by_user_id)
    prev = row.status
    if row.status == "paid":
        new_status = "closed"
    elif row.status == "not_reimbursable":
        new_status = "closed"
    elif row.status == "approved" and not row.is_reimbursable:
        new_status = "not_reimbursable"
    else:
        raise HTTPException(
            status_code=400,
            detail="Закрытие: из paid, not_reimbursable или approved (невозмещаемый) → not_reimbursable",
        )
    if prev == "paid" and new_status == "closed" and row.is_reimbursable:
        _, pr_count, _ = await repo.attachment_kind_metrics(row.id)
        try:
            reimbursable_requires_receipt_before_close(pr_count)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    row.status = new_status
    if new_status == "closed":
        row.closed_at = _utc_now()
    row.updated_by_user_id = int(user["id"])
    row.updated_at = _utc_now()
    await repo.add_status_history(
        expense_request_id=row.id,
        from_status=prev,
        to_status=new_status,
        changed_by_user_id=int(user["id"]),
        comment=None,
    )
    await repo.add_audit(
        expense_request_id=row.id,
        action="close" if new_status == "closed" else "mark_not_reimbursable",
        field_name="status",
        old_value=prev,
        new_value=new_status,
        performed_by_user_id=int(user["id"]),
    )
    await session.commit()
    row = await repo.get_by_id(expense_id, load_children=True)
    return await _detail_response(row, authorization)


@router.post("/{expense_id}/withdraw", response_model=ExpenseRequestDetailOut)
async def withdraw_expense(
    expense_id: str,
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if row.created_by_user_id != int(user["id"]):
        raise HTTPException(status_code=403, detail="Отозвать может только автор")
    if row.status in ("paid", "closed", "rejected", "withdrawn"):
        raise HTTPException(status_code=400, detail="Заявка уже завершена или отозвана")
    prev = row.status
    row.status = "withdrawn"
    row.withdrawn_at = _utc_now()
    row.updated_by_user_id = int(user["id"])
    row.updated_at = _utc_now()
    await repo.add_status_history(
        expense_request_id=row.id,
        from_status=prev,
        to_status="withdrawn",
        changed_by_user_id=int(user["id"]),
        comment=None,
    )
    await repo.add_audit(
        expense_request_id=row.id,
        action="withdrawn",
        field_name="status",
        old_value=prev,
        new_value="withdrawn",
        performed_by_user_id=int(user["id"]),
    )
    await session.commit()
    row = await repo.get_by_id(expense_id, load_children=True)
    return await _detail_response(row, authorization)


@router.get("/{expense_id}/attachments", response_model=list[AttachmentOut])
async def list_attachments(
    expense_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    _ensure_access(row, user)
    return [
        AttachmentOut(
            id=a.id,
            expense_request_id=a.expense_request_id,
            file_name=a.file_name,
            storage_key=a.storage_key,
            mime_type=a.mime_type,
            size_bytes=a.size_bytes,
            attachment_kind=a.attachment_kind,
            uploaded_by_user_id=a.uploaded_by_user_id,
            uploaded_at=a.uploaded_at,
        )
        for a in (row.attachments or [])
    ]


@router.post("/{expense_id}/attachments", response_model=ExpenseRequestDetailOut)
async def upload_attachment(
    expense_id: str,
    file: UploadFile = File(...),
    attachment_kind: Optional[str] = Form(None, alias="attachmentKind"),
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    _ensure_access(row, user)
    kind_norm: str | None = None
    if attachment_kind is not None and str(attachment_kind).strip():
        k = str(attachment_kind).strip()
        if k not in _ALLOWED_ATTACHMENT_KINDS:
            raise HTTPException(status_code=400, detail="Недопустимый тип вложения")
        kind_norm = k

    if not is_admin_editor(user):
        if row.created_by_user_id != int(user["id"]):
            raise HTTPException(status_code=403, detail="Только автор может добавлять вложения")
        try:
            assert_attachment_upload_allowed(
                status=row.status,
                attachment_kind=kind_norm,
                is_admin=False,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    content = await file.read()
    try:
        storage_key, safe_name = save_attachment(row.id, file.filename or "file", content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    att_id = str(uuid.uuid4())
    await repo.add_attachment(
        attachment_id=att_id,
        expense_request_id=row.id,
        file_name=file.filename or safe_name,
        storage_key=storage_key,
        mime_type=file.content_type,
        size_bytes=len(content),
        uploaded_by_user_id=int(user["id"]),
        attachment_kind=kind_norm,
    )
    await repo.add_audit(
        expense_request_id=row.id,
        action="attachment_added",
        field_name="attachment",
        old_value=None,
        new_value=att_id,
        performed_by_user_id=int(user["id"]),
    )
    await session.commit()
    row = await repo.get_by_id(expense_id, load_children=True)
    return await _detail_response(row, authorization)


@router.delete("/{expense_id}/attachments/{attachment_id}", response_model=ExpenseRequestDetailOut)
async def delete_attachment(
    expense_id: str,
    attachment_id: str,
    user: dict = Depends(get_current_user),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    settings = get_settings()
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(expense_id, load_children=True)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    _ensure_access(row, user)
    att_row = next((a for a in (row.attachments or []) if a.id == attachment_id), None)
    if not att_row:
        raise HTTPException(status_code=404, detail="Вложение не найдено")
    if not is_admin_editor(user):
        if row.created_by_user_id != int(user["id"]):
            raise HTTPException(status_code=403, detail="Только автор может удалять вложения")
        kind = (att_row.attachment_kind or "").strip()
        if row.status in ("draft", "revision_required"):
            pass
        elif row.status in ("paid", "closed"):
            if kind != "payment_receipt":
                raise HTTPException(
                    status_code=400,
                    detail="В этом статусе можно удалить только квитанцию (payment_receipt), чтобы заменить файл",
                )
        elif row.status in ("pending_approval", "approved"):
            if kind == "payment_receipt":
                raise HTTPException(
                    status_code=400,
                    detail="Квитанцию можно удалить только после подтверждения выплаты",
                )
        else:
            raise HTTPException(status_code=400, detail="Удаление вложений в этом статусе недоступно")
    storage_key = att_row.storage_key
    ok = await repo.delete_attachment(expense_id, attachment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Вложение не найдено")
    p = Path(settings.media_path) / storage_key
    try:
        if p.is_file():
            p.unlink()
    except OSError:
        pass
    await repo.add_audit(
        expense_request_id=row.id,
        action="attachment_deleted",
        field_name="attachment",
        old_value=attachment_id,
        new_value=None,
        performed_by_user_id=int(user["id"]),
    )
    await session.commit()
    row = await repo.get_by_id(expense_id, load_children=True)
    return await _detail_response(row, authorization)
