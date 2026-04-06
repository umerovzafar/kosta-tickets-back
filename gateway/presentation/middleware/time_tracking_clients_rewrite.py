"""Если nginx отдаёт запросы к Time Manager как /api/v1/clients/... без префикса time-tracking."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class TimeTrackingClientsPathRewriteMiddleware(BaseHTTPMiddleware):
    """Переписывает /api/v1/clients/... → /api/v1/time-tracking/clients/... для совпадения с роутером gateway."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.scope.get("path") or ""
        if path == "/api/v1/clients" or path.startswith("/api/v1/clients/"):
            suffix = path[len("/api/v1") :]
            new_path = "/api/v1/time-tracking" + suffix
            request.scope["path"] = new_path
            rp = request.scope.get("raw_path")
            if isinstance(rp, (bytes, bytearray)):
                request.scope["raw_path"] = new_path.encode("ascii")
        return await call_next(request)
