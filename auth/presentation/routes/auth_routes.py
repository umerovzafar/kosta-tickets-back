from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import RedirectResponse
from application.use_cases import AdminLoginUseCase, AzureLoginUseCase, BootstrapAdminUseCase, GetCurrentUserUseCase
from application.ports import UserRepositoryPort, TokenServicePort, RoleRepositoryPort
from infrastructure.database import get_session
from infrastructure.repositories import UserRepository, RoleRepository
from infrastructure.jwt_service import JWTService
from infrastructure.azure_ad import get_login_url, get_logout_url, acquire_token_by_code
from infrastructure.oauth_state_jwt import create_oauth_state_token, parse_oauth_state_token
from domain.roles import Role
from infrastructure.config import get_settings
from presentation.schemas import (
    UserResponse,
    TokenResponse,
    RoleItem,
    AdminLoginRequest,
    AdminBootstrapRequest,
    AdminBootstrapResponse,
    AdminBootstrapStatusResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

OAUTH_STATE_COOKIE = "oauth_state_nonce"
OAUTH_TARGET_COOKIE = "oauth_target"


def _clear_oauth_cookies(response: RedirectResponse) -> None:
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    response.delete_cookie(OAUTH_TARGET_COOKIE, path="/")


def _frontend_base(settings, target: str) -> str:
    preferred = settings.admin_frontend_url if target == "admin" else settings.frontend_url
    fallback = settings.frontend_url or settings.admin_frontend_url or "http://localhost"
    return (preferred or fallback).rstrip("/")


def _error_redirect(settings, target: str, error_code: str) -> RedirectResponse:
    path = "/index.html" if target == "admin" else "/login"
    return RedirectResponse(
        url=f"{_frontend_base(settings, target)}{path}?error={error_code}",
        status_code=302,
    )


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
async def login(
    target: str = Query("main", description="main или admin — куда редирект после входа"),
    state: Optional[str] = Query(
        None,
        description="Устарело: используйте target=admin вместо state=admin",
    ),
):
    settings = get_settings()
    t: str = "admin" if (target == "admin" or state == "admin") else "main"
    if t not in ("main", "admin"):
        t = "main"
    try:
        state_token = create_oauth_state_token(
            jwt_secret=settings.jwt_secret,
            jwt_algorithm=settings.jwt_algorithm,
            target=t,  # type: ignore[arg-type]
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return RedirectResponse(url=get_login_url(state=state_token), status_code=302)


@router.get("/logout")
async def logout():
    settings = get_settings()
    post_logout_redirect = f"{_frontend_base(settings, 'main')}/login"
    return RedirectResponse(url=get_logout_url(post_logout_redirect), status_code=302)


def _claims_to_user_and_token(claims: dict):
    azure_oid = claims.get("oid") or claims.get("sub") or ""
    email = claims.get("preferred_username") or claims.get("email") or ""
    display_name = claims.get("name")
    picture = claims.get("picture")
    return azure_oid, email, display_name, picture


@router.get("/callback")
async def callback(
    request: Request,
    code: str,
    state: Optional[str] = None,
    uc: AzureLoginUseCase = Depends(get_login_use_case),
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    target_t = parse_oauth_state_token(
        state,
        jwt_secret=settings.jwt_secret,
        jwt_algorithm=settings.jwt_algorithm,
    )
    if target_t is None:
        nonce_ok = (request.cookies.get(OAUTH_STATE_COOKIE) or "").strip()
        cookie_tgt = (request.cookies.get(OAUTH_TARGET_COOKIE) or "main").strip()
        if state and nonce_ok and state == nonce_ok:
            target_t = "admin" if cookie_tgt == "admin" else "main"
    if target_t is None:
        resp = _error_redirect(settings, "main", "oauth_state")
        _clear_oauth_cookies(resp)
        return resp

    tokens = acquire_token_by_code(code)
    if not tokens or "id_token_claims" not in tokens:
        resp = _error_redirect(settings, target_t, "auth_failed")
        _clear_oauth_cookies(resp)
        return resp
    claims = tokens["id_token_claims"]
    azure_oid, email, display_name, picture = _claims_to_user_and_token(claims)
    if not azure_oid or not email:
        resp = _error_redirect(settings, target_t, "missing_claims")
        _clear_oauth_cookies(resp)
        return resp
    user, access_token = await uc.execute(
        azure_oid, email, display_name, picture, Role.EMPLOYEE.value
    )
    await session.commit()
    if target_t == "admin" and settings.admin_frontend_url:
        redirect_base = settings.admin_frontend_url.rstrip("/")
        callback_path = "/auth/callback.html"
    else:
        redirect_base = _frontend_base(settings, "main")
        callback_path = "/auth/callback"
    resp = RedirectResponse(
        url=f"{redirect_base}{callback_path}#access_token={access_token}",
        status_code=302,
    )
    _clear_oauth_cookies(resp)
    return resp


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


def get_bootstrap_admin_use_case(
    session: AsyncSession = Depends(get_session),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
) -> BootstrapAdminUseCase:
    settings = get_settings()
    return BootstrapAdminUseCase(
        user_repo,
        admin_username=settings.admin_username,
        bootstrap_secret=settings.admin_bootstrap_secret,
    )


@router.get("/admin-bootstrap/status", response_model=AdminBootstrapStatusResponse)
async def admin_bootstrap_status(
    user_repo: UserRepositoryPort = Depends(get_user_repo),
):
    """Проверка, доступна ли первичная настройка (без авторизации)."""
    settings = get_settings()
    has_secret = bool((settings.admin_bootstrap_secret or "").strip())
    creds = await user_repo.get_local_admin_credentials()
    in_db = creds is not None
    return AdminBootstrapStatusResponse(
        bootstrap_available=has_secret and not in_db,
        credentials_in_database=in_db,
    )


@router.post("/admin-bootstrap", response_model=AdminBootstrapResponse)
async def admin_bootstrap(
    body: AdminBootstrapRequest,
    uc: BootstrapAdminUseCase = Depends(get_bootstrap_admin_use_case),
    user_repo: UserRepositoryPort = Depends(get_user_repo),
    session: AsyncSession = Depends(get_session),
):
    """
    Одноразовая генерация логина и пароля для входа в админ-панель.
    На сервере должен быть задан ADMIN_BOOTSTRAP_SECRET; в теле запроса — тот же секрет.
    После успеха пароль хранится в БД (bcrypt), пользователь local-admin — «Главный администратор».
    """
    settings = get_settings()
    if not (settings.admin_bootstrap_secret or "").strip():
        raise HTTPException(
            status_code=503,
            detail="Первичная настройка отключена. Задайте ADMIN_BOOTSTRAP_SECRET в окружении.",
        )
    if await user_repo.get_local_admin_credentials():
        raise HTTPException(
            status_code=409,
            detail="Учётная запись администратора уже создана. Вход через POST /auth/admin-login.",
        )
    result = await uc.execute(body.secret)
    if not result:
        raise HTTPException(status_code=403, detail="Неверный секрет")
    username, password = result
    await session.commit()
    return AdminBootstrapResponse(username=username, password=password)


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
    azure_oid, email, display_name, picture = _claims_to_user_and_token(claims)
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
