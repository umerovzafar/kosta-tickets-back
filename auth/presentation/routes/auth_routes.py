from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import RedirectResponse
from application.use_cases import AdminLoginUseCase, AzureLoginUseCase, GetCurrentUserUseCase
from application.ports import UserRepositoryPort, TokenServicePort, RoleRepositoryPort
from infrastructure.database import get_session
from infrastructure.repositories import UserRepository, RoleRepository
from infrastructure.jwt_service import JWTService
from infrastructure.azure_ad import get_login_url, get_logout_url, acquire_token_by_code
from domain.roles import Role
from infrastructure.config import get_settings
from presentation.schemas import UserResponse, TokenResponse, RoleItem, AdminLoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


def get_user_repo(session: AsyncSession = Depends(get_session)) -> UserRepositoryPort:
    return UserRepository(session)


def get_token_service() -> TokenServicePort:
    return JWTService()


def get_login_use_case(
    session: AsyncSession = Depends(get_session),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
    token_service: TokenServicePort = Depends(get_token_service),
) -> AzureLoginUseCase:
    return AzureLoginUseCase(user_repo, token_service)


def get_current_user_use_case(
    user_repo: UserRepositoryPort = Depends(get_user_repo),
    token_service: TokenServicePort = Depends(get_token_service),
) -> GetCurrentUserUseCase:
    return GetCurrentUserUseCase(user_repo, token_service)


def get_role_repo(session: AsyncSession = Depends(get_session)) -> RoleRepositoryPort:
    return RoleRepository(session)


@router.get("/roles")
async def list_roles(role_repo: RoleRepositoryPort = Depends(get_role_repo)):
    """Список ролей из БД (при первом запуске заполняется из enum по умолчанию)."""
    roles = await role_repo.list_all()
    return [RoleItem(value=r["name"], label=r["name"]) for r in roles]

@router.get("/login")
async def login(state: Optional[str] = None):
    return RedirectResponse(url=get_login_url(state=state))


@router.get("/logout")
async def logout():
    settings = get_settings()
    post_logout_redirect = f"{settings.frontend_url.rstrip('/')}/login"
    return RedirectResponse(url=get_logout_url(post_logout_redirect), status_code=302)


def _claims_to_user_and_token(claims: dict, uc: AzureLoginUseCase):
    azure_oid = claims.get("oid") or claims.get("sub") or ""
    email = claims.get("preferred_username") or claims.get("email") or ""
    display_name = claims.get("name")
    picture = claims.get("picture")
    return azure_oid, email, display_name, picture


@router.get("/callback")
async def callback(
    code: str,
    state: Optional[str] = None,
    uc: AzureLoginUseCase = Depends(get_login_use_case),
    session: AsyncSession = Depends(get_session),
):
    tokens = acquire_token_by_code(code)
    settings = get_settings()
    if not tokens or "id_token_claims" not in tokens:
        base = (settings.admin_frontend_url if state == "admin" else settings.frontend_url).rstrip("/")
        path = "/index.html?error=auth_failed" if state == "admin" else "/login?error=auth_failed"
        return RedirectResponse(url=base + path)
    claims = tokens["id_token_claims"]
    azure_oid, email, display_name, picture = _claims_to_user_and_token(claims, uc)
    if not azure_oid or not email:
        base = (settings.admin_frontend_url if state == "admin" else settings.frontend_url).rstrip("/")
        path = "/index.html?error=missing_claims" if state == "admin" else "/login?error=missing_claims"
        return RedirectResponse(url=base + path)
    user, access_token = await uc.execute(
        azure_oid, email, display_name, picture, Role.EMPLOYEE.value
    )
    await session.commit()
    if state == "admin" and settings.admin_frontend_url:
        redirect_base = settings.admin_frontend_url.rstrip("/")
        callback_path = "/auth/callback.html"
    else:
        redirect_base = settings.frontend_url.rstrip("/")
        callback_path = "/auth/callback"
    return RedirectResponse(
        url=f"{redirect_base}{callback_path}?access_token={access_token}",
        status_code=302,
    )


def get_admin_login_use_case(
    session: AsyncSession = Depends(get_session),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
    token_service: TokenServicePort = Depends(get_token_service),
) -> AdminLoginUseCase:
    settings = get_settings()
    return AdminLoginUseCase(
        user_repo, token_service,
        admin_username=settings.admin_username,
        admin_password=settings.admin_password,
    )


@router.post("/admin-login", response_model=TokenResponse)
async def admin_login(
    body: AdminLoginRequest,
    uc: AdminLoginUseCase = Depends(get_admin_login_use_case),
    session: AsyncSession = Depends(get_session),
):
    """Вход для админ-панели по логину и паролю (без Microsoft)."""
    token = await uc.execute(body.username, body.password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    await session.commit()
    return TokenResponse(access_token=token)


@router.post("/exchange", response_model=TokenResponse)
async def exchange(
    body: dict,
    uc: AzureLoginUseCase = Depends(get_login_use_case),
    session: AsyncSession = Depends(get_session),
):
    code = body.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="code required")
    tokens = acquire_token_by_code(code)
    if not tokens or "id_token_claims" not in tokens:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    claims = tokens["id_token_claims"]
    azure_oid, email, display_name, picture = _claims_to_user_and_token(claims, uc)
    if not azure_oid or not email:
        raise HTTPException(status_code=400, detail="Missing user claims")
    user, access_token = await uc.execute(
        azure_oid, email, display_name, picture, Role.EMPLOYEE.value
    )
    await session.commit()
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def me(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    uc: GetCurrentUserUseCase = Depends(get_current_user_use_case),
    role_repo: RoleRepositoryPort = Depends(get_role_repo),
    session=Depends(get_session),
):
    token = (authorization or "").replace("Bearer ", "").strip()
    user = await uc.execute(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
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
        permissions=None,
        time_tracking_role=user.time_tracking_role,
    )
