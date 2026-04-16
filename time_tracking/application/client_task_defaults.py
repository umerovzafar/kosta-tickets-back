"""Общие задачи по умолчанию для всех клиентов time manager.

Список совпадает с задачами из раздела «Other tasks», которые должны
автоматически попадать в «Common tasks» (common_for_future_projects).
"""

from __future__ import annotations

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models import TimeManagerClientModel, TimeManagerClientTaskModel
from infrastructure.repositories import ClientTaskRepository
from infrastructure.repository_shared import _now_utc

# Имена как в UI (при сопоставлении используется lower(trim(name))).
DEFAULT_COMMON_TASK_NAMES: tuple[str, ...] = (
    "Accounting",
    "Business Development",
    "Court Hearing",
    "Court Hearing Preparation",
    "Drafting Documents",
    "Lunch/Dinner",
    "Other research",
    "Proposals",
    "Publications",
    "Review new legislation",
)


def _names_lower() -> tuple[str, ...]:
    return tuple(n.strip().lower() for n in DEFAULT_COMMON_TASK_NAMES)


async def _promote_existing_tasks_to_common(session: AsyncSession, *, client_id: str | None) -> None:
    """Поставить common_for_future_projects=TRUE у задач с именами из списка."""
    cond = [
        func.lower(func.trim(TimeManagerClientTaskModel.name)).in_(_names_lower()),
        TimeManagerClientTaskModel.common_for_future_projects.is_(False),
    ]
    if client_id is not None:
        cond.append(TimeManagerClientTaskModel.client_id == client_id)
    await session.execute(
        update(TimeManagerClientTaskModel)
        .where(and_(*cond))
        .values(common_for_future_projects=True, updated_at=_now_utc())
    )


async def _insert_missing_default_tasks(session: AsyncSession, client_id: str) -> None:
    """Создать отсутствующие задачи из списка с common_for_future_projects=TRUE."""
    r = await session.execute(
        select(TimeManagerClientTaskModel.name).where(TimeManagerClientTaskModel.client_id == client_id)
    )
    existing = {str(x).strip().lower() for x in r.scalars().all()}
    repo = ClientTaskRepository(session)
    for name in DEFAULT_COMMON_TASK_NAMES:
        if name.strip().lower() in existing:
            continue
        await repo.create(
            client_id=client_id,
            name=name,
            default_billable_rate=None,
            billable_by_default=True,
            common_for_future_projects=True,
            add_to_existing_projects=False,
        )
        existing.add(name.strip().lower())


async def seed_default_common_tasks_for_client(session: AsyncSession, client_id: str) -> None:
    """Один клиент: поднять флаг common у совпадающих задач и добавить недостающие из списка."""
    await _promote_existing_tasks_to_common(session, client_id=client_id)
    await _insert_missing_default_tasks(session, client_id)


async def seed_default_common_tasks_for_all_clients(session: AsyncSession) -> None:
    """Все клиенты: глобально поднять флаг, затем для каждого — только недостающие INSERT."""
    await _promote_existing_tasks_to_common(session, client_id=None)
    r = await session.execute(select(TimeManagerClientModel.id))
    for cid in r.scalars().all():
        await _insert_missing_default_tasks(session, str(cid))
