from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from application.use_cases import (
    GetCurrentUserUseCase,
    ListUsersUseCase,
    SetRoleUseCase,
    BlockUserUseCase,
    ArchiveUserUseCase,
)
from application.ports import UserRepositoryPort, TokenServicePort
from domain.entities import User
from infrastructure.database import get_session
from infrastructure.repositories import UserRepository
from infrastructure.jwt_service import JWTService
from presentation.schemas import (
    UserResponse,
    UserDetailResponse,
    SetRoleRequest,
    BlockUserRequest,
    ArchiveUserRequest,
)

router = APIRouter(prefix="/users", tags=["users"])


def get_user_repo(session: AsyncSession = Depends(get_session)) -> UserRepositoryPort:
    return UserRepository(session)


def get_token_service() -> TokenServicePort:
    return JWTService()


async def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
    token_service: TokenServicePort = Depends(get_token_service),
) -> User:
    token = (authorization or "").replace("Bearer ", "").strip()
    uc = GetCurrentUserUseCase(user_repo, token_service)
    user = await uc.execute(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        picture=user.picture,
        role=user.role,
        is_blocked=user.is_blocked,
        is_archived=user.is_archived,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _user_to_detail(user: User) -> UserDetailResponse:
    return UserDetailResponse(
        id=user.id,
        azure_oid=user.azure_oid,
        email=user.email,
        display_name=user.display_name,
        picture=user.picture,
        role=user.role,
        is_blocked=user.is_blocked,
        is_archived=user.is_archived,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("", response_model=list[UserResponse])
async def list_users(
    include_archived: bool = Query(False, description="Include archived users"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
):
    uc = ListUsersUseCase(user_repo)
    users = await uc.execute(include_archived)
    return [_user_to_response(u) for u in users]


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return _user_to_response(current_user)


@router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user_detail(
    user_id: int,
    current_user: User = Depends(get_current_user),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
):
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_detail(user)


@router.patch("/{user_id}/role", response_model=UserDetailResponse)
async def set_user_role(
    user_id: int,
    body: SetRoleRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
):
    uc = SetRoleUseCase(user_repo)
    user = await uc.execute(user_id, body.role)
    await session.commit()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_detail(user)


@router.patch("/{user_id}/block", response_model=UserDetailResponse)
async def block_user(
    user_id: int,
    body: BlockUserRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
):
    uc = BlockUserUseCase(user_repo)
    user = await uc.execute(user_id, body.is_blocked)
    await session.commit()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_detail(user)


@router.patch("/{user_id}/archive", response_model=UserDetailResponse)
async def archive_user(
    user_id: int,
    body: ArchiveUserRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
):
    uc = ArchiveUserUseCase(user_repo)
    user = await uc.execute(user_id, body.is_archived)
    await session.commit()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_detail(user)
