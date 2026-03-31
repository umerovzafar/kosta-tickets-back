"""Общие фикстуры и настройки для тестов."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

_root = Path(__file__).resolve().parent.parent
_SERVICES = ("gateway", "auth", "tickets", "notifications", "inventory", "attendance", "time_tracking", "todos")


def _ensure_service_in_path(service: str):
    """Оставить только нужный сервис в path для изоляции импортов."""
    service_paths = {str((_root / s).resolve()) for s in _SERVICES if (_root / s).exists()}
    for p in list(sys.path):
        try:
            if Path(p).resolve() in {Path(x).resolve() for x in service_paths}:
                sys.path.remove(p)
        except (OSError, ValueError):
            pass
    target = _root / service
    if target.exists():
        sys.path.insert(0, str(target.resolve()))
    # Очистить кэш модулей других сервисов (включая presentation, infrastructure)
    to_remove = [
        k for k in sys.modules
        if k in ("presentation", "infrastructure", "application", "domain")
        or k.startswith(("presentation.", "infrastructure.", "application.", "domain."))
    ]
    for k in to_remove:
        del sys.modules[k]


def pytest_configure(config):
    """Установка переменных окружения до импорта приложений."""
    os.environ.setdefault("JWT_SECRET", "test-jwt-secret-min-32-characters-long")
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test")
    os.environ.setdefault("TICKETS_SERVICE_URL", "http://tickets:1235")
    os.environ.setdefault("AUTH_SERVICE_URL", "http://auth:1236")
    os.environ.setdefault("NOTIFICATIONS_SERVICE_URL", "http://notifications:1237")
    os.environ.setdefault("INVENTORY_SERVICE_URL", "http://inventory:1238")
    os.environ.setdefault("ATTENDANCE_SERVICE_URL", "http://attendance:1239")
    os.environ.setdefault("TIME_TRACKING_SERVICE_URL", "http://time_tracking:1241")
    os.environ.setdefault("TODOS_SERVICE_URL", "http://todos:1240")
    os.environ.setdefault("GATEWAY_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test")
    os.environ.setdefault("AUTH_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test")
    os.environ.setdefault("TICKETS_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test")
    os.environ.setdefault("NOTIFICATIONS_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test")
    os.environ.setdefault("INVENTORY_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test")
    os.environ.setdefault("ATTENDANCE_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test")
    os.environ.setdefault("TODOS_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test")
    os.environ.setdefault("TIME_TRACKING_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/test")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def gateway_client():
    """Клиент для тестирования Gateway API."""
    _ensure_service_in_path("gateway")
    from gateway.presentation.api import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def auth_client():
    """Клиент для тестирования Auth API."""
    _ensure_service_in_path("auth")
    with patch("auth.infrastructure.config.validate_production_secrets", lambda x: None):
        from auth.presentation.api import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def tickets_client():
    """Клиент для тестирования Tickets API."""
    _ensure_service_in_path("tickets")
    from tickets.presentation.api import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def notifications_client():
    """Клиент для тестирования Notifications API."""
    _ensure_service_in_path("notifications")
    from notifications.presentation.api import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def inventory_client():
    """Клиент для тестирования Inventory API."""
    _ensure_service_in_path("inventory")
    from inventory.presentation.api import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def attendance_client():
    """Клиент для тестирования Attendance API."""
    _ensure_service_in_path("attendance")
    from attendance.presentation.api import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def time_tracking_client():
    """Клиент для тестирования Time Tracking API."""
    _ensure_service_in_path("time_tracking")
    from time_tracking.presentation.api import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def todos_client():
    """Клиент для тестирования Todos API."""
    _ensure_service_in_path("todos")
    from todos.presentation.api import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
