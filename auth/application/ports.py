from abc import ABC, abstractmethod
from typing import Optional, Sequence
from domain.entities import User


class UserRepositoryPort(ABC):
    @abstractmethod
    async def get_by_azure_oid(self, azure_oid: str) -> Optional[User]:
        pass

    @abstractmethod
    async def get_by_id(self, user_id: int) -> Optional[User]:
        pass

    @abstractmethod
    async def get_all(self, include_archived: bool = False) -> Sequence[User]:
        pass

    @abstractmethod
    async def create(
        self,
        azure_oid: str,
        email: str,
        display_name: Optional[str],
        picture: Optional[str],
        role: str,
    ) -> User:
        pass

    @abstractmethod
    async def update_profile(
        self,
        user_id: int,
        display_name: Optional[str],
        picture: Optional[str],
        role: Optional[str],
    ) -> Optional[User]:
        pass

    @abstractmethod
    async def set_role(self, user_id: int, role: str) -> Optional[User]:
        pass

    @abstractmethod
    async def set_blocked(self, user_id: int, is_blocked: bool) -> Optional[User]:
        pass

    @abstractmethod
    async def set_archived(self, user_id: int, is_archived: bool) -> Optional[User]:
        pass


class TokenServicePort(ABC):
    @abstractmethod
    def create_access_token(self, user_id: int, azure_oid: str) -> str:
        pass

    @abstractmethod
    def decode_token(self, token: str) -> Optional[dict]:
        pass
