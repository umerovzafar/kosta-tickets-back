from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports import HealthRepositoryPort
from infrastructure.models import TimeTrackingUserModel


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
