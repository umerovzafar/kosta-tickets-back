"""
Алиасы почасовых ставок под префиксом /api/v1/users/... — тот же прокси, что и
/api/v1/time-tracking/users/... (нужно, если nginx проксирует только /api/v1/users).
"""

from fastapi import APIRouter, Depends, Query

from presentation.routes.time_tracking_hourly_proxy import (
    HourlyRateCreateBody,
    HourlyRatePatchBody,
    get_current_user,
    hourly_rates_create_gateway,
    hourly_rates_delete_gateway,
    hourly_rates_get_gateway,
    hourly_rates_list_gateway,
    hourly_rates_patch_gateway,
)

router = APIRouter(prefix="/api/v1/users", tags=["time_tracking"])


@router.get("/{user_id}/hourly-rates")
async def list_hourly_rates_under_users(
    user_id: int,
    kind: str = Query(..., description="billable | cost"),
    user: dict = Depends(get_current_user),
):
    return await hourly_rates_list_gateway(user_id, kind, user)


@router.get("/{user_id}/hourly-rates/{rate_id}")
async def get_hourly_rate_under_users(
    user_id: int,
    rate_id: str,
    user: dict = Depends(get_current_user),
):
    return await hourly_rates_get_gateway(user_id, rate_id, user)


@router.post("/{user_id}/hourly-rates")
async def create_hourly_rate_under_users(
    user_id: int,
    body: HourlyRateCreateBody,
    user: dict = Depends(get_current_user),
):
    return await hourly_rates_create_gateway(user_id, body, user)


@router.patch("/{user_id}/hourly-rates/{rate_id}")
async def patch_hourly_rate_under_users(
    user_id: int,
    rate_id: str,
    body: HourlyRatePatchBody,
    user: dict = Depends(get_current_user),
):
    return await hourly_rates_patch_gateway(user_id, rate_id, body, user)


@router.delete("/{user_id}/hourly-rates/{rate_id}")
async def delete_hourly_rate_under_users(
    user_id: int,
    rate_id: str,
    user: dict = Depends(get_current_user),
):
    return await hourly_rates_delete_gateway(user_id, rate_id, user)
