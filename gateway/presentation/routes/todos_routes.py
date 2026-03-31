"""Прокси запросов к сервису todos (календарь Outlook и др.)."""

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response as FastAPIResponse

from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/todos", tags=["todos"])


def _todos_base() -> str:
    return get_settings().todos_service_url.rstrip("/")


def _strip_hop_and_cors(headers: dict) -> dict:
    """Убираем hop-by-hop и CORS — их выставит gateway."""
    skip = {
        "transfer-encoding",
        "content-encoding",
        "connection",
        "keep-alive",
        "access-control-allow-origin",
        "access-control-allow-credentials",
        "access-control-allow-methods",
        "access-control-allow-headers",
        "access-control-expose-headers",
    }
    return {k: v for k, v in headers.items() if k.lower() not in skip}


@router.get("/calendar/connect", summary="Outlook: URL авторизации (всегда JSON для фронта)")
async def todos_calendar_connect(request: Request):
    """
    Фронт ожидает JSON {"url": "..."}, без HTTP-редиректа (иначе fetch уходит на login.microsoft и ломается по CORS).
    Явный маршрут гарантирует 200 + JSON даже если общий прокси когда-либо пробросил бы редирект.
    """
    base = _todos_base()
    if not base:
        return JSONResponse(
            status_code=503,
            content={"detail": "TODOS_SERVICE_URL not configured"},
        )
    url = f"{base}/api/v1/todos/calendar/connect"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    auth = request.headers.get("Authorization")
    headers = {"Authorization": auth} if auth else {}
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            r = await client.get(url, headers=headers)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException):
        return JSONResponse(
            status_code=503,
            content={"detail": "Todos service unavailable"},
        )
    except Exception:
        return JSONResponse(status_code=502, content={"detail": "Bad gateway"})
    if r.is_redirect:
        return JSONResponse(
            status_code=502,
            content={
                "detail": (
                    "Сервис todos вернул HTTP-редирект вместо JSON. "
                    "Обновите контейнер todos: GET /calendar/connect должен отдавать {\"url\": \"...\"}."
                )
            },
        )
    if r.status_code == 401:
        return JSONResponse(status_code=401, content={"detail": "Authorization required"})
    if r.status_code >= 400:
        try:
            body = r.json()
            if isinstance(body, dict):
                return JSONResponse(status_code=r.status_code, content=body)
        except Exception:
            pass
        return JSONResponse(
            status_code=r.status_code,
            content={"detail": (r.text or "Todos error")[:2000]},
        )
    try:
        data = r.json()
    except Exception:
        return JSONResponse(
            status_code=502,
            content={"detail": "Ответ todos /calendar/connect не JSON — ожидалось {\"url\": \"...\"}"},
        )
    if not isinstance(data, dict) or "url" not in data or not data["url"]:
        return JSONResponse(
            status_code=502,
            content={"detail": "В ответе todos нет поля url"},
        )
    return JSONResponse(content={"url": data["url"]})


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_todos(request: Request, path: str):
    """Проксирование запросов к сервису todos."""
    base = _todos_base()
    if not base:
        return JSONResponse(
            status_code=503,
            content={"detail": "TODOS_SERVICE_URL not configured"},
        )
    url = f"{base}/api/v1/todos/{path}" if path else f"{base}/api/v1/todos"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    headers = dict(request.headers)
    headers.pop("host", None)
    try:
        body = await request.body()
    except Exception:
        body = b""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            r = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException):
        return JSONResponse(
            status_code=503,
            content={"detail": "Todos service unavailable"},
        )
    except Exception:
        return JSONResponse(
            status_code=502,
            content={"detail": "Bad gateway"},
        )
    response_headers = _strip_hop_and_cors(dict(r.headers))
    return FastAPIResponse(
        content=r.content,
        status_code=r.status_code,
        headers=response_headers,
    )
