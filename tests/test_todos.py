"""Тесты Todos API."""

import pytest


@pytest.mark.skip(reason="Требует PostgreSQL")
async def test_todos_health(todos_client):
    """Health endpoint."""
    r = await todos_client.get("/health")
    assert r.status_code in (200, 503)
