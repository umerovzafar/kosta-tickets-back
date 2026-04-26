"""Автосдача прошлой отчётной недели (сб..пт) и блокировка правок после сб 9:00 (WEEKLY_SUBMIT_TZ)."""

from __future__ import annotations

import logging
import os
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from application.weekly_period import (
    is_work_week_edit_deadline_passed,
    local_today,
    previous_closed_saturday_fri_for_anchor,
)
from infrastructure.repository_users import TimeTrackingUserRepository
from infrastructure.repository_weekly_submissions import WeeklySubmissionRepository

_log = logging.getLogger(__name__)


def _submit_tz() -> str:
    return (os.environ.get("WEEKLY_SUBMIT_TZ", "UTC") or "UTC").strip() or "UTC"


async def is_work_date_locked_for_user(
    session: AsyncSession, auth_user_id: int, work_date: date
) -> bool:
    if is_work_week_edit_deadline_passed(work_date, submit_tz=_submit_tz()):
        return True
    repo = WeeklySubmissionRepository(session)
    return await repo.is_work_date_locked(auth_user_id, work_date)


async def run_weekly_auto_submit(session: AsyncSession) -> int:
    """Создаёт записи сдачи за **предыдущую** отчётную неделю (сб..пт), закрываемую в субботу 9:00.

    Celery: якорь = сегодня (в т.з.); при запуске в субботу 9:00 в Asia/Tashkent
    сдаётся последний полный блок сб–пт.

    Возвращает число **новых** записей.
    """
    anchor = local_today(_submit_tz())
    w0, w1 = previous_closed_saturday_fri_for_anchor(anchor)
    ur = TimeTrackingUserRepository(session)
    users = await ur.list_users()
    wr = WeeklySubmissionRepository(session)
    created = 0
    for u in users:
        if u.is_archived:
            continue
        before = await wr.is_work_date_locked(u.auth_user_id, w0)
        if before:
            continue
        await wr.upsert_submission(
            auth_user_id=u.auth_user_id,
            week_start=w0,
            week_end=w1,
            auto=True,
        )
        created += 1
        mgr = u.reports_to_auth_user_id
        _log.info(
            "weekly time submitted user=%s week=%s..%s manager=%s",
            u.auth_user_id,
            w0,
            w1,
            mgr,
        )
    return created


def run_weekly_auto_submit_sync() -> int:
    """Точка входа Celery (синхронно)."""
    import asyncio

    from infrastructure.database import async_session_factory

    async def _go() -> int:
        async with async_session_factory() as session:
            n = await run_weekly_auto_submit(session)
            await session.commit()
            return n

    return asyncio.run(_go())
