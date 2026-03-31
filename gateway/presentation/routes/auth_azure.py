from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
import httpx
from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/auth/azure", tags=["auth"])


@router.get(
    "/login",
    summary="Azure Login",
    description="Редирект на вход через Microsoft. state=admin — после входа редирект на админ-панель.",
)
async def azure_login(state: Optional[str] = Query(None)):
    settings = get_settings()
    url = f"{settings.auth_service_url}/auth/login"
    if state:
        url = f"{url}?state={state}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, follow_redirects=False)
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise HTTPException(
            status_code=502,
            detail="Auth service unavailable. Check: docker compose ps auth; docker compose logs auth",
        ) from e
    if r.status_code in (301, 302, 303, 307, 308):
        return RedirectResponse(url=r.headers["location"], status_code=r.status_code)
    raise HTTPException(
        status_code=502,
        detail="Auth service unavailable. Check: docker compose ps auth; docker compose logs auth",
    )


@router.get(
    "/logout",
    summary="Logout",
    description="Редирект на выход из Microsoft.",
)
async def azure_logout():
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{settings.auth_service_url}/auth/logout",
                follow_redirects=False,
            )
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise HTTPException(
            status_code=502,
            detail="Auth service unavailable",
        ) from e
    if r.status_code in (301, 302, 303, 307, 308):
        return RedirectResponse(url=r.headers["location"], status_code=r.status_code)
    raise HTTPException(status_code=502, detail="Auth service unavailable")


@router.get("/callback")
async def azure_callback(code: str, state: Optional[str] = Query(None)):
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{settings.auth_service_url}/auth/exchange",
            json={"code": code},
        )
    if r.status_code != 200:
        base = settings.admin_frontend_url if state == "admin" else settings.frontend_url
        base = (base or settings.frontend_url).rstrip("/")
        path = "/index.html?error=auth_failed" if state == "admin" else "/login?error=auth_failed"
        return RedirectResponse(url=base + path, status_code=302)
    data = r.json()
    access_token = data.get("access_token", "")
    if state == "admin" and settings.admin_frontend_url:
        base = settings.admin_frontend_url.rstrip("/")
        callback_path = "/auth/callback.html"
    else:
        base = settings.frontend_url.rstrip("/")
        callback_path = "/auth/callback"
    return RedirectResponse(
        url=f"{base}{callback_path}#access_token={access_token}",
        status_code=302,
    )
