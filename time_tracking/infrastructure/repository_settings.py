"""Репозиторий глобальных настроек учёта времени (округление)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.time_rounding import RoundingSettings
from infrastructure.models import TimeTrackingSettingsModel
from infrastructure.repository_shared import _now_utc

_SETTINGS_ID = 1


class TimeTrackingSettingsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_or_create_row(self) -> TimeTrackingSettingsModel:
        r = await self._session.execute(
            select(TimeTrackingSettingsModel).where(TimeTrackingSettingsModel.id == _SETTINGS_ID)
        )
        row = r.scalars().one_or_none()
        if row is not None:
            return row
        row = TimeTrackingSettingsModel(
            id=_SETTINGS_ID,
            rounding_enabled=True,
            rounding_mode="up",
            rounding_step_minutes=15,
            created_at=_now_utc(),
            updated_at=None,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self) -> RoundingSettings:
        row = await self._get_or_create_row()
        return RoundingSettings(
            rounding_enabled=bool(row.rounding_enabled),
            rounding_mode=str(row.rounding_mode),
            rounding_step_minutes=int(row.rounding_step_minutes),
        )

    async def update(
        self,
        *,
        rounding_enabled: bool,
        rounding_mode: str,
        rounding_step_minutes: int,
    ) -> RoundingSettings:
        candidate = RoundingSettings(
            rounding_enabled=bool(rounding_enabled),
            rounding_mode=str(rounding_mode),
            rounding_step_minutes=int(rounding_step_minutes),
        )
        candidate.validate()
        row = await self._get_or_create_row()
        row.rounding_enabled = candidate.rounding_enabled
        row.rounding_mode = candidate.rounding_mode
        row.rounding_step_minutes = candidate.rounding_step_minutes
        row.updated_at = _now_utc()
        self._session.add(row)
        await self._session.flush()
        return candidate
