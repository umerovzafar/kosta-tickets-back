from typing import Optional
from domain.entities import User
from domain.roles import Role
from application.ports import UserRepositoryPort, TokenServicePort


class AzureLoginUseCase:
    def __init__(self, user_repo: UserRepositoryPort, token_service: TokenServicePort):
        self._user_repo = user_repo
        self._token_service = token_service

    async def execute(
        self,
        azure_oid: str,
        email: str,
        display_name: Optional[str],
        picture: Optional[str],
        role: str = Role.EMPLOYEE.value,
    ) -> tuple[User, str]:
        user = await self._user_repo.get_by_azure_oid(azure_oid)
        if not user:
            user = await self._user_repo.create(
                azure_oid, email, display_name, picture, role
            )
        token = self._token_service.create_access_token(user.id, user.azure_oid)
        return user, token


LOCAL_ADMIN_OID = "local-admin"


class AdminLoginUseCase:
    def __init__(
        self,
        user_repo: UserRepositoryPort,
        token_service: TokenServicePort,
        admin_username: str,
        admin_password: str,
    ):
        self._user_repo = user_repo
        self._token_service = token_service
        self._admin_username = admin_username
        self._admin_password = admin_password

    async def execute(self, username: str, password: str) -> str:
        if (username or "").strip() != self._admin_username or (password or "") != self._admin_password:
            return None
        user = await self._user_repo.get_by_azure_oid(LOCAL_ADMIN_OID)
        if not user:
            user = await self._user_repo.create(
                azure_oid=LOCAL_ADMIN_OID,
                email="admin@local",
                display_name="Администратор",
                picture=None,
                role=Role.ADMIN.value,
            )
        return self._token_service.create_access_token(user.id, user.azure_oid)


class GetCurrentUserUseCase:
    def __init__(self, user_repo: UserRepositoryPort, token_service: TokenServicePort):
        self._user_repo = user_repo
        self._token_service = token_service

    async def execute(self, access_token: str) -> Optional[User]:
        payload = self._token_service.decode_token(access_token)
        if not payload:
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        return await self._user_repo.get_by_id(int(user_id))


class UpdateProfileUseCase:
    def __init__(self, user_repo: UserRepositoryPort):
        self._user_repo = user_repo

    async def execute(
        self,
        user_id: int,
        display_name: Optional[str],
        picture: Optional[str],
        role: Optional[str],
    ) -> Optional[User]:
        return await self._user_repo.update_profile(
            user_id, display_name, picture, role
        )


class ListUsersUseCase:
    def __init__(self, user_repo: UserRepositoryPort):
        self._user_repo = user_repo

    async def execute(self, include_archived: bool = False) -> list:
        return list(await self._user_repo.get_all(include_archived))


class SetRoleUseCase:
    def __init__(self, user_repo: UserRepositoryPort):
        self._user_repo = user_repo

    async def execute(self, user_id: int, role: str) -> Optional[User]:
        return await self._user_repo.set_role(user_id, role)


class BlockUserUseCase:
    def __init__(self, user_repo: UserRepositoryPort):
        self._user_repo = user_repo

    async def execute(self, user_id: int, is_blocked: bool) -> Optional[User]:
        return await self._user_repo.set_blocked(user_id, is_blocked)


class ArchiveUserUseCase:
    def __init__(self, user_repo: UserRepositoryPort):
        self._user_repo = user_repo

    async def execute(self, user_id: int, is_archived: bool) -> Optional[User]:
        return await self._user_repo.set_archived(user_id, is_archived)
