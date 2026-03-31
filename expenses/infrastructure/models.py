"""Модели БД расходов (kosta_expenses)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database import Base


class ExpenseSequenceModel(Base):
    """Счётчик для публичных номеров REQ-YYYY-NNNNN."""

    __tablename__ = "expense_sequence"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ExpenseRequestModel(Base):
    __tablename__ = "expense_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    initiator_name: Mapped[str] = mapped_column(String(512), nullable=False)
    department: Mapped[str | None] = mapped_column(String(512), nullable=True)
    budget_category: Mapped[str | None] = mapped_column(String(512), nullable=True)
    counterparty: Mapped[str | None] = mapped_column(String(512), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="UZS")
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reimbursement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    attachments: Mapped[list["ExpenseAttachmentModel"]] = relationship(
        "ExpenseAttachmentModel",
        back_populates="request",
        cascade="all, delete-orphan",
    )


class ExpenseAttachmentModel(Base):
    __tablename__ = "expense_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    expense_request_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("expense_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    request: Mapped["ExpenseRequestModel"] = relationship("ExpenseRequestModel", back_populates="attachments")
