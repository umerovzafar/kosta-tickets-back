from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from application.use_cases import (
    GetCurrentUserUseCase,
    ListUsersUseCase,
    SetRoleUseCase,
    BlockUserUseCase,
    ArchiveUserUseCase,
    SetTimeTrackingRoleUseCase,
    SetPositionUseCase,
)
from application.ports import UserRepositoryPort, TokenServicePort, RoleRepositoryPort
from domain.entities import User
from infrastructure.database import get_session
from infrastructure.repositories import UserRepository, RoleRepository
from infrastructure.jwt_service import JWTService
from domain.roles import Role
from presentation.schemas import (
    UserResponse,
    UserDetailResponse,
    SetRoleRequest,
    BlockUserRequest,
    ArchiveUserRequest,
    TimeTrackingRoleRequest,
    SetPositionRequest,
)

router = APIRouter(prefix="/users", tags=["users"])


def get_user_repo(session: AsyncSession = Depends(get_session)) -> UserRepositoryPort:
    return UserRepository(session)


def get_role_repo(session: AsyncSession = Depends(get_session)) -> RoleRepositoryPort:
    return RoleRepository(session)


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


def _user_to_response(user: User, permissions: Optional[dict] = None) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        picture=user.picture,
        role=user.role,
        position=user.position,
        is_blocked=user.is_blocked,
        is_archived=user.is_archived,
        created_at=user.created_at,
        updated_at=user.updated_at,
        permissions=permissions,
        time_tracking_role=user.time_tracking_role,
    )


def _user_to_detail(user: User) -> UserDetailResponse:
    return UserDetailResponse(
        id=user.id,
        azure_oid=user.azure_oid,
        email=user.email,
        display_name=user.display_name,
        picture=user.picture,
        role=user.role,
        position=user.position,
        is_blocked=user.is_blocked,
        is_archived=user.is_archived,
        time_tracking_role=user.time_tracking_role,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def require_main_admin(current_user: User = Depends(get_current_user)) -> User:
    """Только Главный администратор."""
    if (current_user.role or "").strip() != Role.MAIN_ADMIN.value:
        raise HTTPException(status_code=403, detail="Only Main Administrator can perform this action")
    return current_user


def require_main_admin_or_admin(current_user: User = Depends(get_current_user)) -> User:
    """Главный администратор или Администратор — управление доступом к учёту времени и ролями учёта времени."""
    role = (current_user.role or "").strip()
    if role not in (Role.MAIN_ADMIN.value, Role.ADMIN.value):
        raise HTTPException(status_code=403, detail="Only Main Administrator or Administrator can manage time tracking access")
    return current_user


@router.get("", response_model=list[UserResponse])
async def list_users(
    include_archived: bool = Query(False, description="Include archived users"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
):
    uc = ListUsersUseCase(user_repo)
    users = await uc.execute(include_archived=include_archived)
    return [_user_to_response(u) for u in users]  # без permissions в списке


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return _user_to_response(current_user, permissions=None)


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
    current_user: User = Depends(require_main_admin),
    session: AsyncSession = Depends(get_session),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
    role_repo: RoleRepositoryPort = Depends(get_role_repo),
):
    """Назначить роль пользователю. Только Главный администратор."""
    uc = SetRoleUseCase(user_repo, role_repo)
    user = await uc.execute(user_id, body.role)
    await session.commit()
    if not user:
        raise HTTPException(status_code=404, detail="User not found or role does not exist")
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


@router.patch("/{user_id}/time-tracking-role", response_model=UserDetailResponse)
async def set_time_tracking_role(
    user_id: int,
    body: TimeTrackingRoleRequest,
    current_user: User = Depends(require_main_admin_or_admin),
    session: AsyncSession = Depends(get_session),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
):
    """Назначить роль в модуле учёта времени: user — ведение учёта, manager — управление списком пользователей. Главный администратор или Администратор."""
    value = (body.time_tracking_role or "").strip() or None
    if value is not None and value not in ("user", "manager"):
        raise HTTPException(status_code=400, detail="time_tracking_role must be 'user', 'manager' or null")
    uc = SetTimeTrackingRoleUseCase(user_repo)
    user = await uc.execute(user_id, value)
    await session.commit()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_detail(user)


@router.patch("/{user_id}/position", response_model=UserDetailResponse)
async def set_position(
    user_id: int,
    body: SetPositionRequest,
    current_user: User = Depends(require_main_admin_or_admin),
    session: AsyncSession = Depends(get_session),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
):
    """Установить должность пользователя. Главный администратор или Администратор."""
    value = (body.position or "").strip() or None
    uc = SetPositionUseCase(user_repo)
    user = await uc.execute(user_id, value)
    await session.commit()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_detail(user)
