"""Тесты Time Tracking API."""

import pytest


@pytest.mark.skip(reason="Требует PostgreSQL")
async def test_time_tracking_health(time_tracking_client):
    """Health endpoint."""
    r = await time_tracking_client.get("/health")
    assert r.status_code in (200, 503)
