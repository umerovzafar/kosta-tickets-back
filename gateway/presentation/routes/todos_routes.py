"""Прокси запросов к сервису todos (календарь Outlook и др.)."""

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response as FastAPIResponse

from infrastructure.config import get_settings

router = APIRouter(prefix="/api/v1/todos", tags=["todos"])
logger = logging.getLogger(__name__)


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
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException) as e:
        logger.warning("todos proxy request failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={"detail": "Todos service unavailable"},
        )
    except Exception as e:
        logger.exception("todos proxy error: %s", e)
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
