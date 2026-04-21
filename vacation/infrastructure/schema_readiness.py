"""Флаг готовности схемы БД (create_all завершён). Пока не set — API графика отвечает 503, не 500."""

import asyncio

schema_ready_event = asyncio.Event()


def mark_schema_ready() -> None:
    schema_ready_event.set()
