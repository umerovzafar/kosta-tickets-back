import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from application.hourly_rate_logic import intervals_overlap, validate_range_order
from application.ports import HealthRepositoryPort
from infrastructure.models import TimeTrackingUserModel, UserHourlyRateModel


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class HealthRepository(HealthRepositoryPort):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def check(self) -> bool:
        try:
            await self._session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


class TimeTrackingUserRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_users(self) -> list[TimeTrackingUserModel]:
        q = select(TimeTrackingUserModel).order_by(TimeTrackingUserModel.id)
        r = await self._session.execute(q)
        return list(r.scalars().all())

    async def get_by_auth_user_id(self, auth_user_id: int) -> TimeTrackingUserModel | None:
        r = await self._session.execute(
            select(TimeTrackingUserModel).where(TimeTrackingUserModel.auth_user_id == auth_user_id)
        )
        return r.scalars().one_or_none()

    async def upsert_user(
        self,
        *,
        auth_user_id: int,
        email: str,
        display_name: str | None = None,
        picture: str | None = None,
        role: str = "",
        is_blocked: bool = False,
        is_archived: bool = False,
    ) -> TimeTrackingUserModel:
        r = await self._session.execute(
            select(TimeTrackingUserModel).where(TimeTrackingUserModel.auth_user_id == auth_user_id)
        )
        row = r.scalars().one_or_none()
        now = _now_utc()
        if row:
            row.email = email
            row.display_name = display_name
            row.picture = picture
            row.role = role
            row.is_blocked = is_blocked
            row.is_archived = is_archived
            row.updated_at = now
            self._session.add(row)
            return row
        row = TimeTrackingUserModel(
            auth_user_id=auth_user_id,
            email=email,
            display_name=display_name,
            picture=picture,
            role=role,
            is_blocked=is_blocked,
            is_archived=is_archived,
            created_at=now,
            updated_at=None,
        )
        self._session.add(row)
        return row

    async def delete_by_auth_user_id(self, auth_user_id: int) -> bool:
        """Удаляет пользователя по auth_user_id. Возвращает True если запись была удалена."""
        from sqlalchemy import delete

        r = await self._session.execute(
            delete(TimeTrackingUserModel).where(TimeTrackingUserModel.auth_user_id == auth_user_id)
        )
        return r.rowcount > 0


_RATE_KINDS = frozenset({"billable", "cost"})


class HourlyRateRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_by_user_and_kind(self, auth_user_id: int, rate_kind: str) -> list[UserHourlyRateModel]:
        q = (
            select(UserHourlyRateModel)
            .where(
                UserHourlyRateModel.auth_user_id == auth_user_id,
                UserHourlyRateModel.rate_kind == rate_kind,
            )
            .order_by(UserHourlyRateModel.valid_from.asc().nullsfirst(), UserHourlyRateModel.id)
        )
        r = await self._session.execute(q)
        return list(r.scalars().all())

    async def get_by_id(self, auth_user_id: int, rate_id: str) -> UserHourlyRateModel | None:
        r = await self._session.execute(
            select(UserHourlyRateModel).where(
                UserHourlyRateModel.auth_user_id == auth_user_id,
                UserHourlyRateModel.id == rate_id,
            )
        )
        return r.scalars().one_or_none()

    def _has_overlap(
        self,
        rows: list[UserHourlyRateModel],
        valid_from: date | None,
        valid_to: date | None,
        *,
        exclude_id: str | None = None,
    ) -> bool:
        for row in rows:
            if exclude_id and row.id == exclude_id:
                continue
            if intervals_overlap(row.valid_from, row.valid_to, valid_from, valid_to):
                return True
        return False

    async def create(
        self,
        *,
        auth_user_id: int,
        rate_kind: str,
        amount: Decimal,
        currency: str,
        valid_from: date | None,
        valid_to: date | None,
    ) -> UserHourlyRateModel:
        if rate_kind not in _RATE_KINDS:
            raise ValueError("Недопустимый тип ставки")
        validate_range_order(valid_from, valid_to)
        if amount <= 0:
            raise ValueError("Сумма должна быть больше нуля")
        existing = await self.list_by_user_and_kind(auth_user_id, rate_kind)
        if self._has_overlap(existing, valid_from, valid_to):
            raise ValueError("Интервал пересекается с другой ставкой этого типа")
        now = _now_utc()
        row = UserHourlyRateModel(
            id=str(uuid.uuid4()),
            auth_user_id=auth_user_id,
            rate_kind=rate_kind,
            amount=amount,
            currency=(currency or "USD").strip().upper()[:10] or "USD",
            valid_from=valid_from,
            valid_to=valid_to,
            created_at=now,
            updated_at=None,
        )
        self._session.add(row)
        return row

    async def update(
        self,
        *,
        auth_user_id: int,
        rate_id: str,
        patch: dict[str, Any],
    ) -> UserHourlyRateModel:
        row = await self.get_by_id(auth_user_id, rate_id)
        if not row:
            raise LookupError("not_found")

        new_amount: Decimal = row.amount
        if "amount" in patch:
            raw = patch["amount"]
            new_amount = raw if isinstance(raw, Decimal) else Decimal(str(raw))
        if new_amount <= 0:
            raise ValueError("Сумма должна быть больше нуля")

        new_currency = row.currency
        if "currency" in patch:
            new_currency = (patch["currency"] or "USD").strip().upper()[:10] or "USD"

        new_from = row.valid_from
        if "valid_from" in patch:
            new_from = patch["valid_from"]

        new_to = row.valid_to
        if "valid_to" in patch:
            new_to = patch["valid_to"]

        validate_range_order(new_from, new_to)
        existing = await self.list_by_user_and_kind(auth_user_id, row.rate_kind)
        if self._has_overlap(existing, new_from, new_to, exclude_id=rate_id):
            raise ValueError("Интервал пересекается с другой ставкой этого типа")

        row.amount = new_amount
        row.currency = new_currency
        row.valid_from = new_from
        row.valid_to = new_to
        row.updated_at = _now_utc()
        self._session.add(row)
        return row

    async def delete(self, auth_user_id: int, rate_id: str) -> bool:
        row = await self.get_by_id(auth_user_id, rate_id)
        if not row:
            return False
        await self._session.execute(
            delete(UserHourlyRateModel).where(
                UserHourlyRateModel.auth_user_id == auth_user_id,
                UserHourlyRateModel.id == rate_id,
            )
        )
        return True
