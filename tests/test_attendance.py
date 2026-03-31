"""Тесты Attendance API."""

import pytest


@pytest.mark.skip(reason="Требует PostgreSQL и изолированный path")
async def test_attendance_health(attendance_client):
    """Health endpoint."""
    r = await attendance_client.get("/health")
    assert r.status_code in (200, 503)


@pytest.mark.skip(reason="Требует изолированный path")
async def test_attendance_hikvision_no_config(attendance_client):
    """Hikvision без настройки IP — 400 или пустой результат."""
    r = await attendance_client.get("/hikvision/attendance")
    assert r.status_code in (200, 400)
