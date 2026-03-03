from datetime import time
from sqlalchemy import Integer, Time
from sqlalchemy.orm import Mapped, mapped_column
from infrastructure.database import Base


class WorkdaySettingsModel(Base):
    __tablename__ = "attendance_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workday_start: Mapped[time] = mapped_column(Time, nullable=False)
    workday_end: Mapped[time] = mapped_column(Time, nullable=False)
    late_threshold_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_hours_norm: Mapped[int] = mapped_column(Integer, nullable=False, default=8)

