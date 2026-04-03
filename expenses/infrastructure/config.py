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
    max_upload_mb: int = 15
    # Если задано — submit и create с суммой выше лимита получают ошибку (доп. согласование)
    expense_amount_limit_uzs: Decimal | None = None

    # Почта: уведомление о новой заявке (submit → pending_approval). Microsoft 365: SMTP AUTH,
    # smtp.office365.com:587 + STARTTLS, учётная запись с включённой SMTP-аутентификацией (или app password).
    expense_notify_on_submit: bool = Field(
        default=True,
        validation_alias=AliasChoices("EXPENSE_NOTIFY_ON_SUBMIT"),
    )
    expense_notify_to: str = Field(
        default="zumerov@kostalegal.com",
        validation_alias=AliasChoices("EXPENSE_NOTIFY_TO"),
    )
    smtp_host: str = Field(default="", validation_alias=AliasChoices("EXPENSE_SMTP_HOST", "SMTP_HOST"))
    smtp_port: int = Field(default=587, validation_alias=AliasChoices("EXPENSE_SMTP_PORT", "SMTP_PORT"))
    smtp_user: str = Field(default="", validation_alias=AliasChoices("EXPENSE_SMTP_USER", "SMTP_USER"))
    smtp_password: str = Field(
        default="",
        validation_alias=AliasChoices("EXPENSE_SMTP_PASSWORD", "SMTP_PASSWORD"),
    )
    smtp_use_tls: bool = Field(
        default=True,
        validation_alias=AliasChoices("EXPENSE_SMTP_USE_TLS", "SMTP_USE_TLS"),
    )
    expense_mail_from: str = Field(
        default="",
        validation_alias=AliasChoices("EXPENSE_MAIL_FROM", "EXPENSE_SMTP_FROM"),
    )
    # Ссылка в письме: подставьте {frontend_url} и {expense_id} (хэш-роутер: "{frontend_url}/#/expenses/{expense_id}")
    expense_notify_link_template: str = Field(
        default="{frontend_url}/expenses/{expense_id}",
        validation_alias=AliasChoices("EXPENSE_NOTIFY_LINK_TEMPLATE"),
    )
    frontend_url: str = Field(
        default="",
        validation_alias=AliasChoices("FRONTEND_URL", "EXPENSES_FRONTEND_URL"),
    )
    # Параметр в ссылках кнопок «Утвердить» / «Отклонить» (обрабатывает SPA после входа)
    expense_notify_intent_param: str = Field(
        default="intent",
        validation_alias=AliasChoices("EXPENSE_NOTIFY_INTENT_PARAM"),
    )

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

    @field_validator("expense_notify_link_template", mode="before")
    @classmethod
    def _default_link_template_if_blank(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and not str(v).strip()):
            return "{frontend_url}/expenses/{expense_id}"
        return v


def get_settings() -> Settings:
    return Settings()
