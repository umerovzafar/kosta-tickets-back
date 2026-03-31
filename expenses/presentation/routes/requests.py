import uuid
from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import get_session
from infrastructure.file_storage import save_attachment
from infrastructure.models import ExpenseRequestModel
from infrastructure.repositories import ExpenseRepository, next_public_id
from presentation.deps import (
    check_moderate_role,
    check_view_role,
    created_by_filter_for_user,
    get_current_user,
)
from presentation.schemas import (
    AttachmentOut,
    ExpenseListResponse,
    ExpenseRequestCreateBody,
    ExpenseRequestOut,
    ExpenseRequestPatchBody,
    ExpenseStatusBody,
)

router = APIRouter(prefix="/requests", tags=["requests"])


def _to_out(row: ExpenseRequestModel) -> ExpenseRequestOut:
    return ExpenseRequestOut(
        id=row.id,
        public_id=row.public_id,
        status=row.status,
        request_date=row.request_date,
        created_by_user_id=row.created_by_user_id,
        initiator_name=row.initiator_name,
        department=row.department,
        budget_category=row.budget_category,
        counterparty=row.counterparty,
        amount=row.amount,
        currency=row.currency,
        expense_date=row.expense_date,
        description=row.description,
        reimbursement_type=row.reimbursement_type,
        rejection_reason=row.rejection_reason,
        reviewed_at=row.reviewed_at,
        reviewed_by_user_id=row.reviewed_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        attachments=[
            AttachmentOut(id=a.id, kind=a.kind, file_path=a.file_path) for a in (row.attachments or [])
        ],
    )


@router.get("", response_model=ExpenseListResponse)
async def list_requests(
    status: Optional[str] = Query(None),
    budget_category: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    df = date_type.fromisoformat(date_from) if date_from else None
    dt = date_type.fromisoformat(date_to) if date_to else None
    uid_filter = created_by_filter_for_user(user)
    rows, total = await repo.list_requests(
        created_by_user_id=uid_filter,
        status=status,
        budget_category=budget_category,
        date_from=df,
        date_to=dt,
        skip=skip,
        limit=limit,
    )
    return ExpenseListResponse(
        items=[_to_out(r) for r in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=ExpenseRequestOut)
async def create_request(
    body: ExpenseRequestCreateBody,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    public_id = await next_public_id(session)
    name = (user.get("display_name") or user.get("email") or "").strip() or f"user-{user['id']}"
    row = await repo.create(
        public_id=public_id,
        status=body.status,
        request_date=body.request_date,
        created_by_user_id=int(user["id"]),
        initiator_name=name,
        department=body.department,
        budget_category=body.budget_category,
        counterparty=body.counterparty,
        amount=body.amount,
        currency=body.currency,
        expense_date=body.expense_date,
        description=body.description,
        reimbursement_type=body.reimbursement_type,
    )
    await session.commit()
    row = await repo.get_by_id(row.id)
    return _to_out(row)


@router.get("/{request_id}", response_model=ExpenseRequestOut)
async def get_request(
    request_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    uid_filter = created_by_filter_for_user(user)
    if uid_filter is not None and row.created_by_user_id != uid_filter:
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")
    return _to_out(row)


@router.patch("/{request_id}", response_model=ExpenseRequestOut)
async def patch_request(
    request_id: int,
    body: ExpenseRequestPatchBody,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if row.created_by_user_id != int(user["id"]):
        raise HTTPException(status_code=403, detail="Редактировать может только автор")
    if row.status != "draft":
        raise HTTPException(status_code=400, detail="Редактирование только для черновика")
    data = body.model_dump(exclude_none=True)
    if "amount" in data and data["amount"] is not None and data["amount"] <= 0:
        raise HTTPException(status_code=400, detail="Сумма должна быть больше 0")
    await repo.update_draft(
        row,
        request_date=data.get("request_date"),
        department=data.get("department"),
        budget_category=data.get("budget_category"),
        counterparty=data.get("counterparty"),
        amount=data.get("amount"),
        currency=data.get("currency"),
        expense_date=data.get("expense_date"),
        description=data.get("description"),
        reimbursement_type=data.get("reimbursement_type"),
    )
    await session.commit()
    row = await repo.get_by_id(request_id)
    return _to_out(row)


@router.post("/{request_id}/submit", response_model=ExpenseRequestOut)
async def submit_request(
    request_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if row.created_by_user_id != int(user["id"]):
        raise HTTPException(status_code=403, detail="Отправить может только автор")
    if row.status != "draft":
        raise HTTPException(status_code=400, detail="Отправка только из черновика")
    await repo.submit_draft(row)
    await session.commit()
    row = await repo.get_by_id(request_id)
    return _to_out(row)


@router.patch("/{request_id}/status", response_model=ExpenseRequestOut)
async def set_status(
    request_id: int,
    body: ExpenseStatusBody,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_moderate_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if row.status not in ("pending",):
        raise HTTPException(status_code=400, detail="Согласование только для заявок на рассмотрении")
    await repo.set_status(
        row,
        status=body.status,
        rejection_reason=body.rejection_reason.strip() if body.rejection_reason else None,
        reviewed_by_user_id=int(user["id"]),
    )
    await session.commit()
    row = await repo.get_by_id(request_id)
    return _to_out(row)


@router.post("/{request_id}/attachments", response_model=ExpenseRequestOut)
async def upload_attachment(
    request_id: int,
    kind: str = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if row.created_by_user_id != int(user["id"]):
        raise HTTPException(status_code=403, detail="Прикреплять файлы может только автор")
    if row.status not in ("draft", "pending"):
        raise HTTPException(status_code=400, detail="Файлы можно прикреплять к черновику или заявке на модерации")
    if kind not in ("document", "receipt"):
        raise HTTPException(status_code=400, detail="kind: document или receipt")
    content = await file.read()
    try:
        rel = save_attachment(request_id, file.filename or "file", content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    att_id = str(uuid.uuid4())
    await repo.add_attachment(
        expense_request_id=request_id,
        attachment_id=att_id,
        file_path=rel,
        kind=kind,
    )
    await session.commit()
    row = await repo.get_by_id(request_id)
    return _to_out(row)


@router.delete("/{request_id}/attachments/{attachment_id}", response_model=ExpenseRequestOut)
async def delete_attachment(
    request_id: int,
    attachment_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    check_view_role(user)
    repo = ExpenseRepository(session)
    row = await repo.get_by_id(request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if row.created_by_user_id != int(user["id"]):
        raise HTTPException(status_code=403, detail="Удалять файлы может только автор")
    if row.status not in ("draft", "pending"):
        raise HTTPException(status_code=400, detail="Удалять вложения можно только до завершения модерации")
    ok = await repo.delete_attachment(request_id, attachment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Вложение не найдено")
    await session.commit()
    row = await repo.get_by_id(request_id)
    return _to_out(row)
