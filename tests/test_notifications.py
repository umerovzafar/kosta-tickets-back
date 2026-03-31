"""Тесты Notifications API."""

import pytest


@pytest.mark.skip(reason="Требует PostgreSQL")
async def test_notifications_health(notifications_client):
    """Health endpoint."""
    r = await notifications_client.get("/health")
    assert r.status_code in (200, 503)
