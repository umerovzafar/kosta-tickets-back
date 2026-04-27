"""Правило: у проекта с назначенными в доступе пользователями должен быть хотя бы один с должностью партнёра."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models import TimeTrackingUserModel
from infrastructure.repository_access import UserProjectAccessRepository
from infrastructure.repository_clients import ClientProjectRepository


def job_title_indicates_partner(position: str | None) -> bool:
    """Должность из поля position (TT): партнёр / partner (без привязки к орг-ролям)."""
    if not position or not str(position).strip():
        return False
    s = str(position).strip().casefold()
    if "партн" in s:
        return True
    if "partner" in s:
        return True
    return False


async def ensure_projects_have_partner_assignee(
    session: AsyncSession,
    access_repo: UserProjectAccessRepository,
    project_ids: set[str],
    *,
    projects: ClientProjectRepository | None = None,
) -> None:
    """
    Для каждого project_id: если к проекту привязан хотя бы один пользователь, среди них
    должен быть минимум один с `position`, указывающим на партнёра.
    """
    for pid in project_ids:
        if not (pid and str(pid).strip()):
            continue
        p = str(pid).strip()
        uids = await access_repo.list_auth_user_ids_for_project(p)
        if not uids:
            continue
        r = await session.execute(
            select(TimeTrackingUserModel.auth_user_id, TimeTrackingUserModel.position).where(
                TimeTrackingUserModel.auth_user_id.in_(uids)
            )
        )
        by_uid: dict[int, str | None] = {int(a): b for a, b in r.all()}
        if any(job_title_indicates_partner(by_uid.get(int(uid))) for uid in uids):
            continue
        label = p
        if projects is not None:
            pr = await projects.get_by_id_global(p)
            if pr is not None and getattr(pr, "name", None):
                label = str(pr.name).strip() or p
        raise ValueError(
            f"По проекту «{label}» среди пользователей с доступом к списанию времени "
            f"нужен хотя бы один с должностью партнёра (поле position в учёте времени, "
            f"например «Партнёр»).",
        )
