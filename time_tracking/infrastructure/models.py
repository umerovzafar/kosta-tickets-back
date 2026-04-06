"""Модели БД time_tracking."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database import Base


class TimeTrackingUserModel(Base):
    """Пользователь с доступом к учёту времени (копия/синхрон с auth для раздела time_tracking)."""

    __tablename__ = "time_tracking_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    auth_user_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    picture: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    weekly_capacity_hours: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("35"),
        server_default=text("35"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserHourlyRateModel(Base):
    """Почасовая ставка пользователя по умолчанию: оплачиваемая (billable) или себестоимость (cost)."""

    __tablename__ = "time_tracking_user_hourly_rates"
    __table_args__ = (
        Index("ix_tt_hourly_rates_user_kind", "auth_user_id", "rate_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    auth_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("time_tracking_users.auth_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    rate_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TimeEntryModel(Base):
    """Факт списания времени (загрузка команды: billable / non-billable)."""

    __tablename__ = "time_tracking_entries"
    __table_args__ = (Index("ix_tt_entries_user_date", "auth_user_id", "work_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    auth_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("time_tracking_users.auth_user_id", ondelete="CASCADE"),
        nullable=False,
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_billable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TimeManagerClientModel(Base):
    """Клиент для time manager: биллинг, валюта, срок оплаты, налоги, скидка."""

    __tablename__ = "time_tracking_clients"
    __table_args__ = (Index("ix_tt_clients_name", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    invoice_due_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="custom")
    invoice_due_days_after_issue: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    tax2_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    discount_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TimeManagerClientTaskModel(Base):
    """Задача, привязанная к клиенту time manager (отдельный набор задач на каждого клиента)."""

    __tablename__ = "time_tracking_client_tasks"
    __table_args__ = (Index("ix_tt_client_tasks_client", "client_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("time_tracking_clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    default_billable_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    billable_by_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    common_for_future_projects: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    add_to_existing_projects: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TimeManagerClientExpenseCategoryModel(Base):
    """Категория расхода по клиенту time manager (справочник для счетов и форм)."""

    __tablename__ = "time_tracking_client_expense_categories"
    __table_args__ = (Index("ix_tt_client_exp_cat_client", "client_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("time_tracking_clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    has_unit_price: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
