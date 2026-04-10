"""Helpers for readable, repeatable runtime schema patches."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def execute_sql(conn: AsyncConnection, statements: Iterable[str]) -> None:
    for statement in statements:
        await conn.execute(text(statement))


async def add_columns_if_missing(
    conn: AsyncConnection,
    table_name: str,
    column_definitions: Iterable[str],
) -> None:
    await execute_sql(
        conn,
        [
            f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_definition}"
            for column_definition in column_definitions
        ],
    )
