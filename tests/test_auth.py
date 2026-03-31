"""Тесты Auth API."""

import pytest


@pytest.mark.skip(reason="Требует PostgreSQL")
async def test_auth_health(auth_client):
    """Health endpoint."""
    r = await auth_client.get("/health")
    assert r.status_code in (200, 503)


@pytest.mark.skip(reason="Требует PostgreSQL")
async def test_auth_roles(auth_client):
    """Список ролей."""
    r = await auth_client.get("/auth/roles")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


async def test_auth_admin_login_invalid(auth_client):
    """Admin login с неверными данными — 401."""
    r = await auth_client.post(
        "/auth/admin-login",
        json={"username": "admin", "password": "wrong"},
    )
    assert r.status_code == 401
