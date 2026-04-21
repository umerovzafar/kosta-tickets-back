"""Конфигурация vacation: пароль БД должен совпадать с vacation_db в compose (VACATION_DB_*)."""

from functools import lru_cache
from urllib.parse import quote

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Полный URL (редко). По умолчанию URL собирается из VACATION_DB_* — тот же пароль, что у контейнера vacation_db.
    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "VACATION_DATABASE_URL"),
    )
    # true — использовать database_url как есть (нестандартный хост и т.д.). Иначе пароль всегда из VACATION_DB_*.
    vacation_use_explicit_database_url: bool = Field(
        default=False,
        validation_alias="VACATION_USE_EXPLICIT_DATABASE_URL",
    )
    vacation_db_user: str = Field(default="vacation", validation_alias="VACATION_DB_USER")
    vacation_db_password: str = Field(default="vacation", validation_alias="VACATION_DB_PASSWORD")
    vacation_db_host: str = Field(default="vacation_db", validation_alias="VACATION_DB_HOST")
    vacation_db_port: int = Field(default=5432, validation_alias="VACATION_DB_PORT")
    vacation_db_name: str = Field(default="kosta_vacation", validation_alias="VACATION_DB_NAME")
    service_name: str = "vacation"


def build_database_url_from_parts(settings: Settings) -> str:
    """postgresql://… с корректным экранированием пароля (символы @ : и т.д.)."""
    u = quote((settings.vacation_db_user or "vacation").strip() or "vacation", safe="")
    p = quote((settings.vacation_db_password or "").strip(), safe="")
    h = (settings.vacation_db_host or "vacation_db").strip() or "vacation_db"
    port = int(settings.vacation_db_port or 5432)
    n = (settings.vacation_db_name or "kosta_vacation").strip() or "kosta_vacation"
    return f"postgresql://{u}:{p}@{h}:{port}/{n}"


def resolve_database_url(settings: Settings) -> str:
    raw = (settings.database_url or "").strip()
    # Portainer часто держит старый VACATION_DATABASE_URL с другим паролем, чем VACATION_DB_PASSWORD / volume Postgres.
    if raw and settings.vacation_use_explicit_database_url:
        return raw
    return build_database_url_from_parts(settings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
