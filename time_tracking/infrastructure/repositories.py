import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import case, delete, func, select, text, and_
from sqlalchemy.ext.asyncio import AsyncSession

from application.hourly_rate_logic import intervals_overlap, validate_range_order
from application.ports import HealthRepositoryPort
from infrastructure.models import (
    TimeEntryModel,
    TimeManagerClientModel,
    TimeManagerClientExpenseCategoryModel,
    TimeManagerClientProjectModel,
    TimeManagerClientTaskModel,
    TimeTrackingUserModel,
    UserHourlyRateModel,
)


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
        weekly_capacity_hours: Decimal | None = None,
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
            if weekly_capacity_hours is not None:
                row.weekly_capacity_hours = weekly_capacity_hours
            row.updated_at = now
            self._session.add(row)
            return row
        cap = weekly_capacity_hours if weekly_capacity_hours is not None else Decimal("35")
        row = TimeTrackingUserModel(
            auth_user_id=auth_user_id,
            email=email,
            display_name=display_name,
            picture=picture,
            role=role,
            is_blocked=is_blocked,
            is_archived=is_archived,
            weekly_capacity_hours=cap,
            created_at=now,
            updated_at=None,
        )
        self._session.add(row)
        return row

    async def patch_weekly_capacity_hours(
        self, auth_user_id: int, weekly_capacity_hours: Decimal
    ) -> TimeTrackingUserModel | None:
        row = await self.get_by_auth_user_id(auth_user_id)
        if not row:
            return None
        row.weekly_capacity_hours = weekly_capacity_hours
        row.updated_at = _now_utc()
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


class TimeEntryRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def aggregate_by_user(
        self,
        date_from: date,
        date_to: date,
    ) -> dict[int, tuple[Decimal, Decimal, Decimal]]:
        """auth_user_id -> (total_hours, billable_hours, non_billable_hours)."""
        q = (
            select(
                TimeEntryModel.auth_user_id,
                func.coalesce(
                    func.sum(
                        case((TimeEntryModel.is_billable.is_(True), TimeEntryModel.hours), else_=0),
                    ),
                    0,
                ).label("billable"),
                func.coalesce(
                    func.sum(
                        case((TimeEntryModel.is_billable.is_(False), TimeEntryModel.hours), else_=0),
                    ),
                    0,
                ).label("non_bill"),
                func.coalesce(func.sum(TimeEntryModel.hours), 0).label("total"),
            )
            .where(
                TimeEntryModel.work_date >= date_from,
                TimeEntryModel.work_date <= date_to,
            )
            .group_by(TimeEntryModel.auth_user_id)
        )
        r = await self._session.execute(q)
        out: dict[int, tuple[Decimal, Decimal, Decimal]] = {}
        for row in r.all():
            uid = int(row.auth_user_id)
            bill = row.billable if isinstance(row.billable, Decimal) else Decimal(str(row.billable))
            non = row.non_bill if isinstance(row.non_bill, Decimal) else Decimal(str(row.non_bill))
            tot = row.total if isinstance(row.total, Decimal) else Decimal(str(row.total))
            out[uid] = (tot, bill, non)
        return out

    async def list_for_user(
        self,
        auth_user_id: int,
        date_from: date,
        date_to: date,
    ) -> list[TimeEntryModel]:
        q = (
            select(TimeEntryModel)
            .where(
                TimeEntryModel.auth_user_id == auth_user_id,
                TimeEntryModel.work_date >= date_from,
                TimeEntryModel.work_date <= date_to,
            )
            .order_by(TimeEntryModel.work_date.desc(), TimeEntryModel.id)
        )
        r = await self._session.execute(q)
        return list(r.scalars().all())

    async def get_by_id(self, auth_user_id: int, entry_id: str) -> TimeEntryModel | None:
        r = await self._session.execute(
            select(TimeEntryModel).where(
                TimeEntryModel.auth_user_id == auth_user_id,
                TimeEntryModel.id == entry_id,
            )
        )
        return r.scalars().one_or_none()

    async def create(
        self,
        *,
        entry_id: str,
        auth_user_id: int,
        work_date: date,
        hours: Decimal,
        is_billable: bool,
        project_id: str | None,
        description: str | None,
    ) -> TimeEntryModel:
        if hours <= 0:
            raise ValueError("Количество часов должно быть больше нуля")
        now = _now_utc()
        row = TimeEntryModel(
            id=entry_id,
            auth_user_id=auth_user_id,
            work_date=work_date,
            hours=hours,
            is_billable=is_billable,
            project_id=project_id,
            description=description,
            created_at=now,
            updated_at=None,
        )
        self._session.add(row)
        return row

    async def update(
        self,
        *,
        auth_user_id: int,
        entry_id: str,
        patch: dict[str, Any],
    ) -> TimeEntryModel:
        row = await self.get_by_id(auth_user_id, entry_id)
        if not row:
            raise LookupError("not_found")
        if "hours" in patch:
            h = patch["hours"]
            nh = h if isinstance(h, Decimal) else Decimal(str(h))
            if nh <= 0:
                raise ValueError("Количество часов должно быть больше нуля")
            row.hours = nh
        if "work_date" in patch:
            row.work_date = patch["work_date"]
        if "is_billable" in patch:
            row.is_billable = bool(patch["is_billable"])
        if "project_id" in patch:
            row.project_id = patch["project_id"]
        if "description" in patch:
            row.description = patch["description"]
        row.updated_at = _now_utc()
        self._session.add(row)
        return row

    async def delete(self, auth_user_id: int, entry_id: str) -> bool:
        row = await self.get_by_id(auth_user_id, entry_id)
        if not row:
            return False
        await self._session.execute(
            delete(TimeEntryModel).where(
                TimeEntryModel.auth_user_id == auth_user_id,
                TimeEntryModel.id == entry_id,
            )
        )
        return True


class ClientRepository:
    """Клиенты time manager (настройки биллинга)."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[TimeManagerClientModel]:
        q = select(TimeManagerClientModel).order_by(TimeManagerClientModel.name.asc())
        r = await self._session.execute(q)
        return list(r.scalars().all())

    async def get_by_id(self, client_id: str) -> TimeManagerClientModel | None:
        r = await self._session.execute(
            select(TimeManagerClientModel).where(TimeManagerClientModel.id == client_id)
        )
        return r.scalars().one_or_none()

    async def create(
        self,
        *,
        name: str,
        address: str | None,
        currency: str,
        invoice_due_mode: str,
        invoice_due_days_after_issue: int | None,
        tax_percent: Decimal | None,
        tax2_percent: Decimal | None,
        discount_percent: Decimal | None,
    ) -> TimeManagerClientModel:
        cid = str(uuid.uuid4())
        now = _now_utc()
        row = TimeManagerClientModel(
            id=cid,
            name=name.strip(),
            address=address,
            currency=(currency or "USD").strip().upper()[:10],
            invoice_due_mode=(invoice_due_mode or "custom").strip()[:50],
            invoice_due_days_after_issue=invoice_due_days_after_issue,
            tax_percent=tax_percent,
            tax2_percent=tax2_percent,
            discount_percent=discount_percent,
            created_at=now,
            updated_at=None,
        )
        self._session.add(row)
        return row

    async def update(self, client_id: str, patch: dict[str, Any]) -> TimeManagerClientModel | None:
        row = await self.get_by_id(client_id)
        if not row:
            return None
        if "name" in patch and patch["name"] is not None:
            row.name = str(patch["name"]).strip()
        if "address" in patch:
            row.address = patch["address"]
        if "currency" in patch and patch["currency"] is not None:
            row.currency = str(patch["currency"]).strip().upper()[:10]
        if "invoice_due_mode" in patch and patch["invoice_due_mode"] is not None:
            row.invoice_due_mode = str(patch["invoice_due_mode"]).strip()[:50]
        if "invoice_due_days_after_issue" in patch:
            row.invoice_due_days_after_issue = patch["invoice_due_days_after_issue"]
        if "tax_percent" in patch:
            row.tax_percent = patch["tax_percent"]
        if "tax2_percent" in patch:
            row.tax2_percent = patch["tax2_percent"]
        if "discount_percent" in patch:
            row.discount_percent = patch["discount_percent"]
        row.updated_at = _now_utc()
        self._session.add(row)
        return row

    async def delete(self, client_id: str) -> bool:
        row = await self.get_by_id(client_id)
        if not row:
            return False
        await self._session.execute(delete(TimeManagerClientModel).where(TimeManagerClientModel.id == client_id))
        return True


class ClientTaskRepository:
    """Задачи клиента time manager."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_for_client(self, client_id: str) -> list[TimeManagerClientTaskModel]:
        q = (
            select(TimeManagerClientTaskModel)
            .where(TimeManagerClientTaskModel.client_id == client_id)
            .order_by(TimeManagerClientTaskModel.name.asc())
        )
        r = await self._session.execute(q)
        return list(r.scalars().all())

    async def get_by_id(self, client_id: str, task_id: str) -> TimeManagerClientTaskModel | None:
        r = await self._session.execute(
            select(TimeManagerClientTaskModel).where(
                TimeManagerClientTaskModel.client_id == client_id,
                TimeManagerClientTaskModel.id == task_id,
            )
        )
        return r.scalars().one_or_none()

    async def create(
        self,
        *,
        client_id: str,
        name: str,
        default_billable_rate: Decimal | None,
        billable_by_default: bool,
        common_for_future_projects: bool,
        add_to_existing_projects: bool,
    ) -> TimeManagerClientTaskModel:
        tid = str(uuid.uuid4())
        now = _now_utc()
        row = TimeManagerClientTaskModel(
            id=tid,
            client_id=client_id,
            name=name.strip(),
            default_billable_rate=default_billable_rate,
            billable_by_default=billable_by_default,
            common_for_future_projects=common_for_future_projects,
            add_to_existing_projects=add_to_existing_projects,
            created_at=now,
            updated_at=None,
        )
        self._session.add(row)
        return row

    async def update(self, client_id: str, task_id: str, patch: dict[str, Any]) -> TimeManagerClientTaskModel | None:
        row = await self.get_by_id(client_id, task_id)
        if not row:
            return None
        if "name" in patch and patch["name"] is not None:
            row.name = str(patch["name"]).strip()
        if "default_billable_rate" in patch:
            v = patch["default_billable_rate"]
            row.default_billable_rate = None if v is None else (v if isinstance(v, Decimal) else Decimal(str(v)))
        if "billable_by_default" in patch:
            row.billable_by_default = bool(patch["billable_by_default"])
        if "common_for_future_projects" in patch:
            row.common_for_future_projects = bool(patch["common_for_future_projects"])
        if "add_to_existing_projects" in patch:
            row.add_to_existing_projects = bool(patch["add_to_existing_projects"])
        row.updated_at = _now_utc()
        self._session.add(row)
        return row

    async def delete(self, client_id: str, task_id: str) -> bool:
        row = await self.get_by_id(client_id, task_id)
        if not row:
            return False
        await self._session.execute(
            delete(TimeManagerClientTaskModel).where(
                TimeManagerClientTaskModel.client_id == client_id,
                TimeManagerClientTaskModel.id == task_id,
            )
        )
        return True


class ClientExpenseCategoryRepository:
    """Категории расходов по клиенту time manager."""

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _normalize_name(name: str) -> str:
        return name.strip()

    async def list_for_client(
        self,
        client_id: str,
        *,
        include_archived: bool = False,
    ) -> list[TimeManagerClientExpenseCategoryModel]:
        q = select(TimeManagerClientExpenseCategoryModel).where(
            TimeManagerClientExpenseCategoryModel.client_id == client_id,
        )
        if not include_archived:
            q = q.where(TimeManagerClientExpenseCategoryModel.is_archived.is_(False))
        q = q.order_by(
            TimeManagerClientExpenseCategoryModel.sort_order.asc().nulls_last(),
            TimeManagerClientExpenseCategoryModel.name.asc(),
        )
        r = await self._session.execute(q)
        return list(r.scalars().all())

    async def get_by_id(
        self,
        client_id: str,
        category_id: str,
    ) -> TimeManagerClientExpenseCategoryModel | None:
        r = await self._session.execute(
            select(TimeManagerClientExpenseCategoryModel).where(
                TimeManagerClientExpenseCategoryModel.client_id == client_id,
                TimeManagerClientExpenseCategoryModel.id == category_id,
            )
        )
        return r.scalars().one_or_none()

    async def has_active_name_conflict(
        self,
        client_id: str,
        name: str,
        *,
        exclude_category_id: str | None = None,
    ) -> bool:
        """Другая неархивная категория с тем же именем (без учёта регистра и краевых пробелов)."""
        norm = self._normalize_name(name).lower()
        if not norm:
            return False
        cond = and_(
            TimeManagerClientExpenseCategoryModel.client_id == client_id,
            TimeManagerClientExpenseCategoryModel.is_archived.is_(False),
            func.lower(func.trim(TimeManagerClientExpenseCategoryModel.name)) == norm,
        )
        if exclude_category_id:
            cond = and_(cond, TimeManagerClientExpenseCategoryModel.id != exclude_category_id)
        q = select(func.count()).select_from(TimeManagerClientExpenseCategoryModel).where(cond)
        r = await self._session.execute(q)
        n = r.scalar_one()
        return int(n or 0) > 0

    async def usage_count(self, category_id: str) -> int:
        """Число использований категории (строки расходов/счётов). Пока нет таблиц — всегда 0."""
        _ = category_id
        return 0

    async def create(
        self,
        *,
        client_id: str,
        name: str,
        has_unit_price: bool = False,
        sort_order: int | None = None,
    ) -> TimeManagerClientExpenseCategoryModel:
        cid = str(uuid.uuid4())
        now = _now_utc()
        row = TimeManagerClientExpenseCategoryModel(
            id=cid,
            client_id=client_id,
            name=self._normalize_name(name),
            has_unit_price=has_unit_price,
            is_archived=False,
            sort_order=sort_order,
            created_at=now,
            updated_at=None,
        )
        self._session.add(row)
        return row

    async def update(
        self,
        client_id: str,
        category_id: str,
        patch: dict[str, Any],
    ) -> TimeManagerClientExpenseCategoryModel | None:
        row = await self.get_by_id(client_id, category_id)
        if not row:
            return None
        if "name" in patch and patch["name"] is not None:
            row.name = self._normalize_name(str(patch["name"]))
        if "has_unit_price" in patch:
            row.has_unit_price = bool(patch["has_unit_price"])
        if "is_archived" in patch:
            row.is_archived = bool(patch["is_archived"])
        if "sort_order" in patch:
            v = patch["sort_order"]
            row.sort_order = None if v is None else int(v)
        row.updated_at = _now_utc()
        self._session.add(row)
        return row

    async def delete(self, client_id: str, category_id: str) -> bool:
        row = await self.get_by_id(client_id, category_id)
        if not row:
            return False
        await self._session.execute(
            delete(TimeManagerClientExpenseCategoryModel).where(
                TimeManagerClientExpenseCategoryModel.client_id == client_id,
                TimeManagerClientExpenseCategoryModel.id == category_id,
            )
        )
        return True


_REPORT_VISIBILITY = frozenset({"managers_only", "all_assigned"})
_PROJECT_TYPES = frozenset({"time_and_materials", "fixed_fee", "non_billable"})


def _strip_opt(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _decimal_none(v: Any) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


class ClientProjectRepository:
    """Проекты клиента time manager."""

    def __init__(self, session: AsyncSession):
        self._session = session

    @staticmethod
    def _normalize_code(code: str | None) -> str | None:
        if code is None:
            return None
        s = str(code).strip()
        return s if s else None

    async def list_for_client(
        self,
        client_id: str,
        *,
        include_archived: bool = False,
    ) -> list[TimeManagerClientProjectModel]:
        q = select(TimeManagerClientProjectModel).where(
            TimeManagerClientProjectModel.client_id == client_id,
        )
        if not include_archived:
            q = q.where(TimeManagerClientProjectModel.is_archived.is_(False))
        q = q.order_by(TimeManagerClientProjectModel.name.asc())
        r = await self._session.execute(q)
        return list(r.scalars().all())

    async def get_by_id(
        self,
        client_id: str,
        project_id: str,
    ) -> TimeManagerClientProjectModel | None:
        r = await self._session.execute(
            select(TimeManagerClientProjectModel).where(
                TimeManagerClientProjectModel.client_id == client_id,
                TimeManagerClientProjectModel.id == project_id,
            )
        )
        return r.scalars().one_or_none()

    async def get_last_project_with_code(
        self,
        client_id: str,
    ) -> TimeManagerClientProjectModel | None:
        q = (
            select(TimeManagerClientProjectModel)
            .where(
                TimeManagerClientProjectModel.client_id == client_id,
                TimeManagerClientProjectModel.code.isnot(None),
                func.trim(TimeManagerClientProjectModel.code) != "",
            )
            .order_by(
                TimeManagerClientProjectModel.updated_at.desc().nulls_last(),
                TimeManagerClientProjectModel.created_at.desc(),
            )
            .limit(1)
        )
        r = await self._session.execute(q)
        return r.scalars().one_or_none()

    async def has_code_conflict(
        self,
        client_id: str,
        code: str | None,
        *,
        exclude_project_id: str | None = None,
    ) -> bool:
        norm = self._normalize_code(code)
        if not norm:
            return False
        key = norm.lower()
        cond = and_(
            TimeManagerClientProjectModel.client_id == client_id,
            func.lower(func.trim(TimeManagerClientProjectModel.code)) == key,
        )
        if exclude_project_id:
            cond = and_(cond, TimeManagerClientProjectModel.id != exclude_project_id)
        q = select(func.count()).select_from(TimeManagerClientProjectModel).where(cond)
        r = await self._session.execute(q)
        n = r.scalar_one()
        return int(n or 0) > 0

    async def allocate_duplicate_code(self, client_id: str, base: str | None) -> str | None:
        """Уникальный код для копии: `code-copy`, `code-copy-2`, … в пределах 64 символов."""
        norm = self._normalize_code(base)
        if not norm:
            return None
        for i in range(0, 200):
            suffix = "-copy" if i == 0 else f"-copy-{i + 1}"
            max_prefix = max(1, 64 - len(suffix))
            prefix = norm[:max_prefix]
            cand = f"{prefix}{suffix}"
            if not await self.has_code_conflict(client_id, cand):
                return cand
        return None

    @staticmethod
    def _name_with_copy_suffix(name: str) -> str:
        suffix = " (копия)"
        n = name.strip()
        if len(n) + len(suffix) <= 500:
            return n + suffix
        return n[: 500 - len(suffix)] + suffix

    async def duplicate_from(
        self,
        client_id: str,
        project_id: str,
    ) -> TimeManagerClientProjectModel | None:
        src = await self.get_by_id(client_id, project_id)
        if not src:
            return None
        new_code = await self.allocate_duplicate_code(client_id, src.code)
        return await self.create(
            client_id=client_id,
            name=self._name_with_copy_suffix(src.name),
            code=new_code,
            start_date=src.start_date,
            end_date=src.end_date,
            notes=src.notes,
            report_visibility=src.report_visibility,
            project_type=src.project_type,
            billable_rate_type=src.billable_rate_type,
            budget_type=src.budget_type,
            budget_amount=src.budget_amount,
            budget_hours=src.budget_hours,
            budget_resets_every_month=src.budget_resets_every_month,
            budget_includes_expenses=src.budget_includes_expenses,
            send_budget_alerts=src.send_budget_alerts,
            budget_alert_threshold_percent=src.budget_alert_threshold_percent,
            fixed_fee_amount=src.fixed_fee_amount,
            is_archived=False,
        )

    async def time_entries_count(self, project_id: str) -> int:
        q = select(func.count()).select_from(TimeEntryModel).where(
            TimeEntryModel.project_id == project_id,
        )
        r = await self._session.execute(q)
        n = r.scalar_one()
        return int(n or 0)

    async def create(
        self,
        *,
        client_id: str,
        name: str,
        code: str | None,
        start_date: date | None,
        end_date: date | None,
        notes: str | None,
        report_visibility: str,
        project_type: str = "time_and_materials",
        billable_rate_type: str | None = None,
        budget_type: str | None = None,
        budget_amount: Decimal | None = None,
        budget_hours: Decimal | None = None,
        budget_resets_every_month: bool = False,
        budget_includes_expenses: bool = False,
        send_budget_alerts: bool = False,
        budget_alert_threshold_percent: Decimal | None = None,
        fixed_fee_amount: Decimal | None = None,
        is_archived: bool = False,
    ) -> TimeManagerClientProjectModel:
        pid = str(uuid.uuid4())
        now = _now_utc()
        rv = report_visibility if report_visibility in _REPORT_VISIBILITY else "managers_only"
        pt = project_type if project_type in _PROJECT_TYPES else "time_and_materials"
        row = TimeManagerClientProjectModel(
            id=pid,
            client_id=client_id,
            name=name.strip(),
            code=self._normalize_code(code),
            start_date=start_date,
            end_date=end_date,
            notes=notes,
            report_visibility=rv,
            project_type=pt,
            billable_rate_type=(_strip_opt(billable_rate_type)),
            budget_type=(_strip_opt(budget_type)),
            budget_amount=budget_amount,
            budget_hours=budget_hours,
            budget_resets_every_month=budget_resets_every_month,
            budget_includes_expenses=budget_includes_expenses,
            send_budget_alerts=send_budget_alerts,
            budget_alert_threshold_percent=budget_alert_threshold_percent,
            fixed_fee_amount=fixed_fee_amount,
            is_archived=bool(is_archived),
            created_at=now,
            updated_at=None,
        )
        self._session.add(row)
        return row

    async def update(
        self,
        client_id: str,
        project_id: str,
        patch: dict[str, Any],
    ) -> TimeManagerClientProjectModel | None:
        row = await self.get_by_id(client_id, project_id)
        if not row:
            return None
        if "name" in patch and patch["name"] is not None:
            row.name = str(patch["name"]).strip()
        if "code" in patch:
            v = patch["code"]
            row.code = None if v is None else self._normalize_code(str(v))
        if "start_date" in patch:
            row.start_date = patch["start_date"]
        if "end_date" in patch:
            row.end_date = patch["end_date"]
        if "notes" in patch:
            row.notes = patch["notes"]
        if "report_visibility" in patch and patch["report_visibility"] is not None:
            rv = str(patch["report_visibility"])
            row.report_visibility = rv if rv in _REPORT_VISIBILITY else row.report_visibility
        if "project_type" in patch and patch["project_type"] is not None:
            pt = str(patch["project_type"])
            row.project_type = pt if pt in _PROJECT_TYPES else row.project_type
        if "billable_rate_type" in patch:
            row.billable_rate_type = _strip_opt(patch["billable_rate_type"])
        if "budget_type" in patch:
            row.budget_type = _strip_opt(patch["budget_type"])
        if "budget_amount" in patch:
            row.budget_amount = _decimal_none(patch["budget_amount"])
        if "budget_hours" in patch:
            row.budget_hours = _decimal_none(patch["budget_hours"])
        if "budget_resets_every_month" in patch:
            row.budget_resets_every_month = bool(patch["budget_resets_every_month"])
        if "budget_includes_expenses" in patch:
            row.budget_includes_expenses = bool(patch["budget_includes_expenses"])
        if "send_budget_alerts" in patch:
            row.send_budget_alerts = bool(patch["send_budget_alerts"])
        if "budget_alert_threshold_percent" in patch:
            row.budget_alert_threshold_percent = _decimal_none(patch["budget_alert_threshold_percent"])
        if "fixed_fee_amount" in patch:
            row.fixed_fee_amount = _decimal_none(patch["fixed_fee_amount"])
        if "is_archived" in patch and patch["is_archived"] is not None:
            row.is_archived = bool(patch["is_archived"])
        row.updated_at = _now_utc()
        self._session.add(row)
        return row

    async def delete(self, client_id: str, project_id: str) -> bool:
        row = await self.get_by_id(client_id, project_id)
        if not row:
            return False
        await self._session.execute(
            delete(TimeManagerClientProjectModel).where(
                TimeManagerClientProjectModel.client_id == client_id,
                TimeManagerClientProjectModel.id == project_id,
            )
        )
        return True
