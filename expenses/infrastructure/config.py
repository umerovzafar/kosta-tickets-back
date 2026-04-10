from decimal import Decimal
from functools import lru_cache
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
    # True — модератор может утверждать/отклонять свою заявку; false — как раньше (запрет)
    expense_allow_self_moderation: bool = Field(
        default=True,
        validation_alias=AliasChoices("EXPENSE_ALLOW_SELF_MODERATION"),
    )
    # Если задано — submit и create с суммой выше лимита получают ошибку (доп. согласование)
    expense_amount_limit_uzs: Decimal | None = None

    # Почта: Microsoft 365: SMTP AUTH, smtp.office365.com:587 + STARTTLS.
    expense_notify_on_submit: bool = Field(
        default=True,
        validation_alias=AliasChoices("EXPENSE_NOTIFY_ON_SUBMIT"),
    )
    expense_notify_to: str = Field(
        default="zumerov@kostalegal.com",
        validation_alias=AliasChoices("EXPENSE_NOTIFY_TO"),
    )
    # JSON: {"default":["a@x.com"],"rules":[{"if":{"departmentId":"…"},"to":["b@x.com"]}]} — см. expense_notify_routing.py
    expense_notify_routing_json: str = Field(
        default="",
        validation_alias=AliasChoices("EXPENSE_NOTIFY_ROUTING_JSON"),
    )

    @field_validator("expense_notify_routing_json", mode="before")
    @classmethod
    def _strip_bom_routing_json(cls, v: object) -> object:
        if isinstance(v, str) and v.startswith("\ufeff"):
            return v.lstrip("\ufeff")
        return v
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
    # Публичный URL gateway (https://… без слэша) — ссылки «одним кликом» в письме: /api/v1/expenses/.../email-action
    public_api_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("GATEWAY_BASE_URL", "PUBLIC_API_BASE_URL", "EXPENSES_PUBLIC_API_BASE_URL"),
    )
    # Секрет HMAC для токена в письме; без него кнопки ведут только на фронт с ?intent=
    expense_email_action_secret: str = Field(
        default="",
        validation_alias=AliasChoices("EXPENSE_EMAIL_ACTION_SECRET"),
    )
    expense_email_action_ttl_seconds: int = Field(
        default=604800,
        ge=60,
        le=2592000,
        validation_alias=AliasChoices("EXPENSE_EMAIL_ACTION_TTL_SECONDS"),
    )
    # Если true — ссылки в письме ведут на страницу подтверждения, затем одно нажатие выполняет действие (без SPA).
    expense_email_action_confirm_step: bool = Field(
        default=True,
        validation_alias=AliasChoices("EXPENSE_EMAIL_ACTION_CONFIRM_STEP"),
    )
    # Письмо автору заявки после утверждения / отклонения
    expense_notify_author_on_decision: bool = Field(
        default=True,
        validation_alias=AliasChoices("EXPENSE_NOTIFY_AUTHOR_ON_DECISION"),
    )
    # Письмо автору после отметки «Оплачено» (кто отметил — в теле письма и в поле paidBy в API)
    expense_notify_author_on_paid: bool = Field(
        default=True,
        validation_alias=AliasChoices("EXPENSE_NOTIFY_AUTHOR_ON_PAID"),
    )
    # Опционально: Bearer JWT для GET /users/{id}, когда нет заголовка (согласование по ссылке из письма)
    expense_auth_bearer_for_author_email: str = Field(
        default="",
        validation_alias=AliasChoices("EXPENSE_AUTH_BEARER_FOR_AUTHOR_EMAIL"),
    )
    # Сброс БД через POST /admin/expenses-database/reset (только главный администратор)
    expense_allow_database_reset: bool = Field(
        default=True,
        validation_alias=AliasChoices("EXPENSE_ALLOW_DATABASE_RESET"),
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

    @field_validator("smtp_port", mode="before")
    @classmethod
    def _smtp_port_empty_to_default(cls, v: object) -> object:
        # В Portainer часто задают EXPENSE_SMTP_PORT= без значения — иначе ошибка int
        if v == "" or v is None:
            return 587
        return v

    @field_validator("smtp_host", "smtp_user", "expense_mail_from", mode="after")
    @classmethod
    def _strip_smtp_identity(cls, v: str) -> str:
        return (v or "").strip()

    @field_validator("smtp_password", mode="after")
    @classmethod
    def _normalize_smtp_password(cls, v: str) -> str:
        # CRLF в .env на Windows ломают SMTP AUTH
        return (v or "").strip()

    @field_validator(
        "expense_allow_self_moderation",
        "expense_notify_on_submit",
        "smtp_use_tls",
        "expense_email_action_confirm_step",
        "expense_notify_author_on_decision",
        "expense_notify_author_on_paid",
        "expense_allow_database_reset",
        mode="before",
    )
    @classmethod
    def _empty_env_bool_as_default(cls, v: object) -> object:
        # В Portainer / .env часто задают VAR= без значения — приходит "", Pydantic падает на bool
        if v == "":
            return True
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
