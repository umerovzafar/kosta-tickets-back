"""
Алиасы почасовых ставок под префиксом /api/v1/users/... — тот же прокси, что и
/api/v1/time-tracking/users/... (нужно, если nginx проксирует только /api/v1/users).
"""

from fastapi import APIRouter, Depends, Query, Request

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
from presentation.routes.time_tracking_routes import require_manage_role, require_view_role
from presentation.routes.time_tracking_te_proxy import (
    TimeEntryCreateBody,
    TimeEntryPatchBody,
    time_entries_create_gateway,
    time_entries_delete_gateway,
    time_entries_list_gateway,
    time_entries_patch_gateway,
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


@router.get("/{user_id}/time-entries")
async def list_time_entries_under_users(
    user_id: int,
    request: Request,
    _: dict = Depends(require_view_role),
):
    return await time_entries_list_gateway(user_id, request)


@router.post("/{user_id}/time-entries")
async def create_time_entry_under_users(
    user_id: int,
    body: TimeEntryCreateBody,
    _: dict = Depends(require_manage_role),
):
    return await time_entries_create_gateway(user_id, body)


@router.patch("/{user_id}/time-entries/{entry_id}")
async def patch_time_entry_under_users(
    user_id: int,
    entry_id: str,
    body: TimeEntryPatchBody,
    _: dict = Depends(require_manage_role),
):
    return await time_entries_patch_gateway(user_id, entry_id, body)


@router.delete("/{user_id}/time-entries/{entry_id}")
async def delete_time_entry_under_users(
    user_id: int,
    entry_id: str,
    _: dict = Depends(require_manage_role),
):
    return await time_entries_delete_gateway(user_id, entry_id)
