"""Нормализация путей API учёта времени под префикс роутера gateway `/api/v1/time-tracking`."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _set_path(request: Request, new_path: str) -> None:
    request.scope["path"] = new_path
    rp = request.scope.get("raw_path")
    if isinstance(rp, (bytes, bytearray)):
        request.scope["raw_path"] = new_path.encode("ascii")


class TimeTrackingClientsPathRewriteMiddleware(BaseHTTPMiddleware):
    """Переписывает устаревшие/альтернативные префиксы на `/api/v1/time-tracking/...`.

    - `/api/v1/clients/...` — если nginx отдаёт без префикса time-tracking.
    - `/api/v1/time_tracking/...` — если фронт использует snake_case вместо дефиса.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.scope.get("path") or ""
        new_path: str | None = None
        if path == "/api/v1/clients" or path.startswith("/api/v1/clients/"):
            new_path = "/api/v1/time-tracking" + path[len("/api/v1") :]
        elif path == "/api/v1/time_tracking" or path.startswith("/api/v1/time_tracking/"):
            new_path = "/api/v1/time-tracking" + path[len("/api/v1/time_tracking") :]
        if new_path is not None:
            _set_path(request, new_path)
        return await call_next(request)
