"""Администрирование: сброс бизнес-данных учёта времени (только главный администратор)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from infrastructure.config import get_settings
from infrastructure.time_tracking_business_reset import wipe_time_tracking_business_data
from presentation.deps import check_main_admin, get_current_user

router = APIRouter(prefix="/admin/time-tracking", tags=["admin"])
_log = logging.getLogger(__name__)

_RESET_CONFIRM = "RESET_TIME_TRACKING_BUSINESS_DATA"


class ResetTimeTrackingBusinessBody(BaseModel):
    confirm: str = Field(..., description=f'Должно быть ровно "{_RESET_CONFIRM}"')


class ResetTimeTrackingBusinessOut(BaseModel):
    ok: bool = True
    message: str = (
        "Удалены клиенты, проекты, записи времени, счета, отчёты и связанные данные. "
        "Пользователи учёта времени (time_tracking_users) сохранены."
    )


@router.post("/business-data/reset", response_model=ResetTimeTrackingBusinessOut)
async def reset_time_tracking_business_data(
    body: ResetTimeTrackingBusinessBody,
    user: dict = Depends(get_current_user),
):
    """
    TRUNCATE всех таблиц модуля кроме ``time_tracking_users`` (и без затрагивания auth).

    Требуется роль «Главный администратор», флаг ``TIME_TRACKING_ALLOW_BUSINESS_DATA_RESET=true``
    и тело ``{"confirm": "RESET_TIME_TRACKING_BUSINESS_DATA"}``.
    """
    check_main_admin(user)
    settings = get_settings()
    if not settings.time_tracking_allow_business_data_reset:
        raise HTTPException(
            status_code=409,
            detail=(
                "Сброс отключён: для сервиса time_tracking задайте TIME_TRACKING_ALLOW_BUSINESS_DATA_RESET=true "
                "в .env / Portainer и перезапустите контейнер time_tracking. "
                "Если в .env явно указано false — удалите строку или поставьте true."
            ),
        )
    if (body.confirm or "").strip() != _RESET_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail=f'Укажите confirm: "{_RESET_CONFIRM}"',
        )

    _log.warning(
        "time_tracking business reset by user_id=%s email=%s",
        user.get("id"),
        user.get("email"),
    )
    await wipe_time_tracking_business_data()
    return ResetTimeTrackingBusinessOut()
