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
