from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/auth/azure", tags=["auth"])


def _clear_oauth_cookies(resp: RedirectResponse) -> None:
    resp.delete_cookie("oauth_state_nonce", path="/")
    resp.delete_cookie("oauth_target", path="/")


@router.get(
    "/login",
    summary="Azure Login",
    description="Редирект на вход через Microsoft. target=admin — после входа редирект на админ-панель (state=admin устарел).",
)
async def azure_login(
    target: str = Query("main"),
    state: Optional[str] = Query(None, description="Устарело: используйте target=admin"),
):
    settings = get_settings()
    t = "admin" if (state == "admin" or target == "admin") else "main"
    url = f"{settings.auth_service_url}/auth/login?target={t}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, follow_redirects=False)
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail="Auth service unavailable. Check: docker compose ps auth; docker compose logs auth",
        ) from e
    if r.status_code in (301, 302, 303, 307, 308):
        resp = RedirectResponse(url=r.headers["location"], status_code=r.status_code)
        try:
            cookies = r.headers.get_list("set-cookie")
        except AttributeError:
            cookies = []
        for c in cookies:
            resp.headers.append("set-cookie", c)
        return resp
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
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail="Auth service unavailable",
        ) from e
    if r.status_code in (301, 302, 303, 307, 308):
        return RedirectResponse(url=r.headers["location"], status_code=r.status_code)
    raise HTTPException(status_code=502, detail="Auth service unavailable")


@router.get("/callback")
async def azure_callback(
    request: Request,
    code: str,
    state: Optional[str] = Query(None),
):
    settings = get_settings()
    nonce_ok = (request.cookies.get("oauth_state_nonce") or "").strip()
    target_t = (request.cookies.get("oauth_target") or "main").strip()
    if not state or not nonce_ok or state != nonce_ok:
        base = (settings.frontend_url or "http://localhost").rstrip("/")
        path = "/login?error=oauth_state"
        if target_t == "admin" and (settings.admin_frontend_url or "").strip():
            base = settings.admin_frontend_url.rstrip("/")
            path = "/index.html?error=oauth_state"
        resp = RedirectResponse(url=base + path, status_code=302)
        _clear_oauth_cookies(resp)
        return resp

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{settings.auth_service_url}/auth/exchange",
            json={"code": code},
        )
    if r.status_code != 200:
        base = settings.admin_frontend_url if target_t == "admin" else settings.frontend_url
        base = (base or settings.frontend_url).rstrip("/")
        path = "/index.html?error=auth_failed" if target_t == "admin" else "/login?error=auth_failed"
        resp = RedirectResponse(url=base + path, status_code=302)
        _clear_oauth_cookies(resp)
        return resp
    data = r.json()
    access_token = data.get("access_token", "")
    if target_t == "admin" and settings.admin_frontend_url:
        base = settings.admin_frontend_url.rstrip("/")
        callback_path = "/auth/callback.html"
    else:
        base = settings.frontend_url.rstrip("/")
        callback_path = "/auth/callback"
    resp = RedirectResponse(
        url=f"{base}{callback_path}#access_token={access_token}",
        status_code=302,
    )
    _clear_oauth_cookies(resp)
    return resp
