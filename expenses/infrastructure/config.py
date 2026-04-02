from decimal import Decimal
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SERVICE_DIR.parent


def _env_files() -> tuple[str, ...]:
    paths: list[str] = []
    for p in (_SERVICE_DIR / ".env", _REPO_ROOT / ".env"):
        if p.is_file():
            paths.append(str(p))
    return tuple(paths) if paths else (".env",)


class Settings(BaseSettings):
    # Docker: DATABASE_URL. Локально из корневого .env — как у остальных сервисов: EXPENSES_DATABASE_URL
    database_url: str = Field(
        default="",
        validation_alias=AliasChoices("DATABASE_URL", "EXPENSES_DATABASE_URL"),
    )
    media_path: str = "./media"
    service_name: str = "expenses"
    auth_service_url: str = "http://auth:1236"

    @field_validator("auth_service_url", mode="before")
    @classmethod
    def _default_auth_url_if_empty(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and not v.strip()):
            return "http://auth:1236"
        return v
    max_upload_mb: int = 25
    # Если задано — submit и create с суммой выше лимита получают ошибку (доп. согласование)
    expense_amount_limit_uzs: Decimal | None = None

    model_config = SettingsConfigDict(
        env_file=_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url", mode="after")
    @classmethod
    def _database_url_non_empty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError(
                "Укажите DATABASE_URL или EXPENSES_DATABASE_URL (см. .env в корне репозитория)."
            )
        return v

    @field_validator("expense_amount_limit_uzs", mode="before")
    @classmethod
    def empty_limit(cls, v):
        if v is None or v == "":
            return None
        return v


def get_settings() -> Settings:
    return Settings()
