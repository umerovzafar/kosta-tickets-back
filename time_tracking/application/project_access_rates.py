"""Проверка почасовых ставок при выдаче доступа к проекту (валюта проекта)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from application.hourly_rate_logic import filter_rates_by_currency, pick_rate_for_date
from infrastructure.repositories import ClientProjectRepository, HourlyRateRepository


async def validate_hourly_rates_for_project_access(
    session: AsyncSession,
    *,
    auth_user_id: int,
    project_ids: list[str],
) -> None:
    """
    Без ставок billable и cost в валюте проекта (интервал на сегодня) доступ к проекту не выдаётся.
    """
    if not project_ids:
        return
    cpr = ClientProjectRepository(session)
    hr = HourlyRateRepository(session)
    on_date = date.today()
    for pid in project_ids:
        row = await cpr.get_by_id_global(pid)
        if not row:
            continue
        cur = (row.currency or "USD").strip().upper()[:10] or "USD"
        for kind, label in (
            ("billable", "оплачиваемая (billable)"),
            ("cost", "себестоимость (cost)"),
        ):
            rates = await hr.list_by_user_and_kind(auth_user_id, kind)
            scoped = filter_rates_by_currency(rates, cur)
            if pick_rate_for_date(scoped, on_date) is None:
                raise ValueError(
                    f"Нельзя выдать доступ к проекту «{row.name}» (валюта {cur}): у пользователя нет "
                    f"почасовой ставки «{label}» в валюте {cur} на текущую дату. "
                    "Добавьте ставку в разделе почасовых ставок пользователя, затем повторите назначение."
                )
