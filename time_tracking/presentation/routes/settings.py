"""Глобальные настройки учёта времени (округление)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from application.settings_sync import recalc_rounded_hours_for_all_entries
from application.time_rounding import RoundingSettings
from infrastructure.database import get_session
from infrastructure.repository_settings import TimeTrackingSettingsRepository
from presentation.schemas import RoundingSettingsOut, RoundingSettingsPutBody

router = APIRouter(prefix="/settings", tags=["settings"])


def _to_out(settings: RoundingSettings) -> RoundingSettingsOut:
    return RoundingSettingsOut(
        rounding_enabled=settings.rounding_enabled,
        rounding_mode=settings.rounding_mode,  # type: ignore[arg-type]
        rounding_step_minutes=settings.rounding_step_minutes,
    )


@router.get("/rounding", response_model=RoundingSettingsOut)
async def get_rounding_settings(
    session: AsyncSession = Depends(get_session),
) -> RoundingSettingsOut:
    repo = TimeTrackingSettingsRepository(session)
    settings = await repo.get()
    await session.commit()
    return _to_out(settings)


@router.put("/rounding", response_model=RoundingSettingsOut)
async def put_rounding_settings(
    body: RoundingSettingsPutBody,
    session: AsyncSession = Depends(get_session),
) -> RoundingSettingsOut:
    repo = TimeTrackingSettingsRepository(session)
    try:
        settings = await repo.update(
            rounding_enabled=body.rounding_enabled,
            rounding_mode=body.rounding_mode.value,
            rounding_step_minutes=body.rounding_step_minutes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # После смены настроек — массовый пересчёт rounded_hours одним UPDATE.
    await recalc_rounded_hours_for_all_entries(session, settings)
    await session.commit()
    return _to_out(settings)
