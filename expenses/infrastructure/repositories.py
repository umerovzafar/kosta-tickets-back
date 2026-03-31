from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from infrastructure.models import ExpenseAttachmentModel, ExpenseRequestModel, ExpenseSequenceModel


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def next_public_id(session: AsyncSession) -> str:
    y = date.today().year
    row = await session.execute(
        select(ExpenseSequenceModel).where(ExpenseSequenceModel.year == y).with_for_update()
    )
    seq_row = row.scalars().one_or_none()
    if not seq_row:
        seq_row = ExpenseSequenceModel(year=y, last_seq=0)
        session.add(seq_row)
        await session.flush()
    seq_row.last_seq += 1
    await session.flush()
    return f"REQ-{y}-{seq_row.last_seq:05d}"


class ExpenseRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        *,
        public_id: str,
        status: str,
        request_date: date,
        created_by_user_id: int,
        initiator_name: str,
        department: str | None,
        budget_category: str | None,
        counterparty: str | None,
        amount: Decimal,
        currency: str,
        expense_date: date,
        description: str | None,
        reimbursement_type: str,
    ) -> ExpenseRequestModel:
        now = _now_utc()
        row = ExpenseRequestModel(
            public_id=public_id,
            status=status,
            request_date=request_date,
            created_by_user_id=created_by_user_id,
            initiator_name=initiator_name,
            department=department,
            budget_category=budget_category,
            counterparty=counterparty,
            amount=amount,
            currency=currency,
            expense_date=expense_date,
            description=description,
            reimbursement_type=reimbursement_type,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_id(self, id_: int) -> ExpenseRequestModel | None:
        q = (
            select(ExpenseRequestModel)
            .where(ExpenseRequestModel.id == id_)
            .options(selectinload(ExpenseRequestModel.attachments))
        )
        r = await self._session.execute(q)
        return r.scalars().one_or_none()

    async def list_requests(
        self,
        *,
        created_by_user_id: int | None,
        status: str | None,
        budget_category: str | None,
        date_from: date | None,
        date_to: date | None,
        skip: int,
        limit: int,
    ) -> tuple[list[ExpenseRequestModel], int]:
        q = select(ExpenseRequestModel)
        cnt = select(func.count()).select_from(ExpenseRequestModel)
        if created_by_user_id is not None:
            q = q.where(ExpenseRequestModel.created_by_user_id == created_by_user_id)
            cnt = cnt.where(ExpenseRequestModel.created_by_user_id == created_by_user_id)
        if status:
            q = q.where(ExpenseRequestModel.status == status)
            cnt = cnt.where(ExpenseRequestModel.status == status)
        if budget_category:
            q = q.where(ExpenseRequestModel.budget_category == budget_category)
            cnt = cnt.where(ExpenseRequestModel.budget_category == budget_category)
        if date_from:
            q = q.where(ExpenseRequestModel.expense_date >= date_from)
            cnt = cnt.where(ExpenseRequestModel.expense_date >= date_from)
        if date_to:
            q = q.where(ExpenseRequestModel.expense_date <= date_to)
            cnt = cnt.where(ExpenseRequestModel.expense_date <= date_to)
        q = q.order_by(ExpenseRequestModel.created_at.desc()).offset(skip).limit(limit)
        q = q.options(selectinload(ExpenseRequestModel.attachments))
        rows = await self._session.execute(q)
        total_r = await self._session.execute(cnt)
        return list(rows.scalars().all()), int(total_r.scalar() or 0)

    async def update_draft(
        self,
        row: ExpenseRequestModel,
        *,
        request_date: date | None,
        department: str | None,
        budget_category: str | None,
        counterparty: str | None,
        amount: Decimal | None,
        currency: str | None,
        expense_date: date | None,
        description: str | None,
        reimbursement_type: str | None,
    ) -> None:
        if request_date is not None:
            row.request_date = request_date
        if department is not None:
            row.department = department
        if budget_category is not None:
            row.budget_category = budget_category
        if counterparty is not None:
            row.counterparty = counterparty
        if amount is not None:
            row.amount = amount
        if currency is not None:
            row.currency = currency
        if expense_date is not None:
            row.expense_date = expense_date
        if description is not None:
            row.description = description
        if reimbursement_type is not None:
            row.reimbursement_type = reimbursement_type
        row.updated_at = _now_utc()
        self._session.add(row)

    async def set_status(
        self,
        row: ExpenseRequestModel,
        *,
        status: str,
        rejection_reason: str | None,
        reviewed_by_user_id: int,
    ) -> None:
        row.status = status
        row.rejection_reason = rejection_reason if status == "rejected" else None
        row.reviewed_at = _now_utc()
        row.reviewed_by_user_id = reviewed_by_user_id
        row.updated_at = _now_utc()
        self._session.add(row)

    async def submit_draft(self, row: ExpenseRequestModel) -> None:
        row.status = "pending"
        row.updated_at = _now_utc()
        self._session.add(row)

    async def add_attachment(
        self,
        *,
        expense_request_id: int,
        attachment_id: str,
        file_path: str,
        kind: str,
    ) -> ExpenseAttachmentModel:
        att = ExpenseAttachmentModel(
            id=attachment_id,
            expense_request_id=expense_request_id,
            file_path=file_path,
            kind=kind,
            created_at=_now_utc(),
        )
        self._session.add(att)
        await self._session.flush()
        return att

    async def delete_attachment(self, expense_request_id: int, attachment_id: str) -> bool:
        r = await self._session.execute(
            select(ExpenseAttachmentModel).where(
                and_(
                    ExpenseAttachmentModel.id == attachment_id,
                    ExpenseAttachmentModel.expense_request_id == expense_request_id,
                )
            )
        )
        row = r.scalars().one_or_none()
        if not row:
            return False
        await self._session.delete(row)
        return True

    async def summary_stats(
        self,
        *,
        created_by_user_id: int | None,
        date_from: date,
        date_to: date,
        budget_category: str | None,
    ) -> tuple[Decimal, int, int]:
        """
        Итого: сумма по согласованным; operations_count — все заявки кроме черновиков;
        approved_count — число согласованных.
        """
        base_filters = [
            ExpenseRequestModel.expense_date >= date_from,
            ExpenseRequestModel.expense_date <= date_to,
        ]
        if created_by_user_id is not None:
            base_filters.append(ExpenseRequestModel.created_by_user_id == created_by_user_id)
        if budget_category:
            base_filters.append(ExpenseRequestModel.budget_category == budget_category)

        q_approved_sum = select(
            func.coalesce(func.sum(ExpenseRequestModel.amount), 0),
        ).where(
            and_(
                *base_filters,
                ExpenseRequestModel.status == "approved",
            )
        )
        r1 = await self._session.execute(q_approved_sum)
        total = Decimal(str(r1.scalar() or 0))

        q_ops = select(func.count()).select_from(ExpenseRequestModel).where(
            and_(
                *base_filters,
                ExpenseRequestModel.status != "draft",
            )
        )
        r2 = await self._session.execute(q_ops)
        operations_count = int(r2.scalar() or 0)

        q_appr = select(func.count()).select_from(ExpenseRequestModel).where(
            and_(
                *base_filters,
                ExpenseRequestModel.status == "approved",
            )
        )
        r3 = await self._session.execute(q_appr)
        approved_count = int(r3.scalar() or 0)
        return total, operations_count, approved_count

    async def dynamics_by_day(
        self,
        *,
        created_by_user_id: int | None,
        date_from: date,
        date_to: date,
        budget_category: str | None,
        status_filter: str,
    ) -> list[tuple[date, Decimal, int]]:
        q = (
            select(
                ExpenseRequestModel.expense_date,
                func.coalesce(func.sum(ExpenseRequestModel.amount), 0),
                func.count(ExpenseRequestModel.id),
            )
            .where(
                and_(
                    ExpenseRequestModel.expense_date >= date_from,
                    ExpenseRequestModel.expense_date <= date_to,
                )
            )
            .group_by(ExpenseRequestModel.expense_date)
            .order_by(ExpenseRequestModel.expense_date)
        )
        if created_by_user_id is not None:
            q = q.where(ExpenseRequestModel.created_by_user_id == created_by_user_id)
        if budget_category:
            q = q.where(ExpenseRequestModel.budget_category == budget_category)
        q = q.where(ExpenseRequestModel.status == status_filter)
        r = await self._session.execute(q)
        return [(row[0], Decimal(str(row[1])), int(row[2])) for row in r.all()]

    async def calendar_days(
        self,
        *,
        created_by_user_id: int | None,
        year: int,
        month: int,
    ) -> list[tuple[date, Decimal, int]]:
        from calendar import monthrange

        start = date(year, month, 1)
        _, last = monthrange(year, month)
        end = date(year, month, last)
        q = (
            select(
                ExpenseRequestModel.expense_date,
                func.coalesce(func.sum(ExpenseRequestModel.amount), 0),
                func.count(ExpenseRequestModel.id),
            )
            .where(
                and_(
                    ExpenseRequestModel.expense_date >= start,
                    ExpenseRequestModel.expense_date <= end,
                    ExpenseRequestModel.status != "draft",
                )
            )
            .group_by(ExpenseRequestModel.expense_date)
        )
        if created_by_user_id is not None:
            q = q.where(ExpenseRequestModel.created_by_user_id == created_by_user_id)
        r = await self._session.execute(q)
        return [(row[0], Decimal(str(row[1])), int(row[2])) for row in r.all()]

    async def list_by_expense_date(
        self,
        *,
        created_by_user_id: int | None,
        day: date,
    ) -> list[ExpenseRequestModel]:
        q = (
            select(ExpenseRequestModel)
            .where(ExpenseRequestModel.expense_date == day)
            .where(ExpenseRequestModel.status != "draft")
        )
        if created_by_user_id is not None:
            q = q.where(ExpenseRequestModel.created_by_user_id == created_by_user_id)
        q = q.options(selectinload(ExpenseRequestModel.attachments)).order_by(
            ExpenseRequestModel.created_at.desc()
        )
        r = await self._session.execute(q)
        return list(r.scalars().all())

    async def health_check(self) -> bool:
        try:
            await self._session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
