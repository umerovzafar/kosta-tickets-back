"""Доступ к данным счетов."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from infrastructure.models_invoices import (
    InvoiceAuditLogModel,
    InvoiceCounterModel,
    InvoiceLineItemModel,
    InvoiceModel,
    InvoicePaymentModel,
)
from infrastructure.repository_shared import _now_utc


class InvoiceRepository:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def allocate_next_seq(self, year: int) -> int:
        row = await self._s.get(InvoiceCounterModel, year)
        now = _now_utc()
        if row is None:
            row = InvoiceCounterModel(year=year, last_seq=1)
            self._s.add(row)
            await self._s.flush()
            return 1
        row.last_seq = int(row.last_seq or 0) + 1
        await self._s.flush()
        return row.last_seq

    async def get(self, invoice_id: str) -> InvoiceModel | None:
        q = select(InvoiceModel).where(InvoiceModel.id == invoice_id)
        return (await self._s.execute(q)).scalar_one_or_none()

    async def get_with_children(self, invoice_id: str) -> InvoiceModel | None:
        q = (
            select(InvoiceModel)
            .where(InvoiceModel.id == invoice_id)
            .options(
                selectinload(InvoiceModel.line_items),
                selectinload(InvoiceModel.payments),
                selectinload(InvoiceModel.audit_logs),
            )
        )
        return (await self._s.execute(q)).scalar_one_or_none()

    async def list_invoices(
        self,
        *,
        client_id: str | None = None,
        project_id: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[InvoiceModel]:
        q = select(InvoiceModel).order_by(InvoiceModel.issue_date.desc(), InvoiceModel.invoice_number.desc())
        if client_id:
            q = q.where(InvoiceModel.client_id == client_id)
        if project_id:
            q = q.where(InvoiceModel.project_id == project_id)
        if status:
            if status == "overdue":
                today = date.today()
                q = q.where(
                    and_(
                        InvoiceModel.status.in_(("sent", "viewed", "partial_paid")),
                        InvoiceModel.due_date < today,
                        InvoiceModel.amount_paid < InvoiceModel.total_amount,
                    )
                )
            else:
                q = q.where(InvoiceModel.status == status)
        if date_from:
            q = q.where(InvoiceModel.issue_date >= date_from)
        if date_to:
            q = q.where(InvoiceModel.issue_date <= date_to)
        q = q.limit(min(limit, 500)).offset(offset)
        return list((await self._s.execute(q)).scalars().all())

    async def time_entry_on_active_invoice(
        self, time_entry_id: str, exclude_invoice_id: str | None = None
    ) -> str | None:
        """Возвращает id счёта, если запись уже привязана к неотменённому счёту."""
        cond = [
            InvoiceLineItemModel.time_entry_id == time_entry_id,
            InvoiceModel.status != "canceled",
            InvoiceLineItemModel.time_entry_id.is_not(None),
        ]
        if exclude_invoice_id:
            cond.append(InvoiceModel.id != exclude_invoice_id)
        q = (
            select(InvoiceModel.id)
            .select_from(InvoiceLineItemModel)
            .join(InvoiceModel, InvoiceModel.id == InvoiceLineItemModel.invoice_id)
            .where(and_(*cond))
            .limit(1)
        )
        r = (await self._s.execute(q)).scalar_one_or_none()
        return str(r) if r else None

    async def expense_on_active_invoice(
        self, expense_request_id: str, exclude_invoice_id: str | None = None
    ) -> str | None:
        cond = [
            InvoiceLineItemModel.expense_request_id == expense_request_id,
            InvoiceModel.status != "canceled",
            InvoiceLineItemModel.expense_request_id.is_not(None),
        ]
        if exclude_invoice_id:
            cond.append(InvoiceModel.id != exclude_invoice_id)
        q = (
            select(InvoiceModel.id)
            .select_from(InvoiceLineItemModel)
            .join(InvoiceModel, InvoiceModel.id == InvoiceLineItemModel.invoice_id)
            .where(and_(*cond))
            .limit(1)
        )
        r = (await self._s.execute(q)).scalar_one_or_none()
        return str(r) if r else None

    async def invoiced_time_entry_ids(self, time_entry_ids: list[str]) -> set[str]:
        if not time_entry_ids:
            return set()
        q = (
            select(InvoiceLineItemModel.time_entry_id)
            .join(InvoiceModel, InvoiceModel.id == InvoiceLineItemModel.invoice_id)
            .where(
                and_(
                    InvoiceLineItemModel.time_entry_id.in_(time_entry_ids),
                    InvoiceModel.status != "canceled",
                )
            )
        )
        rows = (await self._s.execute(q)).all()
        return {str(r[0]) for r in rows if r[0]}

    async def invoiced_expense_ids(self, expense_ids: list[str]) -> set[str]:
        if not expense_ids:
            return set()
        q = (
            select(InvoiceLineItemModel.expense_request_id)
            .join(InvoiceModel, InvoiceModel.id == InvoiceLineItemModel.invoice_id)
            .where(
                and_(
                    InvoiceLineItemModel.expense_request_id.in_(expense_ids),
                    InvoiceModel.status != "canceled",
                )
            )
        )
        rows = (await self._s.execute(q)).all()
        return {str(r[0]) for r in rows if r[0]}

    def add(self, inv: InvoiceModel) -> None:
        self._s.add(inv)

    def add_line(self, line: InvoiceLineItemModel) -> None:
        self._s.add(line)

    async def delete_lines(self, invoice_id: str) -> None:
        await self._s.execute(
            InvoiceLineItemModel.__table__.delete().where(InvoiceLineItemModel.invoice_id == invoice_id)
        )

    async def add_payment(self, p: InvoicePaymentModel) -> None:
        self._s.add(p)

    async def add_audit(self, log: InvoiceAuditLogModel) -> None:
        self._s.add(log)

    async def sum_payments(self, invoice_id: str) -> Decimal:
        q = select(func.coalesce(func.sum(InvoicePaymentModel.amount), 0)).where(
            InvoicePaymentModel.invoice_id == invoice_id
        )
        v = (await self._s.execute(q)).scalar_one()
        return Decimal(str(v)) if v is not None else Decimal(0)
