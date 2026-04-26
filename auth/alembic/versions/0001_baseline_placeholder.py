"""Baseline: схема создаётся через create_all на старте; дальнейшие изменения — через autogenerate.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-21

"""

from typing import Sequence, Union  # noqa: I001

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Таблицы уже могут существовать (create_all). Не дублируем DDL здесь до перехода на «только миграции».
    pass


def downgrade() -> None:
    pass
