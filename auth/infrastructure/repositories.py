from typing import Optional, Sequence
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from domain.entities import User
from application.ports import UserRepositoryPort
from infrastructure.models import UserModel


class UserRepository(UserRepositoryPort):
    def __init__(self, session: AsyncSession):
        self._session = session

    def _to_entity(self, m: UserModel) -> User:
        return User(
            id=m.id,
            azure_oid=m.azure_oid,
            email=m.email,
            display_name=m.display_name,
            picture=m.picture,
            role=m.role,
            is_blocked=m.is_blocked,
            is_archived=m.is_archived,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    async def get_by_azure_oid(self, azure_oid: str) -> Optional[User]:
        result = await self._session.execute(select(UserModel).where(UserModel.azure_oid == azure_oid))
        row = result.scalars().one_or_none()
        return self._to_entity(row) if row else None

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self._session.execute(select(UserModel).where(UserModel.id == user_id))
        row = result.scalars().one_or_none()
        return self._to_entity(row) if row else None

    async def get_all(self, include_archived: bool = False) -> Sequence[User]:
        q = select(UserModel).order_by(UserModel.id)
        if not include_archived:
            q = q.where(UserModel.is_archived == False)
        result = await self._session.execute(q)
        rows = result.scalars().all()
        return [self._to_entity(r) for r in rows]

    async def create(
        self,
        azure_oid: str,
        email: str,
        display_name: Optional[str],
        picture: Optional[str],
        role: str,
    ) -> User:
        model = UserModel(
            azure_oid=azure_oid,
            email=email,
            display_name=display_name,
            picture=picture,
            role=role,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def update_profile(
        self,
        user_id: int,
        display_name: Optional[str],
        picture: Optional[str],
        role: Optional[str],
    ) -> Optional[User]:
        values = {}
        if display_name is not None:
            values["display_name"] = display_name
        if picture is not None:
            values["picture"] = picture
        if role is not None:
            values["role"] = role
        if values:
            await self._session.execute(
                update(UserModel).where(UserModel.id == user_id).values(**values)
            )
        await self._session.flush()
        return await self.get_by_id(user_id)

    async def set_role(self, user_id: int, role: str) -> Optional[User]:
        await self._session.execute(
            update(UserModel).where(UserModel.id == user_id).values(role=role)
        )
        await self._session.flush()
        return await self.get_by_id(user_id)

    async def set_blocked(self, user_id: int, is_blocked: bool) -> Optional[User]:
        await self._session.execute(
            update(UserModel).where(UserModel.id == user_id).values(is_blocked=is_blocked)
        )
        await self._session.flush()
        return await self.get_by_id(user_id)

    async def set_archived(self, user_id: int, is_archived: bool) -> Optional[User]:
        await self._session.execute(
            update(UserModel).where(UserModel.id == user_id).values(is_archived=is_archived)
        )
        await self._session.flush()
        return await self.get_by_id(user_id)
