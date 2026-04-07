"""Идемпотентные правки схемы БД (PostgreSQL) для уже существующих инсталляций."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def apply_todo_board_columns_collapsed_patch(conn: AsyncConnection) -> None:
    """Колонка доски: признак «свёрнута» для UI."""
    await conn.execute(
        text(
            """
            ALTER TABLE todo_board_columns
            ADD COLUMN IF NOT EXISTS is_collapsed BOOLEAN NOT NULL DEFAULT FALSE
            """
        )
    )
