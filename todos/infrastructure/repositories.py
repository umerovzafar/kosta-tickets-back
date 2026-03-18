from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from application.ports import HealthRepositoryPort
from infrastructure.models import OutlookCalendarTokenModel


class HealthRepository(HealthRepositoryPort):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def check(self) -> bool:
        try:
            await self._session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


class OutlookCalendarTokenRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_user_id(self, user_id: int) -> OutlookCalendarTokenModel | None:
        r = await self._session.execute(
            select(OutlookCalendarTokenModel).where(
                OutlookCalendarTokenModel.user_id == user_id
            )
        )
        return r.scalars().one_or_none()

    async def upsert(
        self,
        *,
        user_id: int,
        access_token: str,
        refresh_token: str,
        expires_at: datetime | None,
    ) -> None:
        row = await self.get_by_user_id(user_id)
        if row:
            row.access_token = access_token
            row.refresh_token = refresh_token
            row.expires_at = expires_at
            self._session.add(row)
        else:
            self._session.add(
                OutlookCalendarTokenModel(
                    user_id=user_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=expires_at,
                )
            )
