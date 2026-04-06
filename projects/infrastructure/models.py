"""Модели БД kosta_projects — таблицы добавим при проектировании домена."""

from infrastructure.database import Base

# Импорт для регистрации метаданных в Base.metadata (create_all в lifespan).
__all__ = ["Base"]
